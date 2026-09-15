"""Cross-language source declarations must follow the Python catalog.

Keep host bundles self-contained; fail CI on drift instead of adding runtime
imports across independently installed integrations.
"""
import re
from pathlib import Path
import unittest

from agentref.adapters.registry import ADAPTERS
from agentref.agent_menu import AGENTS
from agentref.sources import SOURCES, supported_formats

ROOT = Path(__file__).resolve().parents[1]


class SourceCatalogTests(unittest.TestCase):
    def test_adapter_registration_and_formats(self):
        self.assertEqual(list(ADAPTERS), list(SOURCES))
        self.assertEqual(len(set(supported_formats())), len(SOURCES))
        self.assertIn("DSH", SOURCES["dsh"].format)

    def test_host_menu_policy_is_separate_from_source_support(self):
        self.assertIn("codex", SOURCES)
        self.assertNotIn("codex", AGENTS)
        self.assertEqual(AGENTS, {name: source.codex_menu_label
                                  for name, source in SOURCES.items()
                                  if source.codex_menu_label is not None})

    def test_javascript_lists_and_mention_patterns(self):
        paths = (
            "integrations/dsh/agentref-dsh/src/index.js",
            "integrations/dsh/agentref-dsh/src/client/index.js",
            "integrations/opencode/agentref-tui/tui.mjs",
        )
        for path in paths:
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                declaration = re.search(r"const (?:AGENTS|SOURCES) = (?:Object\.freeze\()?\[([^\]]+)\]", text)
                self.assertIsNotNone(declaration)
                self.assertEqual(re.findall(r"'([^']+)'", declaration[1]), list(SOURCES))
                if path != paths[0]:
                    pattern = re.search(r"@\(([a-z|]+)\)", text)
                    self.assertIsNotNone(pattern)
                    self.assertEqual(pattern[1].split("|"), list(SOURCES))

    def test_browser_labels(self):
        text = (ROOT / "integrations/dsh/agentref-dsh/src/client/index.js").read_text(encoding="utf-8")
        labels = re.search(r"return \{([^}]+)\}\[agent\]", text)
        self.assertIsNotNone(labels)
        self.assertEqual(dict(re.findall(r"(\w+): '([^']+)'", labels[1])),
                         {name: source.label for name, source in SOURCES.items()})
