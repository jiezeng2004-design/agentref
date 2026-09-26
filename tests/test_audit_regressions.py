"""Audit reproductions use isolated sources and actual CLI/MCP request paths."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agentref.adapters.registry import ADAPTERS
from agentref.cli import select
from agentref.index import Index
from agentref.mcp import Server
from extra_fixtures import BUILDERS


class AuditRegressionTests(unittest.TestCase):
    def test_shared_cache_hides_disabled_sources_without_deleting_them(self):
        from agentref.adapters.dsh import DshAdapter
        from dsh_fixtures import dsh
        dsh_root = self.root / 'dsh'
        dsh(dsh_root)
        (self.source / 'healthy.jsonl').write_text(json.dumps({
            'type': 'user', 'sessionId': 'healthy', 'message': {'content': 'CACHED_SOURCE'}}) + '\n', encoding='utf-8')
        adapters = [ADAPTERS['claude']([self.source]), DshAdapter([dsh_root])]
        index = Index(self.root / 'shared', adapters)
        index.refresh()
        cached = next(r for r in index.sessions() if r['agent'] == 'claude')
        index.close()
        index = Index(self.root / 'shared', adapters[1:])
        try:
            statements = []
            index.db.set_trace_callback(statements.append)
            index.refresh()
            cleanup = next(statement for statement in statements
                           if 'SELECT sourcePath,agent,ref FROM sessions' in statement and 'WHERE agent IN' in statement)
            self.assertIn("WHERE agent IN ('dsh')", cleanup)
            self.assertEqual([r['agent'] for r in index.sessions()], ['dsh'])
            self.assertEqual(index.sessions('claude'), [])
            self.assertEqual(index.matches(cached['ref']), [])
            with self.assertRaisesRegex(ValueError, 'not enabled'):
                index.read(cached)
        finally:
            index.close()
        index = Index(self.root / 'shared', adapters)
        try:
            self.assertIn(cached['ref'], [r['ref'] for r in index.sessions()])
        finally:
            index.close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()

    def index(self, agent):
        index = Index(self.root / 'index', [ADAPTERS[agent]([self.source])])
        self.addCleanup(index.close)
        return index

    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'agentref', '--data-dir', str(self.root / 'cli-index'),
                               '--claude-root', str(self.source), *args], input='',
                              capture_output=True, text=True, encoding='utf-8', timeout=15)

    def test_cli_incomplete_inventory_requires_selection_and_keeps_exact_ref_warning(self):
        (self.source / 'healthy.jsonl').write_text(json.dumps({
            'type': 'user', 'sessionId': 'healthy', 'message': {'content': 'AUDIT_UNIQUE_GOAL'}}) + '\n', encoding='utf-8')
        (self.source / 'broken.jsonl').write_bytes(b'{"incomplete":')
        listed = self.cli('sessions', '--json')
        self.assertEqual(listed.returncode, 0)
        self.assertIn('index incomplete', listed.stderr)
        ref = next(r['ref'] for r in json.loads(listed.stdout) if r['sessionId'] == 'healthy')
        for command in ('context', 'inspect', 'pick'):
            with self.subTest(command=command):
                rejected = self.cli(command, 'AUDIT_UNIQUE_GOAL')
                self.assertEqual(rejected.returncode, 2)
                self.assertEqual(rejected.stdout, '')
                accepted = self.cli(command, ref)
                self.assertEqual(accepted.returncode, 0)
                self.assertIn('AUDIT_UNIQUE_GOAL', accepted.stdout)
                self.assertIn('index refresh incomplete', accepted.stdout)
                self.assertIn('index incomplete', accepted.stderr)

    def test_single_partial_match_can_be_explicitly_selected_or_cancelled(self):
        rows = [dict(agent='claude', title='Title', cwd='', updatedAt='', latestAgentState='unknown')]
        with patch('sys.stdin.isatty', return_value=True), patch('sys.stderr', io.StringIO()):
            with patch('builtins.input', return_value='1'):
                self.assertIs(select(rows, require_selection=True), rows[0])
            with patch('builtins.input', return_value=''):
                with self.assertRaisesRegex(ValueError, 'cancelled'):
                    select(rows, require_selection=True)

    def test_extreme_timestamp_isolates_source_and_preserves_stdio(self):
        folder = BUILDERS['grok'](self.source)
        bad = folder.parent / 'bad'
        shutil.copytree(folder, bad)
        path = bad / 'summary.json'
        original = json.loads(path.read_text(encoding='utf-8'))
        index = self.index('grok')
        self.assertFalse(index.refresh()['errors'])
        for value in (1e100, -1e100, 10**400, float('inf'), float('nan')):
            with self.subTest(timestamp=str(value)[:20]):
                path.write_text(json.dumps(dict(original, created_at=value)), encoding='utf-8')
                source_bytes = path.read_bytes()
                requests = [dict(jsonrpc='2.0', id=1, method='tools/call', params={
                    'name': 'search_mentions', 'arguments': {'query': '', 'path': []}}),
                    dict(jsonrpc='2.0', id=2, method='ping')]
                output = io.StringIO()
                Server(index, agent='grok').serve(io.StringIO(''.join(json.dumps(r) + '\n' for r in requests)), output)
                responses = [json.loads(line) for line in output.getvalue().splitlines()]
                menu = responses[0]['result']['structuredContent']
                self.assertTrue(responses[0]['result']['_meta']['indexIncomplete'])
                self.assertTrue(menu['items'])
                self.assertEqual(responses[1], dict(jsonrpc='2.0', id=2, result={}))
                self.assertEqual(path.read_bytes(), source_bytes)
        path.write_text(json.dumps(original), encoding='utf-8')
        self.assertFalse(index.refresh()['errors'])

    def test_unknown_kind_diagnostics_survive_warm_append_and_repair(self):
        path = self.source / 'unknown.jsonl'
        path.write_text('{"type":"future_schema_v99"}\n', encoding='utf-8')
        index = self.index('claude')
        server = Server(index, agent='claude')
        for stage in ('cold', 'warm', 'append'):
            if stage == 'append':
                with path.open('a', encoding='utf-8') as stream:
                    stream.write('{"type":"user","message":{"content":"New goal"}}\n')
            menu = server.mention_items({'query': ''})
            self.assertTrue(menu['indexIncomplete'], stage)
            context = server.context(index.sessions()[0]['ref'])
            self.assertIn('index refresh incomplete', context)
        path.write_text('{"type":"user","message":{"content":"Repaired"}}\n', encoding='utf-8')
        self.assertFalse(server.mention_items({'query': ''})['indexIncomplete'])

    def test_legacy_cache_rechecks_unknown_kind_even_with_valid_append(self):
        path = self.source / 'unknown.jsonl'
        path.write_text('{"type":"future_schema_v99"}\n', encoding='utf-8')
        old = Index(self.root / 'index', [ADAPTERS['claude']([self.source])])
        try:
            old.refresh()
            with old.db:
                old.db.execute('UPDATE sessions SET warnings=0')
                old.db.execute('PRAGMA user_version=0')
        finally:
            old.close()
        with path.open('a', encoding='utf-8') as stream:
            stream.write('{"type":"user","message":{"content":"Appended"}}\n')
        index = self.index('claude')
        self.assertTrue(index.refresh()['errors'])
        self.assertEqual(index.db.execute('PRAGMA user_version').fetchone()[0], 4)

    def test_known_tool_records_do_not_create_false_metadata_warnings(self):
        for agent in ('claude', 'codex'):
            with self.subTest(agent=agent):
                source = self.root / agent
                source.mkdir()
                shutil.copyfile(Path(__file__).parent / 'fixtures' / (agent + '-normal.jsonl'), source / 'normal.jsonl')
                index = Index(self.root / (agent + '-index'), [ADAPTERS[agent]([source])])
                try:
                    self.assertFalse(index.refresh()['errors'])
                    self.assertFalse(index.refresh()['errors'])
                finally:
                    index.close()

    def test_adapter_diagnostics_survive_metadata_indexing_and_warm_cache(self):
        path = self.source / 'partial.jsonl'
        path.write_text(json.dumps({
            'type': 'user', 'sessionId': 'partial', 'message': {'content': 'Synthetic only'}}) + '\n', encoding='utf-8')
        adapter = ADAPTERS['claude']([self.source])
        consume = adapter.consume

        def consume_with_diagnostic(session, record):
            consume(session, record)
            if record.get('type') == 'user':
                session.parseWarnings.append('synthetic adapter diagnostic')

        adapter.consume = consume_with_diagnostic
        index = Index(self.root / 'diagnostic-index', [adapter])
        try:
            self.assertTrue(index.refresh()['errors'])
            self.assertEqual(index.db.execute('SELECT warnings FROM sessions').fetchone()[0], 1)
            self.assertTrue(index.refresh()['errors'])
        finally:
            index.close()

    def test_cli_session_query_is_applied_before_limit_and_offset(self):
        import os
        for number in range(5):
            path = self.source / f'session-{number}.jsonl'
            path.write_text(json.dumps({
                'type': 'user', 'sessionId': f'session-{number}',
                'message': {'content': f'MATCH_TARGET {number}'}}) + '\n', encoding='utf-8')
            os.utime(path, (1_700_000_000 + number, 1_700_000_000 + number))
        result = self.cli('sessions', '--agent', 'claude', '--json', '--query', 'MATCH_TARGET', '--limit', '2', '--offset', '1')
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual([row['sessionId'] for row in rows], ['session-3', 'session-2'])
        plain = self.cli('sessions', '--agent', 'claude', '--json', '--limit', '2', '--offset', '1')
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual([row['sessionId'] for row in json.loads(plain.stdout)], ['session-3', 'session-2'])

    def test_sql_session_pages_match_full_python_order_at_timestamp_edges(self):
        index = self.index('claude')
        rows = [
            ('claude:tie-a', 'tie-a', '2026-01-02T03:00:00+02:00', '', 2_000_000_000_000_000_000),
            ('claude:tie-z', 'tie-z', '2026-01-02T01:00:00Z', 'invalid', 1),
            ('claude:mtime', 'mtime', '', '', 1_700_000_000_000_000_000),
            ('claude:old', 'old', '', '0001-01-01T00:00:00+14:00', 1_700_000_000_000_000_001),
            ('claude:new', 'new', '9999-12-31T23:59:59.999999-14:00', '', 1),
            ('claude:epoch', 'epoch', 'invalid', 'invalid', 1),
        ]
        index.db.executemany('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
            (ref, 'claude', sid, sid, '', created, updated, f'synthetic::{sid}', 'unknown', mtime, 0, 0, '', 0)
            for ref, sid, created, updated, mtime in rows))
        index.db.commit()
        expected = [row['ref'] for row in index.sessions('claude')]
        for offset in range(len(expected) + 1):
            page = index.sessions('claude', limit=2, offset=offset)
            self.assertEqual([row['ref'] for row in page], expected[offset:offset + 2], offset)
        tail = index.sessions('claude', offset=3)
        self.assertEqual([row['ref'] for row in tail], expected[3:])

    def test_exact_reference_match_uses_single_sql_row(self):
        index = self.index('claude')
        ref = 'claude:0123456789abcdef'
        index.db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
            ref, 'claude', 'session-id', 'Exact target', '', '', '2026-01-01T00:00:00Z',
            'synthetic::exact', 'unknown', 0, 0, 0, '', 0))
        index.db.commit()
        with patch.object(index, 'sessions', side_effect=AssertionError('exact ref should not load the source list')):
            rows = index.matches(ref)
            page = index.matches(ref, limit=1)
            beyond = index.matches(ref, limit=1, offset=1)
        self.assertEqual([(row['ref'], row['title']) for row in rows], [(ref, 'Exact target')])
        self.assertEqual([row['ref'] for row in page], [ref])
        self.assertEqual(beyond, [])
