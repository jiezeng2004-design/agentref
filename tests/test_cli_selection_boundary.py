"""Bare CLI references list candidates but never select a transcript implicitly."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentref.cli import main
from agentref.index import Index
from agentref.adapters.claude import ClaudeAdapter
from agentref.adapters.codex import CodexAdapter


class CliSelectionBoundaryTests(unittest.TestCase):
    def test_conflicting_source_filter_cannot_resolve_to_another_agents_alias(self):
        for command in ("pick", "context", "inspect"):
            for query in ("codex", "@codex:shared-title"):
                with self.subTest(command=command, query=query), \
                     patch("agentref.cli.default_adapters", return_value=[]), \
                     patch("agentref.cli.Index", side_effect=AssertionError("conflicting source indexed")), \
                     patch("sys.stdout", io.StringIO()) as output, \
                     patch("sys.stderr", io.StringIO()) as error:
                    self.assertEqual(main([command, query, "--agent", "claude"]), 2)
                    self.assertEqual(output.getvalue(), "")
                    self.assertIn("conflicts with --agent", error.getvalue())

    def test_filtered_listing_never_discovers_other_sources_or_removes_their_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            claude = root / "claude"
            codex = root / "codex"
            claude.mkdir()
            codex.mkdir()
            (claude / "sample.jsonl").write_text(
                '{"type":"user","sessionId":"sample","message":{"content":"Synthetic task"}}\n',
                encoding="utf-8")
            (codex / "sample.jsonl").write_text(
                '{"type":"session_meta","payload":{"id":"codex-sample","cwd":"/synthetic"}}\n',
                encoding="utf-8")
            adapters = [ClaudeAdapter([claude]), CodexAdapter([codex])]
            index = Index(root / "index", adapters)
            try:
                index.refresh()
                before = index.sessions("codex")
                self.assertEqual(len(before), 1)
            finally:
                index.close()
            with patch("agentref.cli.default_adapters", return_value=adapters), \
                 patch.object(adapters[1], "discoverSessions", side_effect=AssertionError("unrelated source scan")), \
                 patch.object(Index, "read", side_effect=AssertionError("unselected context read")), \
                 patch("sys.stdout", io.StringIO()) as output:
                self.assertEqual(main(["--data-dir", str(root / "index"), "sessions", "--agent", "claude", "--json"]), 0)
                self.assertEqual([row["agent"] for row in json.loads(output.getvalue())], ["claude"])
            index = Index(root / "index", adapters)
            try:
                self.assertEqual(index.sessions("codex"), before)
            finally:
                index.close()

    def test_single_candidate_requires_selection_for_bare_references(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source'
            source.mkdir()
            (source / 'demo.jsonl').write_text(
                '{"type":"user","sessionId":"demo","message":{"content":"Unique synthetic task"}}\n',
                encoding='utf-8')
            for command in ('pick', 'context', 'inspect'):
                for query in ('', 'claude', '@claude', '  '):
                    with self.subTest(command=command, query=query), \
                         patch('sys.stdout', io.StringIO()) as output, \
                         patch('sys.stderr', io.StringIO()), \
                         patch('sys.stdin.isatty', return_value=False), \
                         patch.object(Index, 'read', side_effect=AssertionError('unselected transcript read')):
                        result = main(['--data-dir', str(root / 'index'), '--claude-root', str(source), command, query])
                        self.assertEqual(result, 2)
                        self.assertEqual(output.getvalue(), '')

    def test_single_candidate_can_be_cancelled_or_explicitly_selected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source'
            source.mkdir()
            (source / 'demo.jsonl').write_text(
                '{"type":"user","sessionId":"demo","message":{"content":"Unique synthetic task"}}\n', encoding='utf-8')
            args = ['--data-dir', str(root / 'index'), '--claude-root', str(source), 'pick', 'claude']
            with patch('sys.stdin.isatty', return_value=True), patch('sys.stderr', io.StringIO()):
                with patch('builtins.input', return_value=''), patch('sys.stdout', io.StringIO()) as output, \
                     patch.object(Index, 'read', side_effect=AssertionError('cancelled transcript read')):
                    self.assertEqual(main(args), 2)
                    self.assertEqual(output.getvalue(), '')
                with patch('builtins.input', return_value='1'), patch('sys.stdout', io.StringIO()) as output:
                    self.assertEqual(main(args), 0)
                    self.assertIn('Unique synthetic task', output.getvalue())
