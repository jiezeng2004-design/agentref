import tempfile
from pathlib import Path
import unittest

from agentref.adapters.registry import ADAPTERS
from agentref.index import Index
from scripts.check_index_query import check


class IndexQueryTests(unittest.TestCase):
    def test_filtered_and_unfiltered_results_match_full_table_reference(self):
        report = check(rows=60, repeats=1)
        self.assertTrue(report["resultsEquivalent"])
        for scenario in report["scenarios"]:
            self.assertEqual(scenario["materializedRows"]["reference"], 60)
            self.assertEqual(scenario["materializedRows"]["current"], scenario["returned"])

    def test_unknown_disabled_and_empty_sources_do_not_query_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td), [ADAPTERS["claude"]([])])
            try:
                statements = []
                index.db.set_trace_callback(statements.append)
                self.assertEqual(index.sessions("codex"), [])
                self.assertEqual(index.sessions("claude' OR 1=1 --"), [])
                index.adapters = {}
                self.assertEqual(index.sessions(), [])
                self.assertFalse(any("SELECT" in s.upper() for s in statements))
            finally:
                index.close()

    def test_agent_index_is_created_for_existing_database(self):
        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td), [])
            index.db.execute("DROP INDEX sessions_agent")
            index.db.commit()
            index.close()
            index = Index(Path(td), [])
            try:
                names = [row[1] for row in index.db.execute("PRAGMA index_list(sessions)")]
                self.assertIn("sessions_agent", names)
            finally:
                index.close()
