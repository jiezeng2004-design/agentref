import json
from pathlib import Path
import tempfile
import unittest

from agentref.adapters.dsh import DshAdapter
from agentref.index import Index


class DshV3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'sessions/project/native'
        self.folder.mkdir(parents=True)
        self.adapter = DshAdapter([self.root])

    def write(self, events, version=3, **fields):
        header = dict(type='session', version=version, id='native', createdAt=1700000000000,
                      cwd=str(self.root), isSeeded=False, delegationDepth=0)
        header.update(fields)
        path = self.folder / f'session.v{version}.jsonl'
        path.write_text(''.join(json.dumps(row) + '\n' for row in [header, *events]), encoding='utf-8')
        return path

    def user(self, seq=0, text='Complete rollback', **extra):
        return dict(seq=seq, type='user/message', surfaceOp='append',
                    data=dict(source=dict(kind='user'), content=[dict(type='text', text=text)]), **extra)

    def test_real_v3_shape_reads_wrapped_tool_result_and_excludes_embedded_reasoning(self):
        events = [self.user(),
                  dict(seq=1, type='system/message', surfaceOp='append',
                       data=dict(message=dict(content=[dict(type='text', text='SYSTEM_ONLY')]))),
                  dict(seq=2, type='assistant/message', surfaceOp='append', data=dict(
                      message=dict(content=[dict(type='text', text='Public answer'),
                                            dict(type='reasoning', text='PRIVATE_REASONING')]),
                      stream=[dict(type='reasoning-chunks', texts=['PRIVATE_REASONING'])])),
                  dict(seq=3, type='tool/call', data=dict(callId='t', name='shell', arguments='{}')),
                  dict(seq=4, type='tool/result', surfaceOp='append', sourceEventSeqs=[3],
                       data=dict(message=dict(content=[dict(type='tool-result', toolCallId='t',
                           content=[dict(type='text', text='Process exited with code 0')], isError=False)]))),
                  dict(seq=5, type='tool/call', data=dict(callId='pending', name='shell', arguments='{}'))]
        session = self.adapter.readSession(self.write(events))
        self.assertEqual(session.originalGoal, 'Complete rollback')
        self.assertEqual(session.toolCalls[0]['status'], 'COMPLETED')
        self.assertEqual(session.toolCalls[1]['status'], 'UNCERTAIN')
        self.assertEqual(session.latestAgentState, 'incomplete')
        self.assertNotIn('PRIVATE_REASONING', str(session.messages))
        self.assertNotIn('SYSTEM_ONLY', str(session.messages))

    def test_v3_compressed_read_and_metadata_do_not_change_source(self):
        path = self.write([self.user()])
        try:
            from compression import zstd
            compressed = zstd.compress(path.read_bytes())
        except ImportError:
            import zstandard
            compressed = zstandard.ZstdCompressor().compress(path.read_bytes())
        target = path.with_suffix('.jsonl.zstd')
        target.write_bytes(compressed)
        self.assertEqual(self.adapter.metadata(target).sessionId, 'native')
        self.assertEqual(self.adapter.readSession(target).originalGoal, 'Complete rollback')
        self.assertEqual(target.read_bytes(), compressed)

    def test_v3_compaction_requires_sources_and_excludes_replaced_goal(self):
        replacement = dict(seq=1, type='user/message', surfaceOp=dict(op='replace', startSeq=0, endSeq=0),
                           sourceEventSeqs=[0], data=dict(source=dict(kind='plugin'),
                           content=[dict(type='text', text='Historical summary')]))
        session = self.adapter.readSession(self.write([self.user(), replacement]))
        self.assertEqual(session.originalGoal, '')
        self.assertNotIn('Complete rollback', str(session.messages))
        replacement['sourceEventSeqs'] = []
        with self.assertRaisesRegex(ValueError, 'source references'):
            self.adapter.readSession(self.write([self.user(), replacement]))

    def test_v3_header_and_top_level_packed_stream_fail_closed(self):
        for fields in [dict(isSeeded=1), dict(delegationDepth=True), dict(delegationDepth=-1)]:
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'header'):
                self.adapter.readSession(self.write([self.user()], **fields))
        packed = dict(type='text-chunks', seq0=0, data=dict(texts=['unsupported'], dt=[]))
        with self.assertRaisesRegex(ValueError, 'embedded'):
            self.adapter.readSession(self.write([packed]))

    def test_v3_to_v4_upgrade_requires_reselection_and_future_generation_stays_closed(self):
        self.write([self.user()])
        with tempfile.TemporaryDirectory() as cache:
            index = Index(Path(cache), [self.adapter])
            try:
                index.refresh()
                row = index.sessions('dsh')[0]
                self.write([self.user(text='New v4 goal')], version=4)
                with self.assertRaisesRegex(ValueError, 'generation changed'):
                    self.adapter.read_indexed(row)
                self.assertFalse(index.refresh()['errors'])
                self.assertEqual(Path(index.sessions('dsh')[0]['sourcePath']).name, 'session.v4.jsonl')
                self.write([self.user()], version=5)
                self.assertEqual(list(self.adapter.scan_metadata()), [])
                self.assertTrue(self.adapter.scan_errors)
            finally:
                index.close()


if __name__ == '__main__':
    unittest.main()
