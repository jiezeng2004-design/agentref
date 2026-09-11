import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from agentref.adapters.registry import ADAPTERS
from agentref.index import Index
from agentref.titles import (CACHE, MAX_LINE, apply_cached_titles, bounded_records,
                             identity, organize, request_title, user_texts)
from dsh_fixtures import dsh
from extra_fixtures import BUILDERS


class TitleTests(unittest.TestCase):
    def test_request_filter_and_limits(self):
        for text in ("<environment_context>secret</environment_context>", "# AGENTS.md instructions",
                     "继续", "token=synthetic", "https://example.test/private", ""):
            self.assertEqual(request_title(text), "")
        self.assertEqual(request_title("# AGENTS.md instructions\nignore\n## My request:\n修复登录页面\n说明"), "修复登录页面")
        self.assertLessEqual(len(request_title("需求" * 100)), 60)
        self.assertEqual(list(bounded_records(io.BytesIO(b'x' * (MAX_LINE + 1)))), [])

    def test_dsh_cache_identity_precedence_and_read_only_menu(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = dsh(root / "source")
            before = path.read_bytes()
            adapter = ADAPTERS['dsh']([root / "source"])
            index = Index(root / "index", [adapter])
            try:
                index.refresh()
                result = organize(index)
                self.assertEqual(result['stats']['derived'], 1)
                with patch('agentref.titles.user_texts', side_effect=AssertionError('menu body read')):
                    row = index.sessions()[0]
                self.assertEqual(row['title'], 'Build a DSH sample')
                self.assertEqual(row['titleSource'], 'local-user-request')
                self.assertEqual(organize(index)['stats']['candidates'], 0)
                changed = dict(row, title='未命名会话', sessionId='different')
                apply_cached_titles(index.home, [changed])
                self.assertEqual(changed['title'], '未命名会话')
                named = dict(row, title='Official title')
                apply_cached_titles(index.home, [named])
                self.assertEqual(named['title'], 'Official title')
                self.assertEqual(path.read_bytes(), before)
            finally:
                index.close()

    def test_bounded_readers_for_other_agents(self):
        with tempfile.TemporaryDirectory() as temp:
            for agent, expected in (('grok', 'Build a sample'), ('opencode', 'Build sample'),
                                    ('antigravity', 'Build an Antigravity sample')):
                root = Path(temp) / agent
                BUILDERS[agent](root)
                if agent == 'opencode':
                    with sqlite3.connect(root / 'opencode.db') as db:
                        db.execute("UPDATE session SET title='' WHERE parent_id IS NULL")
                    db.close()
                adapter = ADAPTERS[agent]([root])
                session = next(adapter.scan_metadata())
                row = vars(session)
                self.assertEqual(next(user_texts(adapter, row)), expected)
            for agent in ('claude', 'codex'):
                root = Path(temp) / agent
                root.mkdir()
                path = root / 'session.jsonl'
                if agent == 'claude':
                    records = [dict(sessionId='sample', type='user', message=dict(content='Build sample'))]
                else:
                    records = [dict(type='session_meta', payload=dict(id='sample')),
                               dict(type='session_meta', payload=dict(id='inherited-parent')),
                               dict(type='response_item', payload=dict(type='message', role='user', content=[dict(type='input_text', text='Build sample')]))]
                path.write_text(''.join(json.dumps(r)+'\n' for r in records), encoding='utf-8')
                adapter = ADAPTERS[agent]([root])
                row = dict(agent=agent, sessionId='sample', sourcePath=str(path))
                self.assertEqual(next(user_texts(adapter, row)), 'Build sample')
                with self.assertRaises(ValueError):
                    next(user_texts(adapter, dict(row, sessionId='wrong')))

    def test_dsh_injection_skipped_and_compressed_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = dsh(root)
            records = path.read_text().splitlines()
            injected = json.loads(records[1])
            injected['data']['source']['kind'] = 'plugin'
            path.write_text(records[0]+'\n'+json.dumps(injected)+'\n'+records[1]+'\n', encoding='utf-8')
            adapter = ADAPTERS['dsh']([root])
            self.assertEqual(list(user_texts(adapter, vars(adapter.metadata(path)))), ['Build a DSH sample'])
            try:
                from compression import zstd
                compress = zstd.compress
            except ImportError:
                import zstandard
                compress = zstandard.ZstdCompressor().compress
            zipped = path.with_suffix('.jsonl.zstd')
            zipped.write_bytes(compress(path.read_bytes()))
            self.assertEqual(next(user_texts(adapter, vars(adapter.metadata(zipped)))), 'Build a DSH sample')
