import json
import hashlib
import unittest
from unittest.mock import patch

from agentref.adapters.base import BaseAdapter
from agentref.core import SessionIR
from agentref.context_render import CONTEXT_LIMIT, bounded_json
from agentref.evidence import command_history, file_history, continuation_candidates
from agentref.handoff import build_context, reconcile, recent_decisions
from scripts.check_context_render import check as check_context_render
from scripts.check_evidence_history import check as check_evidence_history
import test_stability


class EvidenceTests(unittest.TestCase):
    def test_retry_success_retains_failure_but_not_as_pending_work(self):
        session = SessionIR("claude", commands=[
            {"task": "python -m unittest", "cwd": "/project", "status": status, "evidence": []}
            for status in ("FAILED", "COMPLETED")])
        before = session.to_dict()
        state = reconcile(session)
        self.assertEqual(state["superseded"][0]["status"], "FAILED")
        self.assertEqual(state["commands"][0]["supersededBy"], 1)
        self.assertEqual(continuation_candidates(state["work"])["candidates"], [])
        self.assertEqual(before, session.to_dict())

    def test_retry_does_not_cross_unknown_or_different_workspaces(self):
        for first_cwd in (None, "/other", []):
            history = command_history([
                {"task": "pytest", "cwd": first_cwd, "status": "FAILED"},
                {"task": "pytest", "cwd": "/project", "status": "COMPLETED"}])
            self.assertNotIn("supersededBy", history[0])

    def test_later_failure_is_not_hidden_by_earlier_success(self):
        history = command_history([{"task": "pytest", "cwd": "/project", "status": status}
                                   for status in ("FAILED", "COMPLETED", "FAILED")])
        self.assertEqual(history[0]["supersededBy"], 1)
        self.assertNotIn("supersededBy", history[-1])

    def test_readonly_history_view_preserves_input_and_copies_annotations(self):
        items = [
            {"task": "pytest", "cwd": "/project", "status": "FAILED", "evidence": ["failure"]},
            {"task": "pytest", "cwd": "/project", "status": "COMPLETED", "evidence": ["success"]},
            {"task": "lint", "cwd": "/project", "status": "UNCERTAIN", "evidence": ["pending"]},
        ]
        before = [dict(item, evidence=list(item["evidence"])) for item in items]
        view = command_history(items, copy_evidence=False)
        self.assertEqual(items, before)
        self.assertEqual(view[0]["supersededBy"], 1)
        self.assertIsNot(view[0]["evidence"], items[0]["evidence"])
        self.assertIs(view[2]["evidence"], items[2]["evidence"])
        isolated = command_history(items)
        self.assertIsNot(isolated[2]["evidence"], items[2]["evidence"])

    def test_only_successful_full_write_supersedes_file_history(self):
        original = {"task": "Write", "path": "a.py", "cwd": "/project", "status": "COMPLETED", "expectedSha256": "old", "evidence": []}
        for later in ({"status": "FAILED", "expectedSha256": "new"}, {"status": "COMPLETED"}):
            result = file_history([original, {"path": "a.py", "cwd": "/project", **later}])
            self.assertNotIn("supersededBy", result[0])
        result = file_history([original, dict(original, expectedSha256="new")])
        self.assertEqual(result[0]["supersededBy"], 1)

    def test_working_directory_changes_do_not_merge_unrelated_operations(self):
        adapter = BaseAdapter([])
        session = SessionIR("codex", cwd="/first")
        for i, cwd in enumerate(("/first", "/second")):
            session.cwd = cwd
            adapter.call(session, f"c{i}", "exec_command", {"cmd": "pytest"})
            adapter.result(session, f"c{i}", f"Exit code: {1-i}")
            adapter.call(session, f"w{i}", "Write", {"file_path": "a.py", "content": str(i)})
            adapter.result(session, f"w{i}", "File created successfully")
        adapter.finish(session)
        self.assertEqual([x["cwd"] for x in session.commands], ["/first", "/second"])
        self.assertNotIn("supersededBy", command_history(session.commands)[0])
        self.assertNotIn("supersededBy", file_history(session.fileOperations)[0])

    def test_unknown_file_workspaces_cannot_establish_replacement(self):
        ops = [{"path": "a.py", "status": "COMPLETED", "expectedSha256": str(i)} for i in range(2)]
        self.assertNotIn("supersededBy", file_history(ops)[0])

    def test_confirmed_completed_plan_not_recommended_or_claimed_verified(self):
        adapter = BaseAdapter([])
        session = SessionIR("codex")
        for i, status in enumerate(("pending", "completed")):
            adapter.call(session, str(i), "update_plan", {"plan": [{"step": "registry", "status": status}]})
            adapter.result(session, str(i), "Plan updated")
        adapter.finish(session)
        self.assertEqual(session.possibleTodos[0]["status"], "UNCERTAIN")
        self.assertEqual(continuation_candidates(reconcile(session)["work"])["candidates"], [])

    def test_unconfirmed_completed_plan_still_requires_attention(self):
        adapter = BaseAdapter([])
        session = SessionIR("codex")
        adapter.call(session, "p", "update_plan", {"plan": [{"step": "registry", "status": "completed"}]})
        adapter.finish(session)
        self.assertIn("registry", continuation_candidates(reconcile(session)["work"])["candidates"])

    def test_explicit_pending_plan_beats_many_old_opaque_calls(self):
        work = [{"task": f"old call {i}", "status": "UNCERTAIN"} for i in range(100)]
        work.append({"task": "finish rollback", "status": "NOT_STARTED"})
        result = continuation_candidates(work)
        self.assertEqual(result["candidates"][0], "finish rollback")
        self.assertEqual(result["omittedCandidates"], 89)

    def test_candidate_top_k_matches_full_sort_for_duplicate_tasks_and_statuses(self):
        work = [{"task": f"task-{i % 73}", "status": ("NOT_STARTED", "PARTIAL", "FAILED", "UNCERTAIN")[i % 4],
                 **({"supersededBy": i + 1} if i % 11 == 0 else {}),
                 **({"planStatus": "completed"} if i % 17 == 0 else {})}
                for i in range(1000)]
        candidates = [item for item in work if item["status"] != "COMPLETED"
                      and "supersededBy" not in item and item.get("planStatus") != "completed"]
        priorities = {"NOT_STARTED": 0, "PARTIAL": 1, "FAILED": 2, "UNCERTAIN": 3}
        ordered = sorted(enumerate(candidates), key=lambda pair: (priorities[pair[1]["status"]], -pair[0]))
        expected = list(dict.fromkeys(item["task"] for _, item in ordered))
        result = continuation_candidates(work, limit=12)
        self.assertEqual(result["candidates"], expected[:12])
        self.assertEqual(result["omittedCandidates"], max(0, len(expected) - 12))
        self.assertEqual(continuation_candidates(iter(work), limit=12), result)

    def test_large_context_keeps_current_goal_latest_evidence_and_budget(self):
        session = SessionIR("codex", originalGoal="GOAL_START" + "g" * 20000 + "GOAL_END",
                            latestUserRequest="LATEST_START" + "u" * 20000 + "LATEST_END")
        session.commands = [{"task": f"command-{i}", "status": "FAILED", "evidence": [], "output": "x" * 5000} for i in range(100)]
        session.possibleTodos = [{"task": "finish rollback", "status": "NOT_STARTED", "evidence": []}]
        session.messages = [{"role": "assistant", "text": "RECENT_START" + "z" * 10000 + "RECENT_END"}]
        context = build_context(session)
        for marker in ("GOAL_START", "GOAL_END", "LATEST_START", "LATEST_END", "finish rollback", "command-99", "RECENT_END"):
            self.assertIn(marker, context)
        self.assertLessEqual(len(context), CONTEXT_LIMIT)
        self.assertLess(context.index("Recommended Continuation Point"), context.index("Commands Executed"))

    def test_recent_decisions_keeps_only_latest_eight_in_order(self):
        messages = [{"role": "assistant", "text": f"We decided option-{index}\r\nNo note"} for index in range(10000)]
        messages.insert(25, {"role": "user", "text": "This was chosen by user text"})
        decisions = recent_decisions(messages)
        self.assertEqual([item["claim"] for item in decisions],
                         [f"We decided option-{index}" for index in range(9992, 10000)])
        long_text = "ordinary\n" * 40000 + "We decided on the final path"
        self.assertEqual(recent_decisions([{"role": "assistant", "text": long_text}])[-1]["claim"],
                         "We decided on the final path")

    def test_json_budget_preserves_latest_entries_and_reports_omissions(self):
        rendered = bounded_json([{"task": f"task-{i}"} for i in range(100)], 500)
        value = json.loads(rendered)
        self.assertGreater(value["omittedOlderEntries"], 0)
        self.assertEqual(value["items"][-1]["task"], "task-99")
        self.assertLessEqual(len(rendered), 500)

    def test_json_budget_keeps_small_output_identical_and_bounds_large_newest_entry(self):
        small = [{"task": "old"}, {"task": "new", "detail": [1, 2]}]
        self.assertEqual(bounded_json(small, 2048), json.dumps(small, ensure_ascii=False, indent=2))
        rendered = bounded_json([{"task": "x" * 1_000_000}], 512)
        value = json.loads(rendered)
        self.assertLessEqual(len(rendered), 512)
        self.assertEqual(value["omittedOlderEntries"], 0)
        self.assertIn("TRUNCATED", value["items"][0]["excerpt"])

    def test_context_render_benchmark_matches_reference_shape(self):
        result = check_context_render(rows=100, limit=500, repeats=1)
        self.assertTrue(result["synthetic"])
        self.assertTrue(result["equivalent"])
        self.assertTrue(result["recentDecisions"]["equivalent"])

    def test_evidence_top_k_benchmark_matches_full_sort(self):
        result = check_evidence_history(records=100, unique_tasks=17, repeats=1, limit=5)
        self.assertTrue(result["synthetic"])
        self.assertTrue(result["equivalent"])

    def test_impossible_json_budget_fails_without_retry_loop(self):
        with self.assertRaises(ValueError):
            bounded_json(["x" * 1000], 20)


