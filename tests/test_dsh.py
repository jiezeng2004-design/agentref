import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentref.adapters.dsh import DshAdapter
from agentref.index import Index
from agentref.mcp import Server
from dsh_fixtures import dsh
from scripts.check_dsh_event_streaming import measure


class DshTests(unittest.TestCase):
    def test_malformed_selected_record_returns_error_and_mcp_keeps_serving(self):
        cache = tempfile.TemporaryDirectory()
        self.addCleanup(cache.cleanup)
        shapes = [
            ('user/message', {'source': None}),
            ('assistant/message', {'message': None}),
            ('assistant/message', {'message': {'content': [None]}}),
            ('tool/result', {'message': {'content': [None]}}),
            ('tool/call', {}),
        ]
        for kind, data in shapes:
            with self.subTest(kind=kind, data=data):
                dsh(self.root)
                event = dict(seq=3, type=kind, data=data)
                if kind != 'tool/call':
                    event['surfaceOp'] = 'append'
                self.append(event)
                original = self.path.read_bytes()
                with self.assertRaises(ValueError):
                    self.adapter.readSession(self.path)
                index = Index(Path(cache.name), [self.adapter])
                try:
                    index.refresh()
                    ref = index.sessions()[0]['ref']
                    requests = [
                        dict(jsonrpc='2.0', id=1, method='tools/call', params={
                            'name': 'context', 'arguments': {'ref': ref}}),
                        dict(jsonrpc='2.0', id=2, method='ping'),
                    ]
                    sink = io.StringIO()
                    Server(index, agent='dsh').serve(io.StringIO('\n'.join(map(json.dumps, requests)) + '\n'), sink)
                    replies = list(map(json.loads, sink.getvalue().splitlines()))
                    self.assertTrue(replies[0]['result']['isError'])
                    self.assertEqual(replies[1], {'jsonrpc': '2.0', 'id': 2, 'result': {}})
                finally:
                    index.close()
                self.assertEqual(self.path.read_bytes(), original)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = dsh(self.root)
        self.adapter = DshAdapter([self.root])

    def append(self, event):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def test_metadata_menu_never_reads_context(self):
        original = self.path.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            index = Index(Path(tmp), [self.adapter])
            try:
                with patch.object(self.adapter, "readSession", side_effect=AssertionError("body read")):
                    response = Server(index, agent="dsh").dispatch("tools/call", {
                        "name": "search_mentions", "arguments": {"query": "", "path": []}})
                    self.assertEqual(set(response["structuredContent"]), {"items"})
                    self.assertEqual(len(response["structuredContent"]["items"]), 1)
                    item = response["structuredContent"]["items"][0]
                    self.assertNotEqual(item["title"], "未命名 DSH 会话")
                    self.assertIn(" · ", item["title"])
                    self.assertTrue(item["resourceUri"].startswith("agentref://session/dsh:"))
            finally:
                index.close()
        self.assertEqual(self.path.read_bytes(), original)

    def test_bom_and_crlf_jsonl_records_use_compatible_decoder(self):
        canonical = self.path.read_bytes()
        self.path.write_bytes(b"\xef\xbb\xbf" + canonical.replace(b"\n", b"\r\n"))
        session = self.adapter.readSession(self.path)
        self.assertEqual(session.originalGoal, "Build a DSH sample")
        self.assertEqual(session.latestAgentState, "turn_ended")

        lines = canonical.splitlines()
        self.path.write_bytes(b"".join(b"  " + line + b"  \n" for line in lines))
        spaced = self.adapter.readSession(self.path)
        self.assertEqual(spaced.messages, session.messages)

    def test_snapshot_refresh_skips_unchanged_index_writes_and_updates_changed_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            index = Index(Path(temp), [self.adapter])
            try:
                first = index.refresh()
                self.assertEqual(first["changed"], 1)
                total_changes = index.db.total_changes
                warm = index.refresh()
                self.assertEqual(warm["files"], 1)
                self.assertEqual(warm["changed"], 0)
                self.assertEqual(index.db.total_changes, total_changes)

                records = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
                records[0]["cwd"] = str(self.root / "changed")
                self.path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
                changed = index.refresh()
                self.assertEqual(changed["changed"], 1)
                self.assertEqual(index.sessions()[0]["cwd"], str(self.root / "changed"))
            finally:
                index.close()

    def test_streaming_dsh_event_benchmark_preserves_terminal_state(self):
        result = measure(events=24)
        self.assertTrue(result["synthetic"])
        self.assertTrue(result["equivalentState"])
        self.assertEqual(result["events"], 25)

    def test_zstd_and_plain_selected_context(self):
        try:
            from compression import zstd
            compress = zstd.compress
        except ImportError:
            import zstandard
            compress = zstandard.ZstdCompressor().compress
        plain = self.adapter.readSession(self.path)
        compressed = self.path.with_suffix(".jsonl.zstd")
        compressed.write_bytes(compress(self.path.read_bytes()))
        zipped = self.adapter.readSession(compressed)
        self.assertEqual(plain.messages, zipped.messages)
        self.assertEqual(zipped.originalGoal, "Build a DSH sample")
        self.assertEqual(zipped.latestAgentState, "turn_ended")

    def test_compaction_excludes_replaced_goal_and_injection_is_not_user(self):
        self.append(dict(seq=3, type="user/message", surfaceOp=dict(op="replace", start=0, end=1),
                         data=dict(source=dict(kind="plugin"), content=[dict(type="text", text="summary")])) )
        self.append(dict(seq=4, type="user/message", surfaceOp="append",
                         data=dict(source=dict(kind="user"), content=[dict(type="text", text="New goal")])))
        result = self.adapter.readSession(self.path)
        self.assertEqual(result.latestUserRequest, "New goal")
        self.assertNotIn("Build a DSH sample", str(result.messages))
        self.assertTrue(result.parseWarnings)

    def test_non_tail_compaction_preserves_sequence_lookup_fallback(self):
        self.append(dict(seq=3, type="user/message", surfaceOp=dict(op="replace", start=0, end=0),
                         data=dict(source=dict(kind="plugin"), content=[dict(type="text", text="first summary")])) )
        self.append(dict(seq=4, type="user/message", surfaceOp=dict(op="replace", start=1, end=1),
                         data=dict(source=dict(kind="plugin"), content=[dict(type="text", text="second summary")])) )
        self.append(dict(seq=5, type="user/message", surfaceOp="append",
                         data=dict(source=dict(kind="user"), content=[dict(type="text", text="New goal")])) )
        result = self.adapter.readSession(self.path)
        self.assertEqual(result.latestUserRequest, "New goal")
        self.assertEqual([message["text"] for message in result.messages], [
            "[Historical injected context]\nfirst summary",
            "[Historical injected context]\nsecond summary",
            "New goal",
        ])
        self.assertEqual(sum("compacted surface" in warning for warning in result.parseWarnings), 2)

    def test_incomplete_tail_and_sequence_gap(self):
        with self.path.open("ab") as f:
            f.write(b'{"torn":')
        result = self.adapter.readSession(self.path)
        self.assertEqual(result.latestAgentState, "incomplete")
        dsh(self.root)
        self.append(dict(seq=100, type="turn/end", data={}))
        with self.assertRaises(ValueError):
            self.adapter.readSession(self.path)

    def test_backup_subagent_future_version_and_corruption(self):
        backup = self.root / "session-recovery-backup/a/session-x"
        backup.mkdir(parents=True)
        (backup / "session.jsonl").write_bytes(self.path.read_bytes())
        self.assertEqual(len(list(self.adapter.scan_metadata())), 1)
        data = self.path.read_text(encoding="utf-8").splitlines()
        header = json.loads(data[0]); header['origin'] = 'subagent'
        self.path.write_text(json.dumps(header)+'\n', encoding='utf-8')
        self.assertEqual(list(self.adapter.scan_metadata()), [])
        header['version'] = 999
        self.path.write_text(json.dumps(header)+'\n', encoding='utf-8')
        self.assertEqual(list(self.adapter.scan_metadata()), [])
        self.assertTrue(self.adapter.scan_errors)

    def test_scandir_rejects_linked_session_folders_and_preserves_index(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            index = Index(Path(cache_dir) / "index", [self.adapter])
            try:
                self.assertFalse(index.refresh()["errors"])
                linked = self.root / "sessions/project/session-linked"
                try:
                    linked.symlink_to(self.path.parent, target_is_directory=True)
                except (OSError, NotImplementedError):
                    self.skipTest("Directory symlinks unavailable on this host")
                result = index.refresh()
                self.assertTrue(result["errors"])
                self.assertEqual(len(index.sessions("dsh")), 1)
                self.assertEqual(index.sessions("dsh")[0]["sourcePath"], str(self.path.resolve()))
            finally:
                index.close()

    def test_title_cache_identity_and_header_only(self):
        cache = self.root / 'storages/session_projcache/sessions/session-synthetic.json'
        cache.parent.mkdir(parents=True)
        record = dict(identity=dict(createdAt=1700000000000,cwd=str(self.root)), rows=dict(title=dict(val='Saved title')))
        cache.write_text(json.dumps(dict(record=record)), encoding='utf-8')
        self.assertEqual(self.adapter.metadata(self.path).title, 'Saved title')
        record['identity']['createdAt'] = 1
        cache.write_text(json.dumps(dict(record=record)), encoding='utf-8')
        self.assertNotEqual(self.adapter.metadata(self.path).title, 'Saved title')

    def test_snapshot_metadata_cache_tracks_title_projection_changes(self):
        projection = self.root / 'storages/session_projcache/sessions/session-synthetic.json'
        projection.parent.mkdir(parents=True)
        record = dict(identity=dict(createdAt=1700000000000,cwd=str(self.root)),
                      rows=dict(title=dict(val='Cached DSH title')))
        projection.write_text(json.dumps(dict(record=record)), encoding='utf-8')
        adapter = DshAdapter([self.root])
        adapter.metadata_cache_enabled = True
        with tempfile.TemporaryDirectory() as index_root:
            index = Index(Path(index_root) / 'index', [adapter])
            try:
                self.assertFalse(index.refresh()['errors'])
                self.assertEqual(index.sessions('dsh')[0]['title'], 'Cached DSH title')
                stable = index.refresh()
                self.assertFalse(stable['errors'])
                self.assertEqual(stable['changed'], 0)

                record['rows']['title']['val'] = 'Changed DSH title'
                projection.write_text(json.dumps(dict(record=record)), encoding='utf-8')
                changed = index.refresh()
                self.assertFalse(changed['errors'])
                self.assertEqual(changed['changed'], 1)
                self.assertEqual(index.sessions('dsh')[0]['title'], 'Changed DSH title')
            finally:
                index.close()

    def test_tool_success_failure_and_crash_pending_are_distinct(self):
        self.append(dict(seq=3, type='tool/call', data=dict(callId='ok', name='shell', arguments='{"command":"python -m unittest"}')))
        self.append(dict(seq=4, type='tool/result', surfaceOp='append', data=dict(message=dict(content=[
            dict(type='tool-result', toolCallId='ok', content=[dict(type='text', text='{"exit_code":0}')])]))))
        self.append(dict(seq=5, type='tool/call', data=dict(callId='failed', name='shell', arguments='{"command":"test-fail"}')))
        self.append(dict(seq=6, type='tool/result', surfaceOp='append', data=dict(message=dict(content=[
            dict(type='tool-result', toolCallId='failed', isError=True, content=[dict(type='text', text='Error: failed')])]))))
        self.append(dict(seq=7, type='tool/call', data=dict(callId='pending', name='shell', arguments='{"command":"pending"}')))
        result = self.adapter.readSession(self.path)
        self.assertEqual([c['status'] for c in result.toolCalls], ['COMPLETED', 'FAILED', 'UNCERTAIN'])
        self.assertEqual(result.latestAgentState, 'incomplete')
        self.assertEqual(len(result.testRuns), 1)

    def test_pending_tool_call_map_keeps_latest_duplicate_payload(self):
        self.append(dict(seq=3, type='tool/call', data=dict(
            callId='reused', name='first-tool', arguments={'command': 'first'})))
        self.append(dict(seq=4, type='tool/call', data=dict(
            callId='reused', name='latest-tool', arguments={'command': 'latest'})))
        self.append(dict(seq=5, type='tool/result', surfaceOp='append', data=dict(message=dict(content=[
            dict(type='tool-result', toolCallId='reused', content=[dict(type='text', text='done')])]))))
        session = self.adapter.readSession(self.path)
        self.assertEqual(len(session.toolCalls), 1)
        self.assertEqual(session.toolCalls[0]['name'], 'latest-tool')
        self.assertEqual(session.toolCalls[0]['arguments'], {'command': 'latest'})
        self.assertEqual(session.toolCalls[0]['output'], 'done')

    def test_packed_stream_is_not_duplicated_or_exposed_as_reasoning(self):
        self.append(dict(seq0=3, time0=1700000000000, type='text-chunks',
                         data=dict(texts=['Hello', ' world'], dt=[1], turn=1, step=0, index=0)))
        self.append(dict(seq0=5, time0=1700000000001, type='reasoning-chunks',
                         data=dict(texts=['PRIVATE_REASONING'], dt=[], turn=1, step=0, index=1)))
        self.append(dict(seq=6, type='assistant/message', surfaceOp='append', data=dict(message=dict(content=[
            dict(type='text', text='Hello world'), dict(type='reasoning', text='PRIVATE_REASONING')]))))
        result = self.adapter.readSession(self.path)
        self.assertEqual(str(result.messages).count('Hello world'), 1)
        self.assertNotIn('PRIVATE_REASONING', str(result.messages))

    def test_corrupt_compressed_source_is_isolated(self):
        folder = self.root / 'sessions/project/session-corrupt'
        folder.mkdir()
        (folder / 'session.jsonl.zstd').write_bytes(b'not zstandard')
        self.assertEqual(len(list(self.adapter.scan_metadata())), 1)
        self.assertTrue(self.adapter.scan_errors)

    def test_foreign_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            foreign = dsh(Path(tmp))
            with self.assertRaises(ValueError):
                self.adapter.readSession(foreign)

    def test_indexed_identity_change_requires_reselection(self):
        with self.assertRaises(ValueError):
            self.adapter.read_indexed({'sourcePath': str(self.path), 'sessionId': 'replaced-session'})
