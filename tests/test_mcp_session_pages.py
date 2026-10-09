"""Older session discovery stays bounded and metadata-only over actual RPC."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agentref.adapters import ClaudeAdapter, CodexAdapter
from agentref.index import Index
from agentref.mcp import Server


class McpSessionPageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.index = Index(Path(temporary.name), [ClaudeAdapter([]), CodexAdapter([])])
        self.addCleanup(self.index.close)
        self.index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            (f"{agent}:{number:016x}", agent, f"{agent}-session-{number}",
             "Older needle" if number == 0 else f"Task {number}", "/synthetic/project", "", "",
             f"synthetic-{agent}-{number}", "incomplete", number, 0, 0, "", 0)
            for agent, count in (("claude", 140), ("codex", 30)) for number in range(count)))
        self.index.db.commit()
        self.server = Server(self.index)
        # These rows are generated metadata without source transcripts. Do not
        # rescan nonexistent source files or create any personal source defaults.
        self.refresh = patch.object(self.index, "refresh", return_value={"errors": []})
        self.refresh.start()
        self.addCleanup(self.refresh.stop)
        no_read = patch.object(self.index, "read", side_effect=AssertionError("metadata request read context"))
        no_read.start()
        self.addCleanup(no_read.stop)

    def call(self, **arguments):
        request = {"jsonrpc": "2.0", "id": "list", "method": "tools/call",
                   "params": {"name": "sessions", "arguments": arguments}}
        sink = io.StringIO()
        self.server.serve(io.StringIO(json.dumps(request) + "\n"), sink)
        return json.loads(sink.getvalue())["result"]

    def test_default_page_matches_full_reference_but_materializes_only_fifty_rows(self):
        expected = self.index.sessions("claude")[:50]
        statements, materialized = [], []
        self.index.db.set_trace_callback(statements.append)
        overlay = self.index._overlay_metadata
        def observe(rows, **kwargs):
            materialized.append(len(rows))
            return overlay(rows, **kwargs)
        with patch.object(self.index, "_overlay_metadata", side_effect=observe):
            result = self.call(agent="claude")
        actual = json.loads(result["content"][0]["text"])
        self.assertEqual([row["ref"] for row in actual], [row["ref"] for row in expected])
        self.assertEqual(materialized, [50])
        self.assertTrue(any("LIMIT 50 OFFSET 0" in sql for sql in statements))
        self.assertEqual(result["_meta"]["pagination"]["nextOffset"], 50)
        self.assertEqual(json.loads(result["content"][1]["text"])["pagination"]["total"], 140)

    def test_all_pages_preserve_order_without_duplicates_or_omissions(self):
        expected = [row["ref"] for row in self.index.sessions("claude")]
        actual, offset = [], 0
        while True:
            result = self.call(agent="claude", limit=37, offset=offset)
            actual.extend(row["ref"] for row in json.loads(result["content"][0]["text"]))
            page = result["_meta"]["pagination"]
            self.assertEqual(page["total"], 140)
            if not page["hasMore"]:
                self.assertNotIn("nextOffset", page)
                break
            self.assertGreater(page["nextOffset"], offset)
            offset = page["nextOffset"]
        self.assertEqual(actual, expected)
        self.assertEqual(len(set(actual)), 140)

    def test_keyword_finds_a_session_outside_default_page_and_respects_source(self):
        first = json.loads(self.call(agent="claude")["content"][0]["text"])
        result = self.call(agent="claude", query="older NEEDLE")
        rows = json.loads(result["content"][0]["text"])
        self.assertEqual([row["ref"] for row in rows], ["claude:0000000000000000"])
        self.assertNotIn(rows[0]["ref"], [row["ref"] for row in first])
        self.assertEqual(result["_meta"]["pagination"]["total"], 1)
        self.assertFalse(result["_meta"]["pagination"]["hasMore"])
        rejected = self.call(agent="claude", query="codex:Older needle")
        self.assertEqual(json.loads(rejected["content"][0]["text"]), [])
        self.assertEqual(rejected["_meta"]["pagination"]["total"], 0)

    def test_invalid_page_arguments_fail_before_index_access_and_stdio_survives(self):
        invalid = [{"limit": value} for value in (True, "10", 0, -1, 101, 1.5, None)]
        invalid += [{"offset": value} for value in (False, "0", -1, 1000001, 2**63, None)]
        invalid += [{"query": "x" * 121}]
        requests = [{"jsonrpc": "2.0", "id": number, "method": "tools/call",
                     "params": {"name": "sessions", "arguments": args}}
                    for number, args in enumerate(invalid)]
        requests.append({"jsonrpc": "2.0", "id": "alive", "method": "ping"})
        sink = io.StringIO()
        with patch.object(self.index, "refresh", side_effect=AssertionError("invalid page indexed")):
            self.server.serve(io.StringIO("".join(json.dumps(row) + "\n" for row in requests)), sink)
        replies = [json.loads(line) for line in sink.getvalue().splitlines()]
        self.assertTrue(all(reply["result"]["isError"] for reply in replies[:-1]))
        self.assertEqual(replies[-1]["result"], {})

    def test_empty_late_page_and_partial_index_report_their_boundaries(self):
        with patch.object(self.index, "refresh", return_value={"errors": ["source unavailable"]}):
            result = self.call(agent="claude", offset=200)
        self.assertEqual(json.loads(result["content"][0]["text"]), [])
        self.assertFalse(result["_meta"]["pagination"]["hasMore"])
        self.assertEqual(result["_meta"]["pagination"]["total"], 140)
        self.assertTrue(json.loads(result["content"][-1]["text"])["indexIncomplete"])
