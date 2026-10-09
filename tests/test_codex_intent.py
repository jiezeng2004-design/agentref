"""Host metadata is evidence, not the user's continuation objective."""
import json
from pathlib import Path
import tempfile
import unittest

from agentref.adapters.codex import CodexAdapter
from agentref.context_render import CONTEXT_LIMIT
from agentref.handoff import build_context
from agentref.index import Index
from agentref.mcp import Server


def message(text):
    return {"type": "response_item", "payload": {
        "type": "message", "role": "user", "content": text}}


class CodexIntentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.path = self.source / "session.jsonl"
        self.adapter = CodexAdapter([self.source])

    def write(self, *records):
        self.path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n"
                                     for record in records), encoding="utf-8")
        return self.adapter.readSession(self.path)

    def test_injected_messages_do_not_replace_goal_latest_intent_or_turn_state(self):
        injected = (
            "# AGENTS.md instructions\nSynthetic working agreement",
            "<environment_context>synthetic workspace</environment_context>",
            "<recommended_plugins>synthetic inventory</recommended_plugins>",
            '<external_codex_apps_open_page>{"page_id":null}</external_codex_apps_open_page>',
        )
        records = [message(text) for text in injected[:3]]
        records += [message("Implement incremental search"), message("Keep the existing API"),
                    {"type": "event_msg", "payload": {"type": "task_complete"}},
                    message(injected[-1])]
        session = self.write(*records)
        self.assertEqual(session.originalGoal, "Implement incremental search")
        self.assertEqual(session.latestUserRequest, "Keep the existing API")
        self.assertEqual(session.latestAgentState, "turn-ended")
        self.assertEqual(session.title, "Implement incremental search")
        for text in injected:
            self.assertIn({"role": "context", "text": text}, session.messages)

    def test_wrapped_request_preserves_full_intent_and_raw_provenance(self):
        original = "Implement incremental search\nPreserve this literal heading:\n## My request:\nexample"
        wrapped = "# Files mentioned\r\nsynthetic.py\r\n## My request:\r\n" + original
        session = self.write(message(wrapped))
        self.assertEqual(session.originalGoal, original)
        self.assertEqual(session.latestUserRequest, original)
        self.assertEqual(session.messages, [{"role": "user", "text": wrapped}])
        self.assertEqual(session.title, original.splitlines()[0])

    def test_host_metadata_cannot_evict_recent_conversation_from_handoff(self):
        injected = "<external_codex_apps_open_page>{\"page_id\":null}</external_codex_apps_open_page>"
        session = self.write(message("Preserve register and implement rollback"),
                             {"type": "response_item", "payload": {"type": "message",
                              "role": "assistant", "content": "Register is implemented; rollback remains."}},
                             *(message(injected) for _ in range(20)))
        context = build_context(session)
        recent = json.loads(context.split("## Relevant Recent Conversation\n", 1)[1])
        self.assertEqual([entry["role"] for entry in recent["messages"]], ["user", "assistant"])
        self.assertIn("rollback remains", recent["messages"][-1]["text"])
        self.assertEqual(recent["hostContextMessagesExcluded"], 20)
        self.assertEqual(len(session.messages), 22)

    def test_actual_markup_and_quoted_request_heading_are_user_intent(self):
        for text in ("<task>Implement XML export</task>",
                     "You are helping implement a parser.",
                     "Document this heading:\n```markdown\n## My request:\nexample\n```"):
            with self.subTest(text=text):
                session = self.write(message(text))
                self.assertEqual(session.originalGoal, text)
                self.assertEqual(session.latestUserRequest, text)
                self.assertEqual(session.messages[0]["role"], "user")

    def test_metadata_only_session_does_not_invent_a_user_objective(self):
        session = self.write(message("# AGENTS.md instructions\nSynthetic rules"))
        self.assertEqual(session.originalGoal, "")
        self.assertEqual(session.latestUserRequest, "")
        self.assertEqual(session.latestAgentState, "unknown")

    def test_warm_index_and_selected_mcp_resource_deliver_correct_objectives(self):
        self.write(message("# AGENTS.md instructions\nSynthetic rules"),
                   message("# Files mentioned\nexample.py\n## My request:\nImplement search\nKeep rollback"))
        before = self.path.read_bytes()
        index = Index(self.root / "index", [self.adapter])
        self.addCleanup(index.close)
        index.refresh()
        self.assertEqual(index.refresh()["bytesRead"], 0)
        ref = index.sessions()[0]["ref"]
        server = Server(index, agent="codex")
        result = server.dispatch("resources/read", {"uri": "agentref://session/" + ref})
        context = result["contents"][0]["text"]
        self.assertIn("## Original Goal\nImplement search\nKeep rollback\n", context)
        self.assertIn("## Latest User Intent\nImplement search\nKeep rollback\n", context)
        self.assertLessEqual(len(context), CONTEXT_LIMIT)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(context, build_context(index.read(index.sessions()[0])))
