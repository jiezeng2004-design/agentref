"""Verifier checks use a synthetic receiver; they are not model acceptance."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.continuation_trial import prepare, verify, SCENARIOS

ROLLBACK = "\n\ndef rollback(d, key):\n    d.pop(key, None)\n"


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_all_scenarios_preserve_source_and_existing_code(self):
        for agent in ("claude", "codex"):
            for scenario in SCENARIOS:
                with self.subTest(agent=agent, scenario=scenario):
                    root = prepare(agent, scenario, self.root)
                    context = (root / "context.md").read_text(encoding="utf-8")
                    self.assertIn('"id": "trial-selected"', context)
                    self.assertNotIn('"id": "trial-decoy"', context)
                    if scenario == "workspace_changed":
                        self.assertIn("current bytes differ", context)
                    if scenario == "retry_succeeded":
                        self.assertIn('"supersededBy": 1', context)
                    with (root / "workspace/registry.py").open("a", encoding="utf-8") as stream:
                        stream.write(ROLLBACK)
                    result = verify(root)
                    self.assertTrue(result["passed"])
                    self.assertFalse(result["nativeUIVerified"])

    def test_unfinished_trial_fails_before_receiver_implements(self):
        root = prepare("claude", "interrupted", self.root)
        self.assertFalse(verify(root)["passed"])

    def test_modified_tests_are_not_executed(self):
        root = prepare("codex", "interrupted", self.root)
        (root / "workspace/test_registry.py").write_text("raise AssertionError('do not run modified tests')", encoding="utf-8")
        result = verify(root)
        self.assertFalse(result["testsUnchanged"])
        self.assertFalse((root / "verification.log").exists())

    def test_rewriting_completed_portion_fails_even_if_tests_pass(self):
        root = prepare("claude", "workspace_changed", self.root)
        target = root / "workspace/registry.py"
        target.write_text("def register(d, key, value):\n    d.update({key: value})\n" + ROLLBACK, encoding="utf-8")
        result = verify(root)
        self.assertTrue(result["testsPassed"])
        self.assertFalse(result["completedCodePreserved"])
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
