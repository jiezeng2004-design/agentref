import json
from pathlib import Path
import tempfile
import unittest

from agentref.adapters.dsh import DshAdapter
from agentref.index import Index


class DshGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'sessions/project/native'
        self.folder.mkdir(parents=True)
        self.adapter = DshAdapter([self.root])

    def write(self, version=4, events=None, name=None):
        header = dict(type='session', version=version, id='native', createdAt=1700000000000,
                      cwd=str(self.root), isSeeded=False, delegationDepth=0)
        if events is None:
            events = [dict(seq=0, type='user/message', surfaceOp='append', data=dict(
                source=dict(kind='user'), content=[dict(type='text', text=f'Goal v{version}')]))]
        path = self.folder / (name or (f'session.v{version}.jsonl' if version else 'session.jsonl'))
        path.write_text(''.join(json.dumps(row) + '\n' for row in [header, *events]), encoding='utf-8')
        return path

    def test_newest_generation_selected_without_changing_sources(self):
        old = self.write(0)
        new = self.write(4)
        original = {path: path.read_bytes() for path in (old, new)}
        (self.folder / 'session.v04.jsonl').write_text('staging', encoding='utf-8')
        (self.folder / 'session.v99.jsonl.tmp').write_text('staging', encoding='utf-8')
        sessions = list(self.adapter.scan_metadata())
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].sourcePath, str(new))
        self.assertEqual(self.adapter.readSession(new).originalGoal, 'Goal v4')
        self.assertEqual({path: path.read_bytes() for path in original}, original)

    def test_unknown_newer_generation_refused_without_old_fallback(self):
        self.write(4)
        self.write(5)
        self.assertEqual(list(self.adapter.scan_metadata()), [])
        self.assertTrue(self.adapter.scan_errors)

    def test_filename_header_disagreement_refused(self):
        path = self.write(4, name='session.jsonl')
        with self.assertRaisesRegex(ValueError, 'filename and header'):
            self.adapter.readSession(path)

    def test_index_reselection_required_when_generation_changes(self):
        old = self.write(0)
        with tempfile.TemporaryDirectory() as cache:
            index = Index(Path(cache), [self.adapter])
            try:
                index.refresh()
                row = index.sessions('dsh')[0]
                self.assertEqual(row['sourcePath'], str(old))
                new = self.write(4)
                with self.assertRaisesRegex(ValueError, 'generation changed'):
                    self.adapter.read_indexed(row)
                self.assertFalse(index.refresh()['errors'])
                self.assertEqual(len(index.sessions('dsh')), 1)
                self.assertEqual(index.sessions('dsh')[0]['sourcePath'], str(new))
            finally:
                index.close()

    def test_mixed_encoding_is_refused(self):
        self.write(0)
        self.write(4, name='session.v4.jsonl.zstd')
        self.assertEqual(list(self.adapter.scan_metadata()), [])
        self.assertTrue(self.adapter.scan_errors)

    def test_v4_compaction_uses_seq_names_and_requires_shadowed_sources(self):
        first = dict(seq=0, type='user/message', surfaceOp='append', data=dict(
            source=dict(kind='user'), content=[dict(type='text', text='Old goal')]))
        replacement = dict(seq=1, type='user/message', sourceEventSeqs=[0],
            surfaceOp=dict(op='replace', startSeq=0, endSeq=0), data=dict(
                source=dict(kind='plugin'), content=[dict(type='text', text='Summary')]))
        path = self.write(events=[first, replacement])
        session = self.adapter.readSession(path)
        self.assertNotIn('Old goal', str(session.messages))
        self.assertEqual(session.originalGoal, '')
        replacement['sourceEventSeqs'] = []
        self.write(events=[first, replacement])
        with self.assertRaisesRegex(ValueError, 'source references'):
            self.adapter.readSession(path)

    def test_v4_tool_result_message_shape_and_reasoning_exclusion(self):
        events = [dict(seq=0, type='assistant/message', surfaceOp='append', data=dict(
            message=dict(content=[dict(type='text', text='Public answer'),
                                  dict(type='reasoning', text='HIDDEN_REASONING'),
                                  dict(type='tool-call', id='t', name='shell', arguments='{}')]),
            stream=[dict(type='reasoning-chunks', texts=['HIDDEN_REASONING'])])),
            dict(seq=1, type='tool/call', data=dict(callId='t', name='shell', arguments='{}')),
            dict(seq=2, type='tool/result', surfaceOp='append', data=dict(message=dict(
                toolCallId='t', isError=True, content=[dict(type='text', text='Failed command')]))),
            dict(seq=3, type='turn/end', data=dict(reason=dict(kind='completed')))]
        session = self.adapter.readSession(self.write(events=events))
        self.assertEqual(session.toolCalls[0]['status'], 'FAILED')
        self.assertEqual(session.toolCalls[0]['output'], 'Failed command')
        self.assertNotIn('HIDDEN_REASONING', str(session.messages))
        self.assertEqual(session.latestAgentState, 'turn_ended')

    def test_system_and_developer_messages_do_not_become_user_goals(self):
        events = [dict(seq=i, type=kind, surfaceOp='append', data=dict(message=dict(
            content=[dict(type='text', text=kind)]))) for i, kind in enumerate(
                ['system/message', 'developer/message'])]
        session = self.adapter.readSession(self.write(events=events))
        self.assertEqual(session.originalGoal, '')
        self.assertNotIn('system/message', str(session.messages))
        self.assertIn('Historical developer context', str(session.messages))


if __name__ == '__main__':
    unittest.main()
