import json
import os
import tempfile
import unittest
from unittest.mock import call, patch
from pathlib import Path

from agentref.adapters import ClaudeAdapter, CodexAdapter
from agentref.index import Index, _mention_alias_base
from agentref.mcp import Server, SESSION_TEMPLATE
from agentref.mentions import label, resource_ref, short_text


class MentionTests(unittest.TestCase):
    def test_fast_mention_alias_base_matches_previous_normalization(self):
        values = ("Synthetic title 123", "  多余   空格  ", "emoji 😀 and text",
                  "line\nbreak", "tab\tseparator", "format\u200bcharacter", "___",
                  "长标题" * 100, None, ["list", "value"])
        for value in values:
            with self.subTest(value=value):
                expected = "".join(char if char.isalnum() else "_"
                                   for char in short_text(value, 200)).strip("_")[:36] or "未命名会话"
                self.assertEqual(_mention_alias_base(value), expected)

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

    def test_mention_items_requests_a_bounded_page_with_total(self):
        server = Server(self.index, agent="claude")
        server.refresh = lambda: None
        base = dict(agent="claude", title="Synthetic", cwd="", updatedAt="2026-09-24T00:00:00Z",
                    latestAgentState="unknown")
        rows = [dict(base, ref=f"claude:{n:016x}") for n in range(100)]
        with unittest.mock.patch.object(self.index, "matches", return_value=(rows, 120)) as match:
            result = server.mention_items({"query": "Synthetic"})
        match.assert_called_once_with("Synthetic", "claude", limit=100, offset=0, include_total=True)
        self.assertEqual(len(result["items"]), 100)
        self.assertEqual(result["total"], 120)
        self.assertTrue(result["hasMore"])

    def test_selected_resource_and_legacy_uri(self):
        for agent in ("claude", "codex"):
            server = Server(self.index, agent=agent)
            resource = server.dispatch("resources/list", {})["resources"][0]
            self.assertTrue(resource["description"].startswith("登录修复 1 · "))
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

    def test_resources_list_uses_bounded_sql_pages(self):
        rows = [dict(agent="claude", ref=f"claude:{i:016x}", title=f"Synthetic {i}", cwd="",
                     updatedAt="2026-09-24T00:00:00Z", latestAgentState="unknown") for i in range(101)]
        server = Server(self.index, agent="claude")
        server.refresh = lambda: None
        calls = []

        def page(agent=None, limit=None, offset=0):
            calls.append((agent, limit, offset))
            return rows[offset:offset + limit]

        with patch.object(self.index, "sessions", side_effect=page):
            first = server.dispatch("resources/list", {"cursor": "0"})
            second = server.dispatch("resources/list", {"cursor": "100"})
        self.assertEqual(len(first["resources"]), 100)
        self.assertEqual(first["nextCursor"], "100")
        self.assertEqual(len(second["resources"]), 1)
        self.assertNotIn("nextCursor", second)
        self.assertEqual(calls, [("claude", 101, 0), ("claude", 101, 100)])

    def test_unnamed_dsh_labels_distinguish_sessions_without_body(self):
        row = dict(agent="dsh", title="未命名 DSH 会话", cwd=r"D:\projects\agentref",
                   updatedAt="2026-09-10T06:32:00Z", sessionId="session-common-prefix-a")
        first = label(row)
        second = label(dict(row, sessionId="session-common-prefix-b"))
        self.assertTrue(first.startswith("agentref · 09-10 "))
        self.assertNotEqual(first, second)
        self.assertEqual(first, label(row, rank=9))
        self.assertTrue(label(dict(row, title="Saved title")).startswith("Saved title · 09-10 "))
        self.assertTrue(label(dict(row, agent="claude")).startswith("未命名 DSH 会话 · 09-10 "))
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
                    server.rows = lambda **kwargs: (rows, len(rows)) if kwargs.get("include_total") else rows
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
        self.assertNotIn("description", template)
        with patch.object(self.index, "sessions", wraps=self.index.sessions) as sessions:
            result = server.dispatch("completion/complete", {"ref": {"type": "ref/resource", "uri": template["uriTemplate"]},
                                                            "argument": {"name": "session", "value": ""}})["completion"]
        self.assertEqual(sessions.call_args_list,
                         [call("codex"), call("codex", limit=100, offset=0)])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["values"], ["登录修复_1", "登录修复_0"])
        for value in result["values"]:
            self.assertTrue(all(c.isalnum() or c in "_~" for c in value))
        with patch.object(self.index, "sessions", side_effect=AssertionError("completion inventory should be cached")):
            cached_result = server.dispatch(
                "completion/complete",
                {"ref": {"type": "ref/resource", "uri": template["uriTemplate"]},
                 "argument": {"name": "session", "value": "登录修复 1"}})["completion"]
        self.assertEqual(cached_result["total"], 1)
        self.assertEqual(cached_result["values"], ["登录修复_1"])
        trailing_space = server.dispatch(
            "completion/complete",
            {"ref": {"type": "ref/resource", "uri": template["uriTemplate"]},
             "argument": {"name": "session", "value": "登录修复 1 "}})["completion"]
        self.assertEqual(trailing_space["total"], 0)
        uri = SESSION_TEMPLATE.replace("{session}", result["values"][0])
        content = server.dispatch("resources/read", {"uri": uri})["contents"][0]["text"]
        self.assertIn("登录修复 1", content)
        # Rank/title changes must not redirect a previously inserted reference.
        self.index.db.execute("UPDATE sessions SET title='renamed'")
        self.index.db.commit()
        renamed = server.dispatch(
            "completion/complete",
            {"ref": {"type": "ref/resource", "uri": template["uriTemplate"]},
             "argument": {"name": "session", "value": "renamed"}})["completion"]
        self.assertEqual(renamed["total"], 2)
        self.assertEqual(renamed["values"], ["renamed", "renamed_2"])
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

    def test_empty_alias_inventory_handles_cross_title_suffix_collisions(self):
        rows = [dict(agent="claude", ref=f"claude:{n:016x}", title=title)
                for n, title in enumerate(("same", "same_2", "same"), 1)]
        self.assertEqual(list(self.index.mention_aliases(rows).values()),
                         ["same", "same_2", "same_3"])

    def test_duplicate_alias_reuse_batches_numbered_owner_reads(self):
        rows = [dict(agent="claude", ref=f"claude:{n:016x}", title="shared title")
                for n in range(1, 1201)]
        first = self.index.mention_aliases(rows)
        statements = []
        self.index.db.set_trace_callback(statements.append)
        second = self.index.mention_aliases(rows)
        reversed_result = self.index.mention_aliases(list(reversed(rows)))
        reads = [statement for statement in statements
                 if "FROM mention_aliases" in statement and "INSERT" not in statement]
        self.assertEqual(second, first)
        self.assertEqual(reversed_result, first)
        self.assertLessEqual(len(reads), 10)

    def test_long_reserved_alias_suffixes_are_probed_in_batches(self):
        base = "historic_name"
        self.index.db.executemany(
            "INSERT INTO mention_aliases(agent,alias,ref) VALUES (?,?,?)",
            [("claude", base, "claude:0000000000000001")]
            + [("claude", f"{base}_{n}", f"claude:{n:016x}") for n in range(2, 2501)])
        self.index.db.commit()
        row = dict(agent="claude", ref="claude:ffffffffffffffff", title="historic name")
        statements = []
        self.index.db.set_trace_callback(statements.append)
        alias = self.index.mention_aliases([row])[row["ref"]]
        reads = [statement for statement in statements if "SELECT alias,ref" in statement]
        self.assertEqual(alias, "historic_name_2501")
        self.assertLessEqual(len(reads), 7)

    def test_reused_suffix_cursor_preserves_the_first_available_gap(self):
        existing = [("same", "claude:0000000000000001"),
                    ("same_2", "claude:0000000000000002"),
                    ("same_4", "claude:0000000000000004")]
        self.index.db.executemany(
            "INSERT INTO mention_aliases(agent,alias,ref) VALUES (?,?,?)",
            [("claude", alias, ref) for alias, ref in existing])
        rows = [dict(agent="claude", ref=ref, title="same")
                for ref in ("claude:0000000000000002", "claude:0000000000000004",
                            "claude:ffffffffffffffff")]
        allocated = self.index.mention_aliases(rows)
        self.assertEqual(allocated, {rows[0]["ref"]: "same_2",
                                     rows[1]["ref"]: "same_4",
                                     rows[2]["ref"]: "same_3"})

    def test_mention_alias_inventory_invalidates_when_codex_titles_change(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            sessions = home / "sessions"
            sessions.mkdir()
            (sessions / "session.jsonl").write_text(
                json.dumps({"type": "session_meta", "payload": {"id": "saved-id"}}) + "\n"
                + json.dumps({"type": "response_item", "payload": {"type": "message", "role": "user",
                              "content": [{"type": "input_text", "text": "Build the local index"}]}}) + "\n",
                encoding="utf-8")
            index = Index(home / "index", [CodexAdapter([sessions])])
            try:
                index.refresh()
                row = index.sessions("codex")[0]
                first = index.mention_alias_inventory("codex")
                self.assertEqual(first[row["ref"]], "Build_the_local_index")

                (home / "session_index.jsonl").write_text(
                    json.dumps({"id": "saved-id", "thread_name": "Pinned title"}) + "\n",
                    encoding="utf-8")
                updated = index.mention_alias_inventory("codex")
                self.assertEqual(updated[row["ref"]], "Pinned_title")
            finally:
                index.close()

    def test_large_alias_inventory_uses_ordered_batches(self):
        self.index.refresh()
        with patch("agentref.index.ALIAS_INVENTORY_STREAM_THRESHOLD", 0), \
                patch.object(self.index, "sessions", side_effect=AssertionError("large inventory should stream")):
            self.index.ensure_mention_alias_inventory("codex")
        self.assertEqual(self.index.db.execute(
            "SELECT count(*) FROM mention_aliases WHERE agent='codex'").fetchone()[0], 2)

    def test_streamed_alias_inventory_keeps_suffix_cursor_across_batches(self):
        self.index.db.execute(
            "INSERT INTO mention_aliases(agent,alias,ref) VALUES (?,?,?)",
            ("claude", "historic", "claude:ffffffffffffffff"))
        self.index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            (f"claude:{n:016x}", "claude", f"session-{n}", "shared title", "", "",
             "2026-01-01T00:00:00Z", f"synthetic::{n}", "unknown", n, 0, 0, "", 0)
            for n in range(1, 7)))
        self.index.db.commit()
        with patch("agentref.index.ALIAS_INVENTORY_STREAM_THRESHOLD", 0), \
                patch("agentref.index.ALIAS_INVENTORY_BATCH_SIZE", 2):
            self.index.ensure_mention_alias_inventory("claude")
        aliases = dict(self.index.db.execute(
            "SELECT ref,alias FROM mention_aliases WHERE agent='claude' AND alias LIKE 'shared_title%'"))
        ordered_refs = [row["ref"] for row in self.index.sessions("claude")]
        self.assertEqual([aliases[ref] for ref in ordered_refs],
                         ["shared_title", "shared_title_2", "shared_title_3",
                          "shared_title_4", "shared_title_5", "shared_title_6"])

    def test_empty_streamed_inventory_keeps_cross_title_suffix_ownership(self):
        rows = [("claude:0000000000000003", "session-3", "same"),
                ("claude:0000000000000002", "session-2", "same_2"),
                ("claude:0000000000000001", "session-1", "same")]
        self.index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            (ref, "claude", session_id, title, "", "", "2026-01-01T00:00:00Z", ref,
             "unknown", n, 0, 0, "", 0)
            for n, (ref, session_id, title) in enumerate(rows)))
        self.index.db.commit()
        with patch("agentref.index.ALIAS_INVENTORY_STREAM_THRESHOLD", 0), \
                patch("agentref.index.ALIAS_INVENTORY_BATCH_SIZE", 2):
            self.index.ensure_mention_alias_inventory("claude")
        aliases = dict(self.index.db.execute(
            "SELECT ref,alias FROM mention_aliases WHERE agent='claude'"))
        self.assertEqual(aliases, {rows[0][0]: "same", rows[1][0]: "same_2",
                                   rows[2][0]: "same_3"})

    def test_activity_timestamp_refresh_keeps_alias_inventory_warm(self):
        path = next(path for path in self.paths
                    if path.parent.name == "codex" and path.name == "1.jsonl")
        self.index.refresh()
        self.index.mention_alias_inventory("codex")
        before = self.index._mention_alias_inventory_cache[("codex",)][0]
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "type": "response_item", "timestamp": "2026-09-06T01:00:00Z",
                "payload": {"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": "Recent activity"}]},
            }) + "\n")

        stats = self.index.refresh()
        self.assertGreater(stats["changed"], 0)
        after = self.index._mention_alias_inventory_cache[("codex",)][0]
        self.assertNotEqual(before[0], after[0])
        with patch.object(self.index, "sessions", side_effect=AssertionError("non-alias activity must not rebuild inventory")):
            self.index.ensure_mention_alias_inventory("codex")
        self.assertTrue(self.index.mention_alias_inventory_is_current("codex"))

    def test_single_title_refresh_updates_only_changed_alias_refs(self):
        path = next(path for path in self.paths
                    if path.parent.name == "codex" and path.name == "1.jsonl")
        self.index.refresh()
        aliases = self.index.mention_alias_inventory("codex")
        row = next(item for item in self.index.sessions("codex") if item["sourcePath"] == str(path.resolve()))
        path.write_text(path.read_text(encoding="utf-8").replace(
            r"\u767b\u5f55\u4fee\u590d 1", "Revised request 1"), encoding="utf-8")
        self.assertGreater(self.index.refresh()["changed"], 0)
        with patch.object(self.index, "sessions", side_effect=AssertionError("single-row change must not rebuild all aliases")):
            updated = self.index.mention_alias_inventory("codex")
        self.assertEqual(updated[row["ref"]], "Revised_request_1")
        self.assertEqual(set(updated) - set(aliases), set())

    def test_alias_allocator_reads_only_candidate_aliases(self):
        self.index.refresh()
        self.index.db.executemany(
            "INSERT INTO mention_aliases(agent,alias,ref) VALUES (?,?,?)",
            [("claude", f"historic_{n}", f"claude:{n:016x}") for n in range(1200)])
        self.index.db.commit()
        rows = [dict(agent="claude", ref="claude:ffffffffffffffff", title="current title")]
        statements = []
        self.index.db.set_trace_callback(statements.append)
        aliases = self.index.mention_aliases(rows)
        self.assertEqual(len(aliases), len(rows))
        reads = [statement for statement in statements if "FROM mention_aliases" in statement
                 and "INSERT" not in statement and "SELECT 1 FROM mention_aliases" not in statement]
        self.assertEqual(len(reads), 1)
        self.assertIn("AND alias IN", reads[0])
        self.assertNotIn("WHERE agent IN", reads[0])

    def test_alias_allocator_checks_numbered_conflicts_on_demand(self):
        row = dict(agent="claude", ref="claude:ffffffffffffffff", title="reused title")
        self.index.db.execute(
            "INSERT INTO mention_aliases(agent,alias,ref) VALUES (?,?,?)",
            ("claude", "reused_title", "claude:0000000000000001"))
        self.index.db.execute(
            "INSERT INTO mention_aliases(agent,alias,ref) VALUES (?,?,?)",
            ("claude", "reused_title_2", "claude:0000000000000002"))
        self.index.db.commit()
        self.assertEqual(self.index.mention_aliases([row])[row["ref"]], "reused_title_3")
