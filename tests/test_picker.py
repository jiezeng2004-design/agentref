import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch
from agentref.adapters import CodexAdapter
from agentref.index import Index
from agentref.mcp import Server


class PickerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / "source"
        source.mkdir()
        (source / "demo.jsonl").write_text('{"type":"session_meta","payload":{"id":"demo"}}\n{"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"demo task"}]}}\n', encoding="utf-8")
        self.index = Index(self.root / "data", [CodexAdapter([source])])
        self.addCleanup(self.index.close)
        self.index.refresh()
        self.server = Server(self.index, agent="codex", workspace_roots=[self.root])

    def test_fallback_does_not_read_transcript(self):
        result = json.loads(self.server.picker({}))
        self.assertTrue(result["selectionRequired"])
        self.assertEqual(len(result["sessions"]), 1)

    def test_native_form_selection(self):
        self.server.native_picker = True
        row = self.index.sessions()[0]
        label = f"1. {row['title']} | {row['cwd']} | {row['updatedAt']} | {row['latestAgentState']}"
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {"elicitation": {"form": {}}}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "pick_session", "arguments": {"workspace": str(self.root)}}},
            {"jsonrpc": "2.0", "id": "agentref-pick-1", "result": {"action": "accept", "content": {"session": label}}},
        ]
        sink = io.StringIO()
        self.server.serve(io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n"), sink)
        replies = [json.loads(x) for x in sink.getvalue().splitlines()]
        self.assertEqual(replies[1]["method"], "elicitation/create")
        self.assertIn("Original Goal", replies[2]["result"]["content"][0]["text"])

    def test_cancel_reads_no_session(self):
        self.server.native_picker = True
        self.server.client_capabilities = {"elicitation": {}}
        self.server.source = iter([json.dumps({"id": "agentref-pick-1", "result": {"action": "cancel"}})])
        self.server.sink = io.StringIO()
        self.index.read = lambda row: self.fail("must not read cancelled session")
        self.assertIn("取消", self.server.picker({}))

    def test_workspace_allowlist(self):
        ref = self.index.sessions()[0]["ref"]
        with self.assertRaises(ValueError):
            self.server.context(ref, str(self.root.parent))
        self.assertIn("Current Git State", self.server.context(ref, str(self.root)))

    def test_agent_filter(self):
        with self.assertRaises(ValueError):
            self.server.rows("claude")

    def test_unique_title_and_id_prefix_read_context(self):
        for query in ("task", "dem", "  DEM  "):
            with self.subTest(query=query):
                self.assertIn("Original Goal", self.server.picker({"query": query}))

    def test_unique_project_name(self):
        self.index.db.execute("UPDATE sessions SET cwd=?", (str(self.root / "billing-app"),))
        self.index.db.commit()
        self.assertIn("Original Goal", self.server.picker({"query": "billing"}))

    def test_ambiguous_and_missing_queries_do_not_read(self):
        self.index.read = lambda row: self.fail("must not read an unselected session")
        self.assertIn("没有匹配", self.server.picker({"query": "missing-session"}))
        source = self.root / "source"
        (source / "second.jsonl").write_text((source / "demo.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
        result = json.loads(self.server.picker({"query": "task"}))
        self.assertTrue(result["selectionRequired"])
        self.assertEqual(len(result["sessions"]), 2)

    def test_picker_requests_only_enough_rows_to_detect_ambiguity(self):
        source = self.root / "source"
        (source / "second.jsonl").write_text((source / "demo.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
        self.index.refresh()
        with patch.object(self.index, "matches", wraps=self.index.matches) as matches:
            result = json.loads(self.server.picker({"query": "task"}))
        self.assertTrue(result["selectionRequired"])
        self.assertEqual(len(result["sessions"]), 2)
        matches.assert_any_call("task", "codex", limit=31, offset=0, include_total=False)

    def test_bare_agent_and_whitespace_still_require_selection(self):
        for query in (" ", "@codex", "codex"):
            self.assertTrue(json.loads(self.server.picker({"query": query}))["selectionRequired"])

    def test_unique_query_preserves_workspace_boundary(self):
        with self.assertRaises(ValueError):
            self.server.picker({"query": "task", "workspace": str(self.root.parent)})

    def test_qualified_query_cannot_escape_agent(self):
        self.index.matches = lambda query, agent: [{"agent": "claude"}]
        self.assertEqual(self.server.rows(query="claude:abc"), [])

    def test_url_only_does_not_receive_form(self):
        self.server.client_capabilities = {"elicitation": {"url": {}}}
        self.assertTrue(json.loads(self.server.picker({}))["selectionRequired"])

    def test_default_never_opens_broken_desktop_form(self):
        self.server.client_capabilities = {"elicitation": {"form": {}}}
        self.server.source = iter([])
        self.server.sink = io.StringIO()
        self.assertTrue(json.loads(self.server.picker({}))["selectionRequired"])
        self.assertEqual(self.server.sink.getvalue(), "")

    def test_form_error_is_not_user_cancellation(self):
        self.server.native_picker = True
        self.server.client_capabilities = {"elicitation": {}}
        self.server.source = iter([json.dumps({"id": "agentref-pick-1", "error": {"code": -32601}})])
        self.server.sink = io.StringIO()
        self.assertEqual(json.loads(self.server.picker({}))["reason"], "client_form_error")
