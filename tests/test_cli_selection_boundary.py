"""Bare CLI references list candidates but never select a transcript implicitly."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentref.cli import main
from agentref.index import Index


class CliSelectionBoundaryTests(unittest.TestCase):
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
