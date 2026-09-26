import json
import tempfile
import unittest
from pathlib import Path

from agentref.adapters import CodexAdapter
from agentref.index import Index


class CodexTitleTests(unittest.TestCase):
    def test_saved_title_rename_and_cached_wrapper_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / "sessions"
            root.mkdir()
            source = root / "test.jsonl"
            records = [{"type": "session_meta", "payload": {"id": "test-id"}}]
            for message in ("<recommended_plugins>injected</recommended_plugins>",
                            "# AGENTS.md instructions\nInjected instructions",
                            "# Files mentioned\nfile.txt\n## My request:\n修复登录按钮的点击行为"):
                records.append({"type": "response_item", "payload": {
                    "type": "message", "role": "user", "content": message}})
            source.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
            original = source.read_bytes()
            index = Index(home / "index", [CodexAdapter([root])])
            try:
                index.refresh()
                row = index.sessions()[0]
                self.assertEqual(row["title"], "修复登录按钮的点击行为")
                index.db.execute("UPDATE sessions SET title='<recommended_plugins>'")
                index.db.commit()
                index.refresh()
                self.assertEqual(index.sessions()[0]["title"], row["title"])
                names = home / "session_index.jsonl"
                names.write_text(json.dumps({"id": "test-id", "thread_name": "登录功能验收"}) + "\n{broken\n", encoding="utf-8")
                self.assertEqual(index.sessions()[0]["title"], "登录功能验收")
                with names.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"id": "test-id", "thread_name": "新的会话名称"}) + "\n")
                self.assertEqual(index.refresh()["changed"], 0)
                self.assertEqual(index.sessions()[0]["title"], "新的会话名称")
                self.assertEqual(index.matches("新的会话名称", limit=1)[0]["title"], "新的会话名称")
                self.assertEqual(index.matches("登录功能验收", limit=1), [])
                self.assertEqual(index.sessions()[0]["ref"], row["ref"])
                self.assertEqual(source.read_bytes(), original)
            finally:
                index.close()

    def test_custom_root_does_not_load_parent_title_index(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "session_index.jsonl").write_text('{"id":"test","thread_name":"unrelated"}\n')
            self.assertEqual(CodexAdapter([home / "custom"]).saved_titles(), {})
