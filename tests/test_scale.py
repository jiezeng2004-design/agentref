import unittest
from scripts.check_scale import check


class ScaleTests(unittest.TestCase):
    def test_five_sources_keep_recent_evidence_and_leave_sources_unchanged(self):
        for agent in ("claude", "codex", "grok", "opencode", "antigravity"):
            with self.subTest(agent=agent):
                result = check(agent, count=3, turns=30, width=2048)
                self.assertTrue(result["latestEvidencePreserved"])
                self.assertTrue(result["sourcesUnchanged"])
                self.assertLessEqual(result["contextChars"], 32000)


if __name__ == "__main__":
    unittest.main()
