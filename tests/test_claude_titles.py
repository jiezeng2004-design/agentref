"""Synthetic Claude Desktop/Code title and host-context regressions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agentref.adapters.claude import ClaudeAdapter
from agentref.index import Index


def user(content):
    return {"type": "user", "message": {"content": content}}


def blocks(*texts):
    return [{"type": "text", "text": text} for text in texts]


class ClaudeTitleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "sessions"
        self.source.mkdir()
        self.path = self.source / "synthetic.jsonl"
        self.adapter = ClaudeAdapter([self.source])

    def write(self, *records):
        self.path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n"
                                     for record in records), encoding="utf-8")
        return self.adapter.readSession(self.path)

    def append(self, *records):
        before = self.path.stat().st_size
        with self.path.open("a", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record) + "\n")
        return self.path.stat().st_size - before

    def index(self):
        index = Index(self.root / "index", [self.adapter])
        self.addCleanup(index.close)
        return index

    def test_custom_title_precedence_and_latest_wins(self):
        for records in (
            [user("Derived fallback"), {"type": "ai-title", "aiTitle": "AI title"}],
            [{"type": "ai-title", "aiTitle": "AI title"}, user("Derived fallback")],
        ):
            with self.subTest(records=records):
                self.assertEqual(self.write(*records).title, "AI title")
                session = self.write(*records,
                                     {"type": "custom-title", "customTitle": "First custom"},
                                     {"type": "ai-title", "aiTitle": "Later AI"},
                                     {"type": "custom-title", "customTitle": "Latest custom"},
                                     {"type": "ai-title", "aiTitle": "Last AI"},
                                     {"type": "custom-title", "customTitle": ""})
                self.assertEqual(session.title, "Latest custom")
                self.assertEqual(session.parseWarnings, [])

    def test_injected_first_block_is_not_title_or_intent_and_raw_is_retained(self):
        injected = " \n<system-reminder>Synthetic host instructions</system-reminder>\n "
        first = "Implement search\nPreserve rollback"
        second = "Keep the existing API"
        session = self.write(user(blocks(injected, first)), user(blocks(injected, second)))
        self.assertEqual(session.title, "Implement search")
        self.assertEqual(session.originalGoal, first)
        self.assertEqual(session.latestUserRequest, second)
        self.assertEqual(session.messages[0], {"role": "user", "text": injected + "\n" + first})
        index = self.index()
        with patch.object(self.adapter, "readSession", side_effect=AssertionError("listing read full IR")):
            self.assertFalse(index.refresh()["errors"])
            self.assertEqual(index.sessions()[0]["title"], "Implement search")
            self.assertEqual(index.refresh()["bytesRead"], 0)

    def test_injection_only_messages_do_not_replace_intent_or_turn_state(self):
        injected = "<system-reminder>Synthetic context</system-reminder>"
        session = self.write(user(blocks(injected)))
        self.assertEqual(session.title, self.path.stem)
        self.assertEqual(session.originalGoal, "")
        self.assertEqual(session.latestUserRequest, "")
        self.assertEqual(session.latestAgentState, "unknown")
        self.assertEqual(session.messages, [{"role": "context", "text": injected}])
        session = self.write(user(blocks(injected)), user("Implement search"),
                             {"type": "assistant", "message": {"content": "Done", "stop_reason": "end_turn"}},
                             user(blocks(injected)))
        self.assertEqual(session.title, "Implement search")
        self.assertEqual(session.originalGoal, "Implement search")
        self.assertEqual(session.latestUserRequest, "Implement search")
        self.assertEqual(session.latestAgentState, "turn-ended")

    def test_known_whole_wrappers_are_context_but_unknown_or_mixed_xml_is_intent(self):
        for text in ("<command-name>/clear</command-name>",
                     "<local-command-stdout>Cleared</local-command-stdout>"):
            with self.subTest(text=text):
                session = self.write(user(blocks(text)), user("Real request"))
                self.assertEqual(session.originalGoal, "Real request")
                self.assertEqual(session.title, "Real request")
                self.assertEqual(session.messages[0]["role"], "context")
        for text in ("<task>Implement XML export</task>",
                     "<system-reminder>unclosed", "<command-name>/clear</command-name> then explain it",
                     "Explain <system-reminder>example</system-reminder>"):
            with self.subTest(text=text):
                session = self.write(user(blocks(text)))
                self.assertEqual(session.originalGoal, text)
                self.assertEqual(session.latestUserRequest, text)
                self.assertEqual(session.title, text)

    def test_known_sideband_records_have_no_parse_warnings(self):
        records = [{"type": kind} for kind in (
            "agent-name", "api-request", "api-request-shape", "api-request-blob", "tools-used",
            "pr-link", "relocated", "bridge-session")]
        session = self.write(user("Real request"), *records)
        self.assertEqual(session.parseWarnings, [])
        self.assertEqual(session.unknownTypes, [])
        index = self.index()
        self.assertFalse(index.refresh()["errors"])
        self.assertFalse(index.refresh()["errors"])
        self.assertEqual(index.db.execute("SELECT warnings FROM sessions").fetchone()[0], 0)
        self.append({"type": "future-unknown-kind"})
        self.assertTrue(index.refresh()["errors"])
        self.assertTrue(self.adapter.readSession(self.path).parseWarnings)

    def test_cached_listing_and_appends_preserve_custom_title_precedence(self):
        self.write(user("Derived fallback"),
                   {"type": "assistant", "message": {"content": "SYNTHETIC_BODY_NOT_METADATA " * 1000}})
        index = self.index()
        index.refresh()
        self.assertEqual(index.db.execute("SELECT titleSource FROM claude_title_sources").fetchone()[0], "derived")
        for record, expected, source in (
            ({"type": "ai-title", "aiTitle": "AI title"}, "AI title", "ai"),
            ({"type": "ai-title", "aiTitle": "Latest AI"}, "Latest AI", "ai"),
            ({"type": "custom-title", "customTitle": "Custom title"}, "Custom title", "custom"),
            ({"type": "ai-title", "aiTitle": "Later AI"}, "Custom title", "custom"),
            ({"type": "custom-title", "customTitle": "Renamed custom"}, "Renamed custom", "custom"),
        ):
            # Reopen to ensure precedence comes from SQLite, not process state.
            index.close()
            index = self.index()
            previous_size = self.path.stat().st_size
            appended = self.append(record)
            with patch.object(self.adapter, "readSession", side_effect=AssertionError("listing read full IR")), \
                    patch.object(self.adapter, "scanSessionIncrementally", wraps=self.adapter.scanSessionIncrementally) as scan:
                result = index.refresh()
                self.assertFalse(result["errors"])
                self.assertEqual(result["bytesRead"], appended)
                self.assertLess(result["bytesRead"], previous_size // 10)
                self.assertEqual(scan.call_args.args[1], previous_size)
                self.assertEqual(index.sessions()[0]["title"], expected)
                self.assertEqual(index.matches(expected, limit=1)[0]["title"], expected)
                self.assertEqual(index.refresh()["bytesRead"], 0)
                self.assertEqual(scan.call_count, 1)
                self.assertEqual(index.db.execute("SELECT titleSource FROM claude_title_sources").fetchone()[0], source)
            self.assertEqual(self.adapter.readSession(self.path).title, expected)
        self.assertNotIn("SYNTHETIC_BODY_NOT_METADATA", "\n".join(index.db.iterdump()))

    def test_host_only_cache_accepts_first_real_request_then_keeps_derived_title(self):
        self.write(user(blocks("<system-reminder>Synthetic context</system-reminder>")))
        index = self.index()
        index.refresh()
        self.assertIsNone(index.db.execute("SELECT titleSource FROM claude_title_sources").fetchone()[0])
        for record in (user("First real request"), user("Latest real request")):
            appended = self.append(record)
            self.assertEqual(index.refresh()["bytesRead"], appended)
            self.assertEqual(index.sessions()[0]["title"], "First real request")
        self.assertEqual(index.db.execute("SELECT titleSource FROM claude_title_sources").fetchone()[0], "derived")
        self.assertEqual(index.refresh()["bytesRead"], 0)

    def test_removed_session_drops_provenance_and_recreated_path_starts_fresh(self):
        self.write({"type": "custom-title", "customTitle": "Old custom"})
        index = self.index()
        index.refresh()
        self.path.unlink()
        index.refresh()
        self.assertEqual(index.db.execute("SELECT count(*) FROM claude_title_sources").fetchone()[0], 0)
        self.write(user("Fresh request"))
        index.refresh()
        self.assertEqual(index.sessions()[0]["title"], "Fresh request")

    def test_version_five_cache_rebuilds_provenance_once_then_resumes_tail(self):
        for source in (None, "derived", "ai", "custom"):
            with self.subTest(source=source):
                records = [user(blocks("<system-reminder>Synthetic context</system-reminder>"))]
                if source:
                    records.append(user("Derived fallback"))
                if source in ("ai", "custom"):
                    records.append({"type": "ai-title", "aiTitle": "AI title"})
                if source == "custom":
                    records.append({"type": "custom-title", "customTitle": "Desktop title"})
                self.write(*records)
                original = self.path.read_bytes()
                index = Index(self.root / "index", [self.adapter])
                try:
                    index.refresh()
                    with index.db:
                        # Emulate the actual v5 schema, which has no side table.
                        index.db.execute("DROP TABLE claude_title_sources")
                        index.db.execute("PRAGMA user_version=5")
                        codex = list(index.db.execute("SELECT * FROM sessions WHERE agent='claude'").fetchone())
                        codex[0], codex[1], codex[7] = "codex:synthetic", "codex", "synthetic::codex"
                        index.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", codex)
                finally:
                    index.close()
                index = Index(self.root / "index", [self.adapter])
                try:
                    self.assertEqual(tuple(index.db.execute("SELECT * FROM sessions WHERE agent='codex'").fetchone()), tuple(codex))
                    rebuilt = index.refresh()
                    self.assertEqual(rebuilt["changed"], 1)
                    self.assertEqual(rebuilt["bytesRead"], len(original))
                    self.assertFalse(rebuilt["errors"])
                    self.assertEqual(index.db.execute("SELECT titleSource FROM claude_title_sources").fetchone()[0], source)
                    self.assertEqual(index.refresh()["bytesRead"], 0)
                    self.assertEqual(self.path.read_bytes(), original)
                finally:
                    index.close()
                index = Index(self.root / "index", [self.adapter])
                try:
                    self.assertEqual(index.refresh()["bytesRead"], 0)
                    appended = self.append({"type": "ai-title", "aiTitle": "Appended AI"})
                    self.assertEqual(index.refresh()["bytesRead"], appended)
                    self.assertEqual(index.sessions()[0]["title"], "Desktop title" if source == "custom" else "Appended AI")
                    self.assertEqual(index.db.execute("PRAGMA user_version").fetchone()[0], 6)
                finally:
                    index.close()

    def test_version_four_cache_rebuilds_unchanged_polluted_and_custom_titles_once(self):
        for custom in (False, True):
            with self.subTest(custom=custom):
                records = [user(blocks("<system-reminder>Synthetic context</system-reminder>", "Real request"))]
                if custom:
                    records.append({"type": "custom-title", "customTitle": "Desktop title"})
                self.write(*records)
                original = self.path.read_bytes()
                index = Index(self.root / "index", [self.adapter])
                try:
                    index.refresh()
                    with index.db:
                        index.db.execute("UPDATE sessions SET title='<system-reminder>', warnings=?", (int(custom),))
                        index.db.execute("PRAGMA user_version=4")
                finally:
                    index.close()
                index = Index(self.root / "index", [self.adapter])
                try:
                    result = index.refresh()
                    self.assertEqual(result["changed"], 1)
                    self.assertFalse(result["errors"])
                    self.assertEqual(index.sessions()[0]["title"], "Desktop title" if custom else "Real request")
                    self.assertEqual(index.refresh()["bytesRead"], 0)
                    self.assertEqual(index.db.execute("PRAGMA user_version").fetchone()[0], 6)
                    self.assertEqual(self.path.read_bytes(), original)
                finally:
                    index.close()
