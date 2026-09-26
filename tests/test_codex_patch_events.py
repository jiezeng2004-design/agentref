"""Synthetic sideband events; no copied real transcripts or host execution."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agentref.adapters import CodexAdapter
from agentref.evidence import file_history
from agentref.handoff import reconcile
from agentref.index import Index


def event(changes=None, **overrides):
    return {"type": "event_msg", "payload": {"type": "patch_apply_end", "call_id": "patch-one",
        "turn_id": "turn-one", "success": True, "status": "completed",
        "changes": changes if changes is not None else {"example.py": {"type": "add", "content": "VALUE = 1\n"}},
        **overrides}}


class CodexPatchEventTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.path = self.source / "synthetic.jsonl"
        self.adapter = CodexAdapter([self.source])

    def write(self, *records):
        data = [{"type": "session_meta", "payload": {"id": "synthetic-source", "cwd": str(self.workspace)}},
                {"type": "response_item", "payload": {"type": "message", "role": "user", "content": "Implement example"}}, *records]
        self.path.write_text("".join(json.dumps(row) + "\n" for row in data), encoding="utf-8")
        before = self.path.read_bytes()
        session = self.adapter.readSession(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        return session

    def test_successful_add_has_exact_hash_and_requires_workspace_reconciliation(self):
        for content in ("VALUE = 1\n", "VALUE = 1", "标签 = '中文'\r\n", ""):
            session = self.write(event({"example.py": {"type": "add", "content": content}}))
            operation = session.fileOperations[0]
            self.assertEqual(operation["expectedSha256"], hashlib.sha256(content.encode()).hexdigest())
            self.assertEqual(operation["status"], "COMPLETED")
            self.assertFalse(session.parseWarnings)
            (self.workspace / "example.py").write_bytes(content.encode())
            self.assertEqual(reconcile(session, self.workspace)["work"][0]["status"], "COMPLETED")
            (self.workspace / "example.py").write_text("USER_CHANGED\n", encoding="utf-8")
            self.assertEqual(reconcile(session, self.workspace)["work"][0]["status"], "PARTIAL")

    def test_failed_add_never_supplies_a_completion_hash(self):
        session = self.write(event(success=False, status="failed"))
        self.assertEqual(session.fileOperations[0]["status"], "FAILED")
        self.assertNotIn("expectedSha256", session.fileOperations[0])

    def test_identical_duplicate_is_not_counted_twice(self):
        session = self.write(event(), event())
        self.assertEqual(len(session.fileOperations), 1)
        self.assertFalse(session.parseWarnings)

    def test_conflicting_duplicate_never_picks_the_optimistic_outcome(self):
        for first, second in ((event(), event(success=False, status="failed")),
                              (event(success=False, status="failed"), event()),
                              (event(), event({"example.py": {"type": "add", "content": "different"}}))):
            session = self.write(first, second, first)
            self.assertTrue(session.parseWarnings)
            self.assertEqual(session.fileOperations[0]["status"], "UNCERTAIN")
            self.assertNotIn("expectedSha256", session.fileOperations[0])

    def test_unsupported_shapes_and_changes_warn_instead_of_claiming_completion(self):
        for overrides in ({"success": "true"}, {"status": "in_progress"}, {"call_id": None},
                          {"turn_id": []}, {"changes": []}, {"changes": {"example.py": {"type": "update"}}},
                          {"changes": {"example.py": {"type": "add", "content": []}}}):
            session = self.write(event(**overrides))
            self.assertTrue(session.parseWarnings, overrides)
            self.assertEqual(session.fileOperations, [])

    def test_mixed_changes_preserve_known_add_but_keep_warning(self):
        session = self.write(event({"example.py": {"type": "add", "content": "known"},
                                    "other.py": {"type": "future-v99"}}))
        self.assertEqual([x["path"] for x in session.fileOperations], ["example.py"])
        self.assertTrue(session.parseWarnings)

    def direct(self, success=True):
        patch = "*** Begin Patch\n*** Add File: example.py\n+VALUE = 1\n*** End Patch"
        return [{"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "patch-one",
                    "name": "apply_patch", "input": patch}},
                {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "patch-one",
                    "output": "Success. Updated file" if success else "Error: write failed"}}]

    def test_direct_call_and_matching_event_collapse_with_provenance(self):
        session = self.write(*self.direct(), event())
        self.assertEqual(len(session.fileOperations), 1)
        self.assertEqual(session.fileOperations[0]["status"], "COMPLETED")
        self.assertIn("structured patch_apply_end add-file event", session.fileOperations[0]["evidence"])
        self.assertFalse(session.parseWarnings)

    def test_conflicting_direct_result_does_not_become_completed(self):
        session = self.write(*self.direct(False), event())
        self.assertTrue(session.parseWarnings)
        self.assertTrue(all(x["status"] == "UNCERTAIN" for x in session.fileOperations))
        self.assertTrue(all("expectedSha256" not in x for x in session.fileOperations))

    def test_duplicate_completion_does_not_reorder_intervening_writes(self):
        later = event({"example.py": {"type": "add", "content": "VALUE = 2\n"}}, call_id="patch-two")
        session = self.write(*self.direct(), later, event())
        history = file_history(session.fileOperations)
        self.assertEqual(history[0]["supersededBy"], 1)
        self.assertEqual(history[1]["expectedSha256"], hashlib.sha256(b"VALUE = 2\n").hexdigest())

    def test_call_time_cwd_and_unknown_exec_are_not_reinterpreted(self):
        session = self.write({"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "opaque",
                "name": "exec", "input": "untrusted JavaScript; do not evaluate"}}, event(),
            {"type": "turn_context", "payload": {"cwd": str(self.root / "different")}},
            {"type": "event_msg", "payload": {"type": "turn_complete"}})
        self.assertEqual(session.fileOperations[0]["cwd"], str(self.workspace))
        self.assertEqual(session.toolCalls[0]["status"], "UNCERTAIN")
        self.assertEqual(session.commands, [])
        self.assertEqual(session.latestAgentState, "incomplete")  # unresolved opaque call

    def test_new_index_has_no_warning_or_persisted_body_for_known_event(self):
        session = self.write(event({"example.py": {"type": "add", "content": "PRIVATE_SYNTHETIC_SENTINEL"}}),
                             {"type": "event_msg", "payload": {"type": "turn_complete"}})
        with_index = Index(self.root / "index", [self.adapter])
        try:
            self.assertFalse(with_index.refresh()["errors"])
            self.assertFalse(with_index.refresh()["errors"])
            self.assertEqual(session.latestAgentState, "turn-ended")
            self.assertNotIn("PRIVATE_SYNTHETIC_SENTINEL", json.dumps(with_index.sessions()))
            self.assertNotIn("PRIVATE_SYNTHETIC_SENTINEL", "\n".join(with_index.db.iterdump()))
        finally:
            with_index.close()

    def test_old_warning_cache_is_rechecked_once_without_changing_source(self):
        self.write(event())
        before = self.path.read_bytes()
        index = Index(self.root / "index", [self.adapter])
        index.refresh()
        with index.db:
            index.db.execute("UPDATE sessions SET warnings=1")
            index.db.execute("PRAGMA user_version=1")
        index.close()
        index = Index(self.root / "index", [self.adapter])
        try:
            self.assertEqual(index.refresh()["changed"], 1)
            self.assertFalse(index.refresh()["errors"])
            self.assertEqual(index.refresh()["changed"], 0)
            self.assertEqual(index.db.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(self.path.read_bytes(), before)
        finally:
            index.close()

    def test_migration_preserves_healthy_codex_and_other_source_rows(self):
        self.write(event())
        index = Index(self.root / "index", [self.adapter])
        index.refresh()
        with index.db:
            row = index.db.execute("SELECT * FROM sessions").fetchone()
            values = list(row)
            values[0], values[1], values[7], values[13] = "claude:synthetic", "claude", "synthetic-foreign-path", 1
            index.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
            index.db.execute("PRAGMA user_version=1")
        before = [tuple(r) for r in index.db.execute("SELECT * FROM sessions ORDER BY ref")]
        index.close()
        index = Index(self.root / "index", [self.adapter])
        try:
            self.assertEqual([tuple(r) for r in index.db.execute("SELECT * FROM sessions ORDER BY ref")], before)
            self.assertEqual(index.refresh()["changed"], 0)
            self.assertIsNotNone(index.db.execute("SELECT 1 FROM sessions WHERE agent='claude'").fetchone())
        finally:
            index.close()

    def test_other_tool_with_same_id_is_not_reclassified_as_patch(self):
        records = [{"type": "response_item", "payload": {"type": "function_call", "call_id": "patch-one",
                    "name": "Write", "arguments": json.dumps({"file_path": "example.py", "content": "VALUE = 1\n"})}},
                   {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "patch-one", "output": "Success"}}]
        session = self.write(*records, event())
        self.assertEqual(len(session.fileOperations), 2)

    def test_unknown_event_still_reaches_warm_metadata_diagnostics(self):
        self.write(event({"example.py": {"type": "update", "future": True}}))
        index = Index(self.root / "index", [self.adapter])
        try:
            self.assertTrue(index.refresh()["errors"])
            self.assertTrue(index.refresh()["errors"])
        finally:
            index.close()


if __name__ == "__main__":
    unittest.main()
