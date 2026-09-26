import hashlib
import json
import sqlite3
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
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
            with self.assertRaises(ValueError):
                adapter.checked(source / '..' / 'outside.jsonl')
            file_link = source / 'linked-session.jsonl'
            file_link.symlink_to(target)
            with self.assertRaises(ValueError):
                adapter.checked(alias / 'sessions' / file_link.name)
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

    def test_grok_summary_metadata_cache_invalidates_edits_and_membership(self):
        source = self.root / "grok-cache-source"
        folder = BUILDERS["grok"](source)
        adapter = ADAPTERS["grok"]([source])
        self.assertTrue(adapter.metadata_cache_enabled)
        index = Index(self.root / "grok-cache-index", [adapter])
        self.addCleanup(index.close)
        summary = folder / "summary.json"
        with patch.object(adapter, "_metadata_checked", wraps=adapter._metadata_checked) as metadata:
            self.assertFalse(index.refresh()["errors"])
            self.assertEqual(metadata.call_count, 1)
            metadata.reset_mock()

            statements = []
            index.db.set_trace_callback(statements.append)
            stable = index.refresh()
            index.db.set_trace_callback(None)
            self.assertFalse(stable["errors"])
            self.assertEqual(stable["changed"], 0)
            self.assertEqual(metadata.call_count, 0)
            inventory_queries = [sql for sql in statements
                                 if "SELECT sourcePath FROM sessions WHERE agent=" in sql
                                 and "ORDER BY sourcePath" in sql]
            self.assertEqual(len(inventory_queries), 1)

            record = json.loads(summary.read_text(encoding="utf-8"))
            record["generated_title"] = "Edited Grok metadata"
            summary.write_text(json.dumps(record), encoding="utf-8")
            changed = index.refresh()
            self.assertFalse(changed["errors"])
            self.assertEqual(changed["changed"], 1)
            self.assertEqual(metadata.call_count, 1)
            self.assertEqual(index.sessions("grok")[0]["title"], "Edited Grok metadata")
            metadata.reset_mock()

            added = source / "another-project" / "grok-second"
            added.mkdir(parents=True)
            second = dict(record)
            second["info"] = dict(record.get("info") or {}, id="grok-second")
            second["generated_title"] = "Second Grok metadata"
            (added / "summary.json").write_text(json.dumps(second), encoding="utf-8")
            added_stats = index.refresh()
            self.assertFalse(added_stats["errors"])
            self.assertEqual(added_stats["changed"], 1)
            self.assertEqual(metadata.call_count, 1)
            self.assertEqual(len(index.sessions("grok")), 2)
            metadata.reset_mock()

            linked = source / "linked-project"
            try:
                linked.symlink_to(folder.parent, target_is_directory=True)
            except (OSError, NotImplementedError):
                linked = None
            if linked is not None:
                unsafe = index.refresh()
                self.assertTrue(unsafe["errors"])
                self.assertEqual(len(index.sessions("grok")), 2)
                linked.unlink()

            summary.unlink()
            removed = index.refresh()
            self.assertFalse(removed["errors"])
            self.assertEqual(removed["changed"], 0)
            self.assertEqual(metadata.call_count, 0)
            self.assertEqual([row["title"] for row in index.sessions("grok")], ["Second Grok metadata"])

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
        with patch('agentref.adapters.grok.read_jsonl', side_effect=AssertionError('list parser used'), create=True):
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
        adapter = index.adapters['opencode']
        statements = []
        database = adapter.database

        @contextmanager
        def traced(path):
            with database(path) as db:
                db.set_trace_callback(statements.append)
                yield db

        with patch.object(adapter, 'database', traced):
            reverted = index.read(row)
        self.assertNotIn('Reverted request', json.dumps(reverted.to_dict()))
        joined = next(statement for statement in statements if 'JOIN part AS p' in statement)
        self.assertIn('m.time_created IS NULL OR m.time_created<', joined)

    def test_opencode_reads_all_message_parts_with_one_ordered_join(self):
        source, index = self.index('opencode')
        adapter = index.adapters['opencode']
        statements = []
        database = adapter.database

        @contextmanager
        def traced(path):
            with database(path) as db:
                db.set_trace_callback(statements.append)
                yield db

        with patch.object(adapter, 'database', traced):
            session = adapter.read_session(source / 'opencode.db', 'oc-fixture')
        self.assertEqual([message['role'] for message in session.messages], ['user', 'assistant', 'user'])
        self.assertEqual(session.testRuns[0]['status'], 'COMPLETED')
        part_queries = [statement for statement in statements if 'JOIN part AS p' in statement]
        self.assertEqual(len(part_queries), 1)

    def test_opencode_snapshot_metadata_is_yielded_row_by_row(self):
        source, index = self.index('opencode')
        writer = sqlite3.connect(source / 'opencode.db')
        try:
            with writer:
                writer.executemany("INSERT INTO session VALUES (?,?,?,?,?,?,?)", (
                    (f'bulk-{n}', None, f'Bulk {n}', str(source), n, n, None) for n in range(100)))
        finally:
            writer.close()
        adapter = index.adapters['opencode']
        iterator = adapter.scan_metadata()
        try:
            with patch.object(adapter, 'metadata', wraps=adapter.metadata) as metadata:
                first = next(iterator)
                self.assertEqual(first.sessionId, 'oc-fixture')
                self.assertEqual(metadata.call_count, 1)
        finally:
            iterator.close()

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

    def test_antigravity_metadata_uses_one_snapshot_query(self):
        source = self.root / "antigravity-metadata"
        BUILDERS["antigravity"](source)
        adapter = ADAPTERS["antigravity"]([source])
        path = source / "ag-fixture.db"
        statements = []
        with adapter.database(path) as db:
            db.set_trace_callback(statements.append)
            session = adapter.metadata(db, path)
        selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
        self.assertEqual(len(selects), 1)
        self.assertEqual(session.sessionId, "ag-fixture")
        self.assertEqual(session.title, "Build an Antigravity sample")
        self.assertEqual(Path(session.cwd), source)

    def test_antigravity_parallel_metadata_scan_is_ordered_and_isolates_bad_files(self):
        template_root = self.root / "antigravity-template"
        BUILDERS["antigravity"](template_root)
        source = self.root / "antigravity-many"
        source.mkdir()
        for number in range(255):
            path = source / f"{number:04d}.db"
            shutil.copyfile(template_root / "ag-fixture.db", path)
            db = sqlite3.connect(path)
            db.execute("UPDATE trajectory_meta SET trajectory_id=?", (f"ag-{number:04d}",))
            db.commit()
            db.close()
        (source / "9999.db").write_bytes(b"invalid sqlite")

        def source_hashes():
            return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in source.glob("*.db")}

        before = source_hashes()
        adapter = ADAPTERS["antigravity"]([source])
        rows = list(adapter.scan_metadata())
        self.assertEqual([row.sessionId for row in rows], [f"ag-{number:04d}" for number in range(255)])
        self.assertEqual(len(adapter.scan_errors), 1)
        self.assertEqual(source_hashes(), before)

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
        with patch('agentref.adapters.grok.read_jsonl', side_effect=AssertionError('list parser used'), create=True):
            s = index.read(index.sessions()[0])
        self.assertEqual(s.originalGoal, 'Fallback task')
        self.assertTrue(any('fallback' in w for w in s.parseWarnings))
        self.assertNotIn('REASONING_SENTINEL', json.dumps(s.to_dict()))


if __name__ == '__main__':
    unittest.main()
