import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentref.adapters import ClaudeAdapter, CodexAdapter
from agentref.core import SessionIR
from agentref.handoff import reconcile, build_context, safe_file
from agentref.index import Index
from agentref.mcp import Server
from agentref.parser import read_jsonl
from agentref.cli import select

FIXTURES = Path(__file__).parent / "fixtures"


class AgentRefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sources = self.root / "sessions"
        self.sources.mkdir()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()

    def fixture(self, agent="codex"):
        path = self.sources / (agent + ".jsonl")
        shutil.copyfile(FIXTURES / (agent + "-normal.jsonl"), path)
        adapter = (CodexAdapter if agent == "codex" else ClaudeAdapter)([self.sources])
        return path, adapter

    def index(self, adapter):
        idx = Index(self.root / "data", [adapter])
        self.addCleanup(idx.close)
        return idx

    def append(self, path, record):
        with path.open("ab") as f:
            f.write((json.dumps(record) + "\n").encode())

    def test_claude_normal(self):
        p, a = self.fixture("claude")
        s = a.readSession(p)
        self.assertEqual(s.sessionId, "claude-demo")
        self.assertEqual(s.latestAgentState, "turn-ended")
        self.assertEqual(len(s.fileOperations), 1)

    def test_codex_normal(self):
        p, a = self.fixture()
        s = a.readSession(p)
        self.assertEqual(s.sessionId, "codex-demo")
        self.assertEqual(s.latestAgentState, "turn-ended")
        self.assertEqual(s.versions, ["0.147.0"])

    def test_fork_keeps_first_identity(self):
        p, a = self.fixture()
        self.append(p, {"type": "session_meta", "payload": {"id": "parent-session", "cwd": "/parent"}})
        self.assertEqual(a.readSession(p).sessionId, "codex-demo")
        idx = self.index(a)
        idx.refresh()
        self.assertEqual(idx.sessions()[0]["sessionId"], "codex-demo")

    def test_tool_error_overrides_zero_exit_text(self):
        p, a = self.fixture("claude")
        p.write_text(p.read_text().replace('"tool_use_id":"c2","content"', '"tool_use_id":"c2","is_error":true,"content"'))
        self.assertEqual(a.readSession(p).testRuns[0]["status"], "FAILED")

    def test_opaque_exec_failure_is_preserved(self):
        p, a = self.fixture()
        self.append(p, {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "js", "name": "exec", "input": "await example();"}})
        self.append(p, {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "js", "output": [{"type": "input_text", "text": "Script failed\npatch rejected"}]}})
        session = a.readSession(p)
        self.assertEqual(session.toolCalls[-1]["status"], "FAILED")
        self.assertTrue(any(w["task"] == "Tool: exec" and w["status"] == "FAILED" for w in reconcile(session)["work"]))

    def test_claude_interrupted(self):
        p, a = self.fixture("claude")
        self.append(p, {"type": "system", "subtype": "interrupt", "content": "Ctrl+C"})
        self.assertEqual(a.readSession(p).latestAgentState, "interrupted")

    def test_codex_interrupted(self):
        p, a = self.fixture()
        self.append(p, {"type": "event_msg", "payload": {"type": "turn_aborted", "reason": "usage limit"}})
        self.assertEqual(a.readSession(p).latestAgentState, "interrupted")

    def test_malformed_trailing(self):
        p, a = self.fixture()
        before = len(a.readSession(p).toolCalls)
        with p.open("ab") as f:
            f.write(b'{"type":')
        s = a.readSession(p)
        self.assertEqual(len(s.toolCalls), before)
        self.assertTrue(any("trailing" in x for x in s.parseWarnings))

    def test_unmatched_call(self):
        p, a = self.fixture()
        self.append(p, {"type": "response_item", "payload": {"type": "function_call", "call_id": "pending", "name": "exec_command", "arguments": '{"cmd":"npm test"}'}})
        s = a.readSession(p)
        self.assertEqual(s.testRuns[-1]["status"], "UNCERTAIN")
        self.assertEqual(s.latestAgentState, "incomplete")

    def test_plan_is_not_completed(self):
        p, a = self.fixture()
        self.assertTrue(a.readSession(p).possibleTodos)
        self.assertTrue(all(t["status"] != "COMPLETED" for t in a.readSession(p).possibleTodos))

    def test_changed_file_evidence(self):
        p, a = self.fixture()
        (self.workspace / "registry.py").write_text("REGISTRY = {}\n")
        state = reconcile(a.readSession(p), self.workspace)
        self.assertEqual(state["files"][0]["path"], "registry.py")
        self.assertEqual(len(state["files"][0]["sha256"]), 64)

    def test_exact_write_completed_and_conflict_partial(self):
        for agent in ("codex", "claude"):
            p, a = self.fixture(agent)
            (self.workspace / "registry.py").write_bytes(b"REGISTRY = {}\n")
            self.assertEqual(reconcile(a.readSession(p), self.workspace)["work"][0]["status"], "COMPLETED")
            (self.workspace / "registry.py").write_bytes(b"REGISTRY = {'new': 1}\n")
            self.assertEqual(reconcile(a.readSession(p), self.workspace)["work"][0]["status"], "PARTIAL")

    def test_structured_pending_plan(self):
        p, a = self.fixture()
        self.append(p, {"type": "response_item", "payload": {"type": "function_call", "call_id": "plan", "name": "update_plan", "arguments": json.dumps({"plan": [{"step": "rollback", "status": "pending"}]})}})
        self.assertEqual(a.readSession(p).possibleTodos[-1]["status"], "NOT_STARTED")

    def test_mcp_stdio_unicode_and_bad_request(self):
        _, _ = self.fixture()
        requests = ["not-json", json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}), json.dumps({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})]
        cmd = [sys.executable, "-m", "agentref", "--data-dir", str(self.root / "mcp-data"), "--codex-root", str(self.sources), "mcp"]
        result = subprocess.run(cmd, input="\n".join(requests) + "\n", text=True, encoding="utf-8", capture_output=True, check=True)
        replies = [json.loads(x) for x in result.stdout.splitlines()]
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertEqual(len(replies[2]["result"]["resources"]), 1)

    def test_completed_tests(self):
        for agent in ("claude", "codex"):
            p, a = self.fixture(agent)
            self.assertEqual(a.readSession(p).testRuns[0]["status"], "COMPLETED")

    def test_failed_tests(self):
        p, a = self.fixture()
        p.write_text(p.read_text().replace('\\"exit_code\\":0', '\\"exit_code\\":1'))
        self.assertEqual(a.readSession(p).testRuns[0]["status"], "FAILED")

    def test_workspace_differs(self):
        p, a = self.fixture()
        self.assertIn("current workspace differs from source session", reconcile(a.readSession(p), self.workspace)["warnings"])

    def test_dirty_git(self):
        subprocess.run(["git", "init", "-q", str(self.workspace)], check=True)
        (self.workspace / "dirty.txt").write_text("new")
        state = reconcile(SessionIR("codex"), self.workspace)
        self.assertIn("dirty.txt", state["git"]["status"]["output"])

    def test_duplicate_titles_need_picker(self):
        p, a = self.fixture()
        shutil.copyfile(p, self.sources / "duplicate.jsonl")
        idx = self.index(a)
        idx.refresh()
        rows = idx.matches("Implement registry")
        self.assertEqual(len(rows), 2)
        with patch("sys.stdin.isatty", return_value=False), patch("sys.stderr", io.StringIO()):
            with self.assertRaisesRegex(ValueError, "Ambiguous"):
                select(rows)

    def test_missing_workspace(self):
        self.assertIn("workspace missing", reconcile(SessionIR("claude"), self.workspace / "missing")["warnings"])

    def test_unknown_fields(self):
        p, a = self.fixture()
        self.append(p, {"type": "future_record", "extra": {"nested": True}})
        s = a.readSession(p)
        self.assertIn("future_record", s.unknownTypes)
        self.assertTrue(s.originalGoal)

    def test_appended_partial_record_retried(self):
        p, a = self.fixture()
        with p.open("ab") as f:
            f.write(b'{"type":"event_msg","payload":')
        _, offset, warnings = read_jsonl(p)
        self.assertTrue(warnings)
        with p.open("ab") as f:
            f.write(b'{"type":"turn_aborted"}}\n')
        records, end, _ = a.readSessionIncrementally(p, offset)
        self.assertEqual(len(records), 1)
        self.assertEqual(end, p.stat().st_size)

    def test_incremental_index(self):
        p, a = self.fixture()
        idx = self.index(a)
        first = idx.refresh()
        self.assertGreater(first["bytesRead"], 0)
        self.assertEqual(idx.refresh()["bytesRead"], 0)
        self.append(p, {"type": "event_msg", "payload": {"type": "turn_aborted"}})
        change = idx.refresh()
        self.assertLess(change["bytesRead"], first["bytesRead"])
        self.assertEqual(idx.sessions()[0]["latestAgentState"], "interrupted")
        cols = {r[1] for r in idx.db.execute("PRAGMA table_info(sessions)")}
        self.assertFalse(cols & {"messages", "transcript", "toolCalls", "output"})

    def test_truncation_reindexes(self):
        p, a = self.fixture()
        idx = self.index(a)
        idx.refresh()
        p.write_text('{"type":"session_meta","payload":{"id":"replacement"}}\n')
        idx.refresh()
        self.assertEqual(idx.sessions()[0]["sessionId"], "replacement")

    def test_no_workspace_implicit_reads(self):
        with patch("agentref.handoff.git", side_effect=AssertionError("must not run")):
            state = reconcile(SessionIR("codex", cwd=str(self.workspace)))
        self.assertFalse(state["files"])

    def test_path_and_secret_boundaries(self):
        self.assertIsNone(safe_file(self.workspace, "../secret"))
        self.assertIsNone(safe_file(self.workspace, ".env.local"))
        self.assertIsNone(safe_file(self.workspace, ".ssh/id_rsa"))
        try:
            (self.workspace / "escape").symlink_to(self.root, target_is_directory=True)
        except OSError:
            return
        self.assertIsNone(safe_file(self.workspace, "escape/outside.txt"))

    def test_foreign_session_immutable(self):
        p, a = self.fixture()
        before = p.read_bytes()
        idx = self.index(a)
        idx.refresh()
        build_context(idx.read(idx.sessions()[0]), self.workspace)
        self.assertEqual(before, p.read_bytes())

    def test_mcp_roundtrip(self):
        p, a = self.fixture()
        server = Server(self.index(a), self.workspace)
        resources = server.dispatch("resources/list", {})["resources"]
        out = server.dispatch("resources/read", {"uri": resources[0]["uri"]})
        self.assertIn("Original Goal", out["contents"][0]["text"])
        self.assertTrue(server.dispatch("tools/call", {"name": "context", "arguments": {"ref": "../../credentials"}})["isError"])
        sink = io.StringIO()
        server.serve(io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}\n'), sink)
        self.assertEqual(json.loads(sink.getvalue())["result"]["protocolVersion"], "2024-11-05")

    def test_cli_subprocess(self):
        p, _ = self.fixture()
        cmd = [sys.executable, "-m", "agentref", "--data-dir", str(self.root / "cli-data"), "--codex-root", str(self.sources)]
        result = subprocess.run(cmd + ["sessions", "--json"], capture_output=True, text=True, check=True)
        self.assertEqual(len(json.loads(result.stdout)), 1)
        result = subprocess.run(cmd + ["context", "codex-demo", "--workspace", str(self.workspace)], capture_output=True, text=True, check=True)
        self.assertIn("Continuation Policy", result.stdout)

    def test_index_cannot_write_foreign_root(self):
        _, a = self.fixture()
        with self.assertRaises(ValueError):
            Index(self.sources / "data", [a])


if __name__ == "__main__":
    unittest.main()