class IndexDiagnosticsTests(unittest.TestCase):
    # Reuse fixture setup without inheriting/re-running the stability test cases.
    setUp = test_stability.StabilityTests.setUp

    def test_relative_file_from_earlier_workspace_is_not_verified_here(self):
        (self.root / "a.py").write_bytes(b"same")
        session = SessionIR("codex", cwd=str(self.root), fileOperations=[{
            "path": "a.py", "cwd": str(self.root / "other"), "task": "Write a.py", "status": "COMPLETED",
            "expectedSha256": hashlib.sha256(b"same").hexdigest(), "evidence": []}])
        state = reconcile(session, self.root)
        self.assertEqual(state["files"], [])
        self.assertEqual(state["work"][0]["status"], "UNCERTAIN")
        self.assertIn("another source workspace", state["work"][0]["evidence"][-1])

    def test_malformed_source_diagnostics_survive_warm_refresh_and_clear_on_repair(self):
        path = self.source / "broken.jsonl"
        path.write_bytes(b'{"incomplete":')
        self.assertTrue(self.index.refresh()["errors"])
        warm = self.index.refresh()
        self.assertEqual(warm["bytesRead"], 0)
        self.assertTrue(warm["errors"])
        with path.open("ab") as stream:
            stream.write(b'\n{"type":"user","message":{"role":"user","content":"Appended"}}\n')
        self.assertTrue(self.index.refresh()["errors"])
        path.write_text('{"type":"user","message":{"role":"user","content":"Repaired"}}\n', encoding="utf-8")
        self.assertFalse(self.index.refresh()["errors"])

    def test_discovery_error_preserves_cached_entries_and_reports_warning(self):
        self.index.refresh()
        before = self.index.sessions()
        with patch.object(self.index.adapters["claude"], "discoverSessions", side_effect=PermissionError):
            stats = self.index.refresh()
        self.assertTrue(stats["errors"])
        self.assertEqual(before, self.index.sessions())

    def test_incomplete_index_never_auto_reads_apparently_unique_query(self):
        self.index.refresh()
        self.index.read = lambda row: self.fail("incomplete uniqueness is not selection")
        with patch.object(self.index, "refresh", return_value={"errors": ["source unavailable"]}):
            result = json.loads(self.server.picker({"query": "registry"}))
        self.assertTrue(result["selectionRequired"])
        self.assertEqual(result["reason"], "index_incomplete")
        self.assertTrue(result["indexIncomplete"])

    def test_empty_failed_inventory_differs_from_no_matches(self):
        with patch.object(self.index, "refresh", return_value={"errors": ["source unavailable"]}):
            result = json.loads(self.server.picker({"query": "missing"}))
            menu = self.server.mention_items({"query": ""})
        self.assertTrue(result["sourceUnavailable"])
        self.assertEqual(menu["items"], [])
        self.assertTrue(menu["warnings"])

    def test_native_menu_is_bounded_and_search_can_reach_older_sessions(self):
        self.index.refresh()
        original = self.index.sessions()[0]
        rows = [dict(original, ref=f"claude:{i}", title=f"Session {i}") for i in range(120)]
        with patch.object(self.server, "rows", return_value=rows):
            result = self.server.mention_items({"query": ""})
        self.assertEqual(len(result["items"]), 100)
        self.assertEqual(result["total"], 120)
        self.assertTrue(result["hasMore"])
        with patch.object(self.server, "rows", return_value=rows[-1:]) as search:
            result = self.server.mention_items({"query": "Session 119"})
        search.assert_called_once_with(query="Session 119")
        self.assertTrue(result["items"][0]["title"].startswith("Session 119 · "))


if __name__ == "__main__":
    unittest.main()
