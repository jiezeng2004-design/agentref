"""Failure isolation and continuation regressions using synthetic data only."""
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentref.adapters import ClaudeAdapter
from agentref.core import SessionIR
from agentref.handoff import FILE_LIMIT, build_context, reconcile, recent_conversation
from agentref.index import Index
from agentref.mcp import Server
from agentref.mentions import session_time


class StabilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        shutil.copyfile(Path(__file__).parent / "fixtures/claude-normal.jsonl", self.source / "session.jsonl")
        self.index = Index(self.root / "index", [ClaudeAdapter([self.source])])
        self.addCleanup(self.index.close)
        self.server = Server(self.index, workspace=str(self.root))

    def test_malformed_tool_requests_do_not_stop_stdio(self):
        invalid = [
            {"name": "pick_session", "arguments": {"query": 7}},
            {"name": "context", "arguments": {"ref": "example", "workspace": []}},
            {"name": "sessions", "arguments": ["claude"]},
            {"name": "sessions", "arguments": False},
            {"name": "sessions", "arguments": None},
            {"name": "search_mentions", "arguments": {"path": [7]}},
            {"name": "context", "arguments": {}},
            {"name": "sessions", "arguments": {"unexpected": "ignored?"}},
        ]
        requests = [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": p}
                    for i, p in enumerate(invalid)]
        requests.append({"jsonrpc": "2.0", "id": "alive", "method": "ping"})
        sink = io.StringIO()
        self.server.serve(io.StringIO("\n".join(json.dumps(r) for r in requests)), sink)
        replies = [json.loads(line) for line in sink.getvalue().splitlines()]
        self.assertEqual(len(replies), len(requests))
        self.assertTrue(all(r["result"]["isError"] for r in replies[:-1]))
        self.assertEqual(replies[-1]["result"], {})

    def test_bad_protocol_shapes_do_not_stop_stdio(self):
        invalid = [("initialize", {"capabilities": []}),
                   ("completion/complete", {"ref": [], "argument": {}}),
                   ("resources/read", {"uri": []}), ("ping", False)]
        requests = [{"jsonrpc": "2.0", "id": i, "method": method, "params": params}
                    for i, (method, params) in enumerate(invalid)]
        requests.append({"jsonrpc": "2.0", "id": "alive", "method": "ping"})
        sink = io.StringIO()
        self.server.serve(io.StringIO("\n".join(json.dumps(r) for r in requests)), sink)
        replies = [json.loads(line) for line in sink.getvalue().splitlines()]
        self.assertTrue(all("error" in r for r in replies[:-1]))
        self.assertEqual(replies[-1]["result"], {})

    def test_bad_source_times_have_stable_fallback(self):
        for value in (None, 7, [], {}, "invalid"):
            self.assertEqual(session_time({"updatedAt": value, "createdAt": value, "mtime": value}).timestamp(), 0)

    def test_fixed_workspace_string_is_accepted(self):
        self.index.refresh()
        ref = self.index.sessions()[0]["ref"]
        self.assertIn("Current Git State", self.server.context(ref, str(self.root)))

    def test_recent_context_keeps_latest_reply_after_large_earlier_turn(self):
        messages = [{"role": "assistant", "text": "x" * 9000}]
        messages += [{"role": "user", "text": "Continue rollback"},
                     {"role": "assistant", "text": "PRESERVE_REGISTRY" + "x" * 9000 + "NEXT_ROLLBACK_TEST"}]
        context = build_context(SessionIR("claude", messages=messages))
        recent = context.split("## Relevant Recent Conversation\n")[1]
        decoded = json.loads(recent)
        self.assertEqual(len(decoded["messages"]), 3)
        self.assertIn("Continue rollback", recent)
        self.assertIn("PRESERVE_REGISTRY", recent)
        self.assertIn("NEXT_ROLLBACK_TEST", recent)
        self.assertLessEqual(len(recent.strip()), 5000)

    def test_recent_context_is_valid_json_with_escape_expansion(self):
        messages = [{"role": "assistant", "text": "\x01" * 9000} for _ in range(12)]
        recent = recent_conversation(messages)
        self.assertLessEqual(len(recent), 5000)
        self.assertEqual(json.loads(recent)["olderMessagesOmitted"], 4)

    def test_unreadable_file_does_not_hide_other_work(self):
        session = SessionIR("claude", fileOperations=[
            {"path": name, "task": "Write " + name, "status": "COMPLETED", "evidence": []}
            for name in ("blocked.py", "good.py")])
        for name in ("blocked.py", "good.py"):
            (self.root / name).write_text("data")
        original = Path.open
        def selective_open(path, *args, **kwargs):
            if path.name == "blocked.py":
                raise PermissionError("synthetic locked file")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", selective_open):
            state = reconcile(session, self.root)
        self.assertEqual(state["work"][0]["status"], "UNCERTAIN")
        self.assertIn("PermissionError", state["work"][0]["evidence"][-1])
        self.assertEqual([f["path"] for f in state["files"]], ["good.py"])

    def test_file_growing_after_stat_is_bounded(self):
        target = self.root / "growing.py"
        target.write_text("small")
        session = SessionIR("claude", fileOperations=[
            {"path": target.name, "task": "Write", "status": "COMPLETED", "evidence": []}])
        with patch.object(Path, "open", return_value=io.BytesIO(b"x" * (FILE_LIMIT + 10))):
            state = reconcile(session, self.root)
        self.assertEqual(state["files"], [])
        self.assertIn("exceeds inspection limit", state["work"][0]["evidence"][-1])

    def test_native_selection_carries_continuation_policy_without_workspace(self):
        server = Server(self.index, agent="claude")
        uri = server.mention_items({"query": ""})["items"][0]["resourceUri"]
        context = server.dispatch("resources/read", {"uri": uri})["contents"][0]["text"]
        self.assertIn("Receiving Task", context)
        self.assertIn("Do not stop at a summary or reopen the picker", context)
        self.assertIn("workspace not explicitly supplied", context)
        self.assertIn("rollback", context)


if __name__ == "__main__":
    unittest.main()
