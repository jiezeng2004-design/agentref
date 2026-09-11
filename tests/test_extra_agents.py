import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from agentref.adapters.registry import ADAPTERS
from agentref.adapters.protobuf import fields
from agentref.adapters.snapshot import SnapshotAdapter
from agentref.index import Index
from agentref.mcp import Server
from extra_fixtures import BUILDERS, proto


class ExtraAgentsTest(unittest.TestCase):
    def test_system_ancestor_alias_does_not_allow_links_inside_source(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            real = base / 'real'
            source = real / 'sessions'
            source.mkdir(parents=True)
            target = source / 'session.jsonl'
            target.write_text('{}', encoding='utf-8')
            alias = base / 'alias'
            try:
                alias.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest('Directory symlinks unavailable on this host')
            adapter = SnapshotAdapter([alias / 'sessions'])
            self.assertEqual(adapter.checked(alias / 'sessions' / target.name), target)
            inside = source / 'linked'
            inside.symlink_to(source, target_is_directory=True)
            with self.assertRaises(ValueError):
                adapter.checked(alias / 'sessions' / 'linked' / target.name)
            outside = real / 'outside.jsonl'
            outside.write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError):
                adapter.checked(alias / 'outside.jsonl')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def index(self, name):
        source = self.root / name
        BUILDERS[name](source)
        index = Index(self.root / (name + '-index'), [ADAPTERS[name]([source])])
        self.addCleanup(index.close)
        return source, index

    def test_all_sources_menu_context_and_readonly(self):
        for name in BUILDERS:
            with self.subTest(agent=name):
                source, index = self.index(name)
                def hashes():
                    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
                before = hashes()
                self.assertFalse(index.refresh()['errors'])
                server = Server(index, agent=name)
                menu = server.mention_items({'query': '', 'path': []})['items']
                self.assertEqual(len(menu), 1)
                result = server.dispatch('resources/read', {'uri': menu[0]['resourceUri']})
                context = result['contents'][0]['text']
                self.assertIn('Build', context)
                self.assertNotIn('REASONING_SENTINEL', context)
                self.assertEqual(before, hashes())
                tools = server.dispatch('tools/list', {})['tools']
                self.assertEqual(next(t for t in tools if t['name'] == 'sessions')['inputSchema']['properties']['agent']['enum'], [name])

    def test_grok_stream_chunks_failure_and_incomplete_tail(self):
        source, index = self.index('grok')
        index.refresh()
        row = index.sessions()[0]
        session = index.read(row)
        self.assertEqual(session.originalGoal, 'Build a sample')
        self.assertEqual(session.messages[-1]['text'], 'Tests failed; fix pending.')
        self.assertEqual(session.testRuns[0]['status'], 'FAILED')
        log = next(source.rglob('updates.jsonl'))
        with log.open('ab') as stream:
            stream.write(b'{"partial":')
        self.assertEqual(index.read(row).latestAgentState, 'incomplete')

    def test_opencode_live_wal_metadata_and_selected_session(self):
        source, index = self.index('opencode')
        writer = sqlite3.connect(source / 'opencode.db')
        self.addCleanup(writer.close)
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute("UPDATE session SET title='Changed in WAL' WHERE id='oc-fixture'")
        writer.commit()
        self.assertFalse(index.refresh()['errors'])
        row = index.sessions()[0]
        self.assertEqual(row['title'], 'Changed in WAL')
        self.assertEqual(index.read(row).testRuns[0]['status'], 'COMPLETED')
        with index.adapters['opencode'].database(source / 'opencode.db') as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM session")
        writer.execute('UPDATE session SET revert=? WHERE id=?', (json.dumps({'messageID': 'm3'}), 'oc-fixture'))
        writer.commit()
        self.assertNotIn('Reverted request', json.dumps(index.read(row).to_dict()))

    def test_database_source_escape_rejected(self):
        source, index = self.index('opencode')
        index.refresh()
        row = index.sessions()[0]
        row['sourcePath'] = str(self.root / 'outside.db') + '::' + row['sessionId']
        with self.assertRaises(ValueError):
            index.read(row)

    def test_antigravity_command_exit_and_schema_warning(self):
        source, index = self.index('antigravity')
        index.refresh()
        row = index.sessions()[0]
        s = index.read(row)
        self.assertEqual(s.testRuns[0]['status'], 'COMPLETED')
        self.assertEqual(Path(s.cwd), source)
        db = sqlite3.connect(source / 'ag-fixture.db')
        db.execute('INSERT INTO steps VALUES (9,999,3,?,?,0)', (b'', b'\x80'))
        db.commit()
        db.close()
        s = index.read(row)
        self.assertTrue(any('step 9' in w for w in s.parseWarnings))
        self.assertEqual(len(s.messages), 2)

    def test_antigravity_subagent_excluded(self):
        source, index = self.index('antigravity')
        db = sqlite3.connect(source / 'ag-fixture.db')
        db.execute('UPDATE trajectory_metadata_blob SET data=?', (proto((8, proto((1, 'child')))),))
        db.commit()
        db.close()
        self.assertFalse(index.refresh()['errors'])
        self.assertEqual(index.sessions(), [])

    def test_malformed_wire_rejected(self):
        for data in (b'\x80', b'\x0a\xff', b'\x0a\x03x', b'\x00'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                fields(data)

    def test_transient_database_failure_keeps_index(self):
        source, index = self.index('opencode')
        index.refresh()
        db = sqlite3.connect(source / 'opencode.db')
        db.execute('ALTER TABLE session RENAME TO temporarily_unavailable')
        db.commit()
        db.close()
        self.assertTrue(index.refresh()['errors'])
        self.assertEqual(len(index.sessions()), 1)

    def test_filtered_servers_do_not_purge_each_others_index(self):
        for name in ('grok', 'opencode'):
            BUILDERS[name](self.root / name)
        first = Index(self.root / 'shared', [ADAPTERS['grok']([self.root / 'grok'])])
        second = Index(self.root / 'shared', [ADAPTERS['opencode']([self.root / 'opencode'])])
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        first.refresh()
        second.refresh()
        first.refresh()
        self.assertEqual(len(first.sessions('grok')), 1)
        self.assertEqual(len(second.sessions('opencode')), 1)

    def test_one_corrupt_database_does_not_hide_healthy_sources(self):
        source, index = self.index('antigravity')
        (source / '000-corrupt.db').write_bytes(b'not a database')
        self.assertTrue(index.refresh()['errors'])
        self.assertEqual(len(index.sessions()), 1)

    def test_grok_fallback_omits_internal_reasoning(self):
        source, index = self.index('grok')
        folder = next(source.rglob('summary.json')).parent
        (folder / 'updates.jsonl').unlink()
        (folder / 'chat_history.jsonl').write_text('\n'.join(json.dumps(r) for r in [
            {'type': 'user', 'content': 'Fallback task'},
            {'type': 'reasoning', 'content': 'PRIVATE_REASONING_SENTINEL'},
            {'type': 'assistant', 'content': 'Fallback answer'},
        ]) + '\n', encoding='utf-8')
        index.refresh()
        s = index.read(index.sessions()[0])
        self.assertEqual(s.originalGoal, 'Fallback task')
        self.assertTrue(any('fallback' in w for w in s.parseWarnings))
        self.assertNotIn('REASONING_SENTINEL', json.dumps(s.to_dict()))


if __name__ == '__main__':
    unittest.main()
