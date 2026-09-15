import unittest
from scripts.check_scale import check
from agentref.adapters.registry import ADAPTERS


class ScaleTests(unittest.TestCase):
    def test_all_sources_keep_recent_evidence_and_leave_sources_unchanged(self):
        for agent in ADAPTERS:
            with self.subTest(agent=agent):
                result = check(agent, count=3, turns=30, width=2048)
                self.assertTrue(result["latestEvidencePreserved"])
                self.assertTrue(result["sourcesUnchanged"])
                self.assertLessEqual(result["contextChars"], 32000)

    def test_compressed_dsh_keeps_recent_evidence_and_leaves_sources_unchanged(self):
        result = check("dsh", count=3, turns=30, width=2048, dsh_compressed=True)
        self.assertEqual(result["sourceFormat"], "jsonl.zstd")
        self.assertTrue(result["latestEvidencePreserved"])
        self.assertTrue(result["sourcesUnchanged"])
        self.assertLessEqual(result["contextChars"], 32000)


if __name__ == "__main__":
    unittest.main()
