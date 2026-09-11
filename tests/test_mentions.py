import json
import os
import tempfile
import unittest
from pathlib import Path

from agentref.adapters import ClaudeAdapter, CodexAdapter
from agentref.index import Index
from agentref.mcp import Server, SESSION_TEMPLATE
from agentref.mentions import label, resource_ref


class MentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.paths = []
        for i, timestamp in enumerate(("2026-09-01T01:00:00Z", "2026-09-05T01:00:00Z")):
            for agent in ("claude", "codex"):
                folder = self.sources / agent
                folder.mkdir(exist_ok=True)
                path = folder / f"{i}.jsonl"
                sid = f"{agent}-session-{i}"
                if agent == "claude":
                    records = [{"type": "user", "sessionId": sid, "timestamp": timestamp,
                                "message": {"role": "user", "content": "登录修复 " + str(i)}}]
                else:
                    records = [{"type": "session_meta", "timestamp": timestamp, "payload": {"id": sid}},
                               {"type": "response_item", "timestamp": timestamp,
                                "payload": {"type": "message", "role": "user", "content": [
                                    {"type": "input_text", "text": "登录修复 " + str(i)}]}}]
                path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
                # The older session was copied more recently: transcript time must win.
                os.utime(path, (2000000000 - i, 2000000000 - i))
                self.paths.append(path)
        self.index = Index(self.root / "index", [ClaudeAdapter([self.sources / "claude"]),
                                                CodexAdapter([self.sources / "codex"])])
        self.addCleanup(self.index.close)

    def test_native_menu_contract_and_both_agent_boundaries(self):
        before = {p: p.read_bytes() for p in self.paths}
        self.index.read = lambda row: self.fail("candidate browsing must not read full context")
        for agent in ("claude", "codex"):
            server = Server(self.index, agent=agent)
            tool = next(t for t in server.dispatch("tools/list", {})["tools"] if t["name"] == "search_mentions")
            self.assertEqual(tool["_meta"]["openai/extensions"]["mentions/search"], {})
            response = server.dispatch("tools/call", {"name": "search_mentions", "arguments": {"query": "", "path": []}})
            items = response["structuredContent"]["items"]
            self.assertEqual(len(items), 2)
            self.assertEqual(set(response["structuredContent"]), {"items"})
            self.assertEqual(json.loads(response["content"][0]["text"]),
                             {**response["structuredContent"], **response["_meta"]})
            self.assertTrue(all(i["type"] == "resource" for i in items))
            self.assertTrue(all(resource_ref(i["resourceUri"]).startswith(agent + ":") for i in items))
            self.assertIn("登录修复 1", items[0]["title"])
            self.assertIn("登录修复 0", items[1]["title"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.paths})

    def test_search_and_no_match(self):
        server = Server(self.index, agent="claude")
        self.assertEqual(len(server.mention_items({"query": "登录修复 1"})["items"]), 1)
        self.assertEqual(server.mention_items({"query": "codex:codex-session"})["items"], [])
        self.assertEqual(server.mention_items({"query": "not-found"})["items"], [])

    def test_selected_resource_and_legacy_uri(self):
        for agent in ("claude", "codex"):
            server = Server(self.index, agent=agent)
            resource = server.dispatch("resources/list", {})["resources"][0]
            self.assertEqual(resource["description"], "登录修复 1")
            self.assertIn("登录修复 1", resource["description"])
            uri = resource["uri"]
            original = server.dispatch("resources/read", {"uri": uri})["contents"][0]["text"]
            legacy = server.dispatch("resources/read", {"uri": uri.split("?")[0]})["contents"][0]["text"]
            self.assertEqual(original, legacy)
            self.assertIn("登录修复 1", original)
            self.assertIn("Continuation Policy", original)

    def test_bad_uri_and_query_fail_closed(self):
        server = Server(self.index, agent="claude")
        for uri in ("file:///secrets", "agentref://session/../../secret", "agentref://other/claude:id"):
            with self.assertRaises(ValueError):
                server.dispatch("resources/read", {"uri": uri})
        result = server.dispatch("tools/call", {"name": "search_mentions", "arguments": {"query": 2}})
        self.assertTrue(result["isError"])

    def test_label_is_short_and_single_line(self):
        row = {"updatedAt": "2026-09-05T01:00:00Z", "title": "x\n\x1b\u202e" * 80, "sessionId": "abcd"}
        value = label(row)
        self.assertLess(len(value), 70)
        for control in ("\n", "\x1b", "\u202e"):
            self.assertNotIn(control, value)

    def test_equal_timestamps_have_stable_order(self):
        self.index.refresh()
        first = [r["ref"] for r in self.index.sessions()]
        self.index.refresh()
        self.assertEqual(first, [r["ref"] for r in self.index.sessions()])

    def test_unnamed_dsh_labels_distinguish_sessions_without_body(self):
        row = dict(agent="dsh", title="未命名 DSH 会话", cwd=r"D:\projects\agentref",
                   updatedAt="2026-09-10T06:32:00Z", sessionId="session-common-prefix-a")
        first = label(row)
        second = label(dict(row, sessionId="session-common-prefix-b"))
        self.assertTrue(first.startswith("agentref · 09-10 "))
        self.assertNotEqual(first, second)
        self.assertEqual(first, label(row, rank=9))
        self.assertEqual(label(dict(row, title="Saved title")), "Saved title")
        self.assertEqual(label(dict(row, agent="claude")), "未命名 DSH 会话")
        long = label(dict(row, cwd="/projects/" + "x" * 100))
        self.assertTrue(long.endswith(first.rsplit(" · ", 1)[1]))
        self.assertLess(len(long), 50)
        missing = label(dict(row, cwd=None, updatedAt="invalid"))
        self.assertTrue(missing.startswith("DSH · 时间未知 · "))

    def test_all_agents_unnamed_mentions_keep_exact_resource(self):
        names = dict(claude="Claude", codex="Codex", grok="Grok", opencode="OpenCode",
                     antigravity="Antigravity", dsh="DSH")
        for agent, name in names.items():
            for title in (None, "", " \n", "未命名会话", f"未命名 {name} 会话", "session-a"):
                with self.subTest(agent=agent, title=title):
                    rows = [dict(agent=agent, title=title, sessionId="session-a",
                                 ref=agent + ":abc123", cwd="", updatedAt="invalid")]
                    server = Server(self.index, agent=agent)
                    server.refresh = lambda: None
                    server.rows = lambda **kwargs: rows
                    self.index.read = lambda row: self.fail("labels must not read context")
                    item = server.mention_items({"query": ""})["items"][0]
                    self.assertTrue(item["title"].startswith(name + " · 时间未知 · "))
                    self.assertEqual(resource_ref(item["resourceUri"]), rows[0]["ref"])
                    self.assertNotEqual(item["title"], label(dict(rows[0], ref=agent + ":def456")))
                    self.assertEqual(label(dict(rows[0], title="My saved title")), "My saved title")
                    self.assertEqual(label(dict(rows[0], title="未命名会话的修复")), "未命名会话的修复")

    def test_claude_dynamic_completion_selects_exact_resource(self):
        server = Server(self.index, agent="codex", template_menu=True)
        self.assertEqual(server.dispatch("resources/list", {})["resources"], [])
        template = server.dispatch("resources/templates/list", {})["resourceTemplates"][0]
        result = server.dispatch("completion/complete", {"ref": {"type": "ref/resource", "uri": template["uriTemplate"]},
                                                        "argument": {"name": "session", "value": ""}})["completion"]
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["values"], ["登录修复_1", "登录修复_0"])
        for value in result["values"]:
            self.assertTrue(all(c.isalnum() or c in "_~" for c in value))
        uri = SESSION_TEMPLATE.replace("{session}", result["values"][0])
        content = server.dispatch("resources/read", {"uri": uri})["contents"][0]["text"]
        self.assertIn("登录修复 1", content)
        # Rank/title changes must not redirect a previously inserted reference.
        self.index.db.execute("UPDATE sessions SET title='renamed'")
        self.index.db.commit()
        self.assertEqual(content, server.dispatch("resources/read", {"uri": uri})["contents"][0]["text"])

    def test_completion_browsing_does_not_read_transcripts(self):
        server = Server(self.index, agent="codex", template_menu=True)
        self.index.read = lambda row: self.fail("completion must only use metadata")
        result = server.dispatch("completion/complete", {"ref": {"type": "ref/resource", "uri": SESSION_TEMPLATE},
                                                        "argument": {"name": "session", "value": "登录修复 1"}})
        self.assertEqual(result["completion"]["total"], 1)
        with self.assertRaises(ValueError):
            server.dispatch("resources/read", {"uri": "agentref://session/label~123"})

    def test_completion_resource_cannot_cross_agent_boundary(self):
        server = Server(self.index, agent="codex", template_menu=True)
        self.index.refresh()
        foreign_token = self.index.sessions("claude")[0]["ref"].split(":", 1)[1]
        with self.assertRaises(ValueError):
            server.dispatch("resources/read", {"uri": "agentref://session/label~" + foreign_token})

    def test_duplicate_name_aliases_survive_rename_and_restart(self):
        self.index.refresh()
        self.index.db.execute("UPDATE sessions SET title='相同名称' WHERE agent='codex'")
        self.index.db.commit()
        rows = self.index.sessions("codex")
        aliases = self.index.mention_aliases(rows)
        self.assertEqual(list(aliases.values()), ["相同名称", "相同名称_2"])
        other = Index(self.root / "index", list(self.index.adapters.values()))
        try:
            self.assertEqual(other.mention_aliases(list(reversed(rows))), aliases)
            renamed = [dict(rows[0], title="新名称"), rows[1]]
            self.assertEqual(other.mention_aliases(renamed)[rows[0]["ref"]], "新名称")
            stored = other.db.execute("SELECT ref FROM mention_aliases WHERE agent='codex' AND alias='相同名称'").fetchone()[0]
            self.assertEqual(stored, rows[0]["ref"])
        finally:
            other.close()
