import tempfile
import random
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from unittest.mock import patch

from agentref.adapters.registry import ADAPTERS
from agentref.index import (
    Index, _ISO_ORDER_CACHE, _ISO_ORDER_CACHE_SEEN, _iso_session_order_key, _path_name,
)
from agentref.mentions import session_time
from scripts.check_jsonl_streaming import check as check_jsonl_streaming
from scripts.check_index_query import check


class IndexQueryTests(unittest.TestCase):
    def test_trigram_casefold_candidates_cover_unicode_substrings(self):
        rng = random.Random(20260925)
        alphabet = list('abcXYZ0123 _-./\\:\n\t"\'') + [
            "ß", "ẞ", "K", "ﬃ", "Æ", "İ", "Σ", "ς", "é", "e\u0301", "\u0301",
            "😀", "🧑‍💻", "中", "文", "あ", "한", "\x00",
        ]
        alphabet += [chr(codepoint) for start, end in (
            (0x00A0, 0x024F), (0x0300, 0x036F), (0x0370, 0x03FF),
            (0x4E00, 0x4EFF), (0x1F300, 0x1F5FF)) for codepoint in range(start, end)]
        texts = ["".join(rng.choice(alphabet) for _ in range(rng.randint(10, 90)))
                 for _ in range(250)]
        db = sqlite3.connect(":memory:")
        try:
            try:
                db.execute("""CREATE VIRTUAL TABLE search USING fts5(
                    title, tokenize='trigram case_sensitive 1', detail=none)""")
            except sqlite3.OperationalError as exc:
                self.skipTest("SQLite FTS5 trigram tokenizer unavailable: " + str(exc))
            db.executemany("INSERT INTO search(rowid,title) VALUES (?,?)",
                           ((n + 1, text.casefold()) for n, text in enumerate(texts)))
            checked = 0
            for rowid, text in enumerate(texts, 1):
                folded = text.casefold()
                for _ in range(4):
                    start = rng.randrange(len(folded))
                    query = folded[start:start + rng.randint(3, 12)]
                    if len(query) < 3 or "\x00" in query:
                        continue
                    grams = dict.fromkeys(query[i:i + 3] for i in range(len(query) - 2))
                    expression = " AND ".join('"' + gram.replace('"', '""') + '"'
                                              for gram in grams)
                    candidate = db.execute(
                        "SELECT 1 FROM search WHERE search MATCH ? AND rowid=?",
                        (expression, rowid),
                    ).fetchone()
                    self.assertIsNotNone(candidate, (repr(text), repr(query)))
                    checked += 1
            self.assertGreater(checked, 500)
        finally:
            db.close()

    def test_query_path_name_matches_pathlib_semantics(self):
        for value in ("", "/", "\\", "C:\\", "C:\\Users\\Jane\\",
                      "/workspace/project/", "//server/share/", "relative/session"):
            with self.subTest(value=value):
                self.assertEqual(_path_name(value), Path(value).name)

    def test_session_order_timestamp_cache_is_bounded(self):
        _ISO_ORDER_CACHE.clear()
        for n in range(4100):
            _iso_session_order_key(f"2026-01-01T00:00:{n % 60:02d}.{n:06d}Z")
        self.assertLessEqual(len(_ISO_ORDER_CACHE), 4096)
        self.assertGreater(len(_ISO_ORDER_CACHE), 0)
        before = len(_ISO_ORDER_CACHE)
        _iso_session_order_key("x" * 1024)
        self.assertEqual(len(_ISO_ORDER_CACHE), before)

    def test_session_order_cache_admits_only_repeated_values(self):
        _ISO_ORDER_CACHE.clear()
        unique = "2026-01-01T00:00:00.123456Z"
        first = _iso_session_order_key(unique)
        self.assertIs(_ISO_ORDER_CACHE[unique], _ISO_ORDER_CACHE_SEEN)
        second = _iso_session_order_key(unique)
        self.assertEqual(second, first)
        self.assertEqual(_ISO_ORDER_CACHE[unique], first)

    def test_session_order_cache_is_safe_for_concurrent_indexes(self):
        _ISO_ORDER_CACHE.clear()
        values = [f"2026-01-01T00:00:{n % 60:02d}Z" for n in range(4000)]
        with ThreadPoolExecutor(max_workers=4) as workers:
            keys = list(workers.map(_iso_session_order_key, values))
        self.assertEqual(len(keys), len(values))
        self.assertLessEqual(len(_ISO_ORDER_CACHE), 4096)

    def test_filtered_and_unfiltered_results_match_full_table_reference(self):
        report = check(rows=60, repeats=1)
        self.assertTrue(report["resultsEquivalent"])
        for scenario in report["scenarios"]:
            self.assertEqual(scenario["materializedRows"]["reference"], 60)
            self.assertEqual(scenario["materializedRows"]["current"], scenario["returned"])

    def test_unknown_disabled_and_empty_sources_do_not_query_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td), [ADAPTERS["claude"]([])])
            try:
                statements = []
                index.db.set_trace_callback(statements.append)
                self.assertEqual(index.sessions("codex"), [])
                self.assertEqual(index.sessions("claude' OR 1=1 --"), [])
                index.adapters = {}
                self.assertEqual(index.sessions(), [])
                self.assertFalse(any("SELECT" in s.upper() for s in statements))
            finally:
                index.close()

    def test_keyword_pages_include_exact_total_without_materializing_all_rows(self):
        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td), [ADAPTERS["claude"]([])])
            try:
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"claude:{n:016x}", "claude", f"session-{n}",
                     "needle target" if n % 2 == 0 else "other", "", "", "2026-01-01T00:00:00Z",
                     f"synthetic::{n}", "unknown", n, 0, 0, "", 0) for n in range(25)))
                index.db.commit()
                first, total = index.matches("NEEDLE", "claude", limit=5, include_total=True)
                self.assertEqual(total, 13)
                self.assertEqual(len(first), 5)
                self.assertTrue(all("_agentrefTotal" not in row for row in first))
                second, second_total = index.matches("NEEDLE", "claude", limit=5, offset=5, include_total=True)
                self.assertEqual(second_total, total)
                self.assertEqual(len(second), 5)
                beyond, beyond_total = index.matches("NEEDLE", "claude", limit=5, offset=50, include_total=True)
                self.assertEqual(beyond, [])
                self.assertEqual(beyond_total, total)
                empty, empty_total = index.matches("missing", "claude", limit=5, include_total=True)
                self.assertEqual((empty, empty_total), ([], 0))
                with patch("agentref.index._path_name",
                           side_effect=AssertionError("ID prefix match should skip cwd parsing")):
                    prefix, prefix_total = index.matches("session", "claude", limit=5,
                                                         include_total=True)
                self.assertEqual((prefix_total, len(prefix)), (25, 5))
                self.assertFalse(index.db.in_transaction)
                index.db.execute("BEGIN")
                index.matches("NEEDLE", "claude", limit=5, include_total=True)
                self.assertTrue(index.db.in_transaction)
                index.db.execute("ROLLBACK")
            finally:
                index.close()

    def test_empty_query_page_uses_unfiltered_order_and_keeps_exact_empty_id(self):
        with tempfile.TemporaryDirectory() as td:
            names = ("claude", "codex", "grok")
            index = Index(Path(td), [ADAPTERS[name]([]) for name in names])
            try:
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"{agent}:{n:016x}", agent, f"session-{n}", f"Synthetic {agent} {n}", "", "",
                     f"2026-01-01T00:00:{n:02d}Z", f"synthetic::{agent}:{n}", "unknown", n, 0, 0, "", 0)
                    for agent in names for n in range(10)))
                index.db.commit()
                expected_rows = index.sessions(limit=7, offset=3)
                page, total = index.matches("", limit=7, offset=3, include_total=True)
                self.assertEqual((page, total), (expected_rows, 30))
                self.assertFalse(index.db.in_transaction)

                index.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                 ("claude:empty-id-ref", "claude", "", "Empty identity", "", "", "",
                                  "synthetic::empty-id", "unknown", 100, 0, 0, "", 0))
                index.db.commit()
                exact, exact_total = index.matches("", limit=7, include_total=True)
                self.assertEqual(([row["ref"] for row in exact], exact_total),
                                 (["claude:empty-id-ref"], 1))
            finally:
                index.close()

    def test_multi_source_keyword_pages_match_global_reference_with_exact_totals(self):
        with tempfile.TemporaryDirectory() as td:
            names = ("claude", "codex", "grok")
            index = Index(Path(td), [ADAPTERS[name]([]) for name in names])
            try:
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"{agent}:{n:016x}", agent, f"session-{n}",
                     "needle match" if n % 4 else "other", "", "", "2026-01-01T00:00:00Z",
                     f"synthetic::{agent}:{n}", "unknown", n, 0, 0, "", 0)
                    for agent in names for n in range(30)))
                index.db.commit()
                reference = [row for row in index.sessions()
                             if "needle" in row["title"].casefold()]
                for offset, limit in ((0, 7), (4, 9), (17, 11), (100, 5), (0, 0)):
                    page, total = index.matches("needle", limit=limit, offset=offset,
                                                include_total=True)
                    self.assertEqual(page, reference[offset:offset + limit])
                    self.assertEqual(total, len(reference))
                    self.assertEqual(index.matches("needle", limit=limit, offset=offset),
                                     reference[offset:offset + limit])
                self.assertEqual(index.matches("not-present", limit=5, include_total=True),
                                 ([], 0))
            finally:
                index.close()

    def test_process_local_trigram_candidates_track_rows_and_preserve_title_overlays(self):
        with tempfile.TemporaryDirectory() as td, patch("agentref.index._SEARCH_FTS_MIN_ROWS", 0):
            names = ("claude", "codex", "grok")
            index = Index(Path(td), [ADAPTERS[name]([]) for name in names])
            try:
                rows = [
                    ("claude", "prefix-needle", "A Streetstraße conversation", "C:\\work\\TargetProject"),
                    ("codex", "untitled-session", "untitled-session", ""),
                    ("grok", "unrelated", "Another title", "C:\\work\\Elsewhere"),
                    ("grok", "quoted-session", 'A "Quoted" heading', ""),
                    ("grok", "split-session", "abcd", "cdef"),
                ]
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"{agent}:{n:016x}", agent, session_id, title, cwd, "", "2026-01-01T00:00:00Z",
                     f"synthetic::{agent}:{n}", "unknown", n, 0, 0, "", 0)
                    for n, (agent, session_id, title, cwd) in enumerate(rows)))
                index.db.commit()
                for _ in range(2):
                    index.matches("STRASSE", limit=5, include_total=True)
                self.assertTrue(index._search_fts_build_pending)
                self.assertFalse(index._search_fts_ready)

                street, total = index.matches("STRASSE", limit=5, include_total=True)
                self.assertEqual((total, [row["agent"] for row in street]), (1, ["claude"]))
                self.assertTrue(index._search_fts_ready)
                cwd, cwd_total = index.matches("TargetProject", limit=5, include_total=True)
                self.assertEqual((cwd_total, [row["sessionId"] for row in cwd]), (1, ["prefix-needle"]))
                prefix, prefix_total = index.matches("prefix", limit=5, include_total=True)
                self.assertEqual((prefix_total, len(prefix)), (1, 1))
                quoted, quoted_total = index.matches('"Quoted"', "grok", limit=5,
                                                     include_total=True)
                self.assertEqual((quoted_total, len(quoted)), (1, 1))
                grams = '"abc" AND "bcd" AND "cde" AND "def"'
                candidate = index.db.execute("""SELECT s.ref FROM temp.agentref_search AS f
                    CROSS JOIN sessions AS s ON s.ref=f.ref
                    WHERE s.agent=? AND s.sessionId=? AND agentref_search MATCH ?""",
                    ("grok", "split-session", grams)).fetchone()
                self.assertIsNotNone(candidate)
                split_false_positive, split_total = index.matches("abcdef", "grok", limit=5,
                                                                  include_total=True)
                self.assertEqual((split_false_positive, split_total), ([], 0))
                unnamed, unnamed_total = index.matches("未命名", limit=5, include_total=True)
                self.assertEqual((unnamed_total, [row["agent"] for row in unnamed]), (1, ["codex"]))
                with patch.object(index.adapters["codex"], "metadata_overlay",
                                  return_value={"untitled-session": "Saved Codex heading"}):
                    saved, saved_total = index.matches("Saved Codex heading", "codex", limit=5,
                                                       include_total=True)
                self.assertEqual((saved_total, [row["sessionId"] for row in saved]),
                                 (1, ["untitled-session"]))

                from agentref.titles import identity
                index.db.execute("UPDATE sessions SET title=sessionId WHERE agent='claude'")
                index.db.commit()
                index._mark_search_fts_dirty()
                title_row = dict(index.db.execute("SELECT * FROM sessions WHERE agent='claude'").fetchone())
                title_cache = {title_row["ref"]: {"identity": identity(title_row),
                                                   "title": "Derived local heading"}}
                with patch.object(index, "_load_title_cache", return_value=title_cache):
                    derived, derived_total = index.matches("Derived local heading", "claude", limit=5,
                                                           include_total=True)
                self.assertEqual((derived_total, len(derived)), (1, 1))

                index.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    "claude:0000000000000000", "claude", "prefix-needle", "freshkeyword", "", "",
                    "2026-01-01T00:00:00Z", "synthetic::claude:0", "unknown", 0, 0, 0, "", 0))
                index.db.commit()
                index._mark_search_fts_dirty()
                fresh, fresh_total = index.matches("freshkeyword", "claude", limit=5, include_total=True)
                self.assertEqual((fresh_total, len(fresh)), (1, 1))
                index.db.execute("UPDATE sessions SET title='changedkeyword' WHERE agent='claude'")
                index.db.commit()
                index._mark_search_fts_dirty()
                changed, changed_total = index.matches("changedkeyword", "claude", limit=5,
                                                       include_total=True)
                self.assertEqual((changed_total, len(changed)), (1, 1))

                other = Index(Path(td), [])
                try:
                    other.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                        "grok:external", "grok", "external", "externalkeyword", "", "",
                        "2026-01-02T00:00:00Z", "synthetic::external", "unknown", 0, 0, 0, "", 0))
                    other.db.commit()
                finally:
                    other.close()
                external, external_total = index.matches("externalkeyword", "grok", limit=5,
                                                          include_total=True)
                self.assertEqual((external_total, len(external)), (1, 1))
            finally:
                index.close()

    def test_dense_keyword_queries_do_not_build_trigram_index(self):
        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td), [ADAPTERS["claude"]([])])
            try:
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"claude:{n:016x}", "claude", f"session-{n}", "common title", "", "",
                     "2026-01-01T00:00:00Z", f"synthetic::{n}", "unknown", n, 0, 0, "", 0)
                    for n in range(600)))
                index.db.commit()
                for _ in range(12):
                    page, total = index.matches("common title", "claude", limit=10,
                                                include_total=True)
                    self.assertEqual((len(page), total), (10, 600))
                self.assertFalse(index._search_fts_ready)
                self.assertEqual(index._search_sparse_queries, 0)
            finally:
                index.close()

    def test_repeated_sparse_query_can_build_fts_before_one_off_sparse_queries(self):
        with (tempfile.TemporaryDirectory() as td,
              patch("agentref.index._SEARCH_FTS_MIN_ROWS", 0),
              patch("agentref.index._SEARCH_FTS_QUERY_THRESHOLD", 100)):
            index = Index(Path(td) / "repeated", [ADAPTERS["claude"]([])])
            try:
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"claude:{n:016x}", "claude", f"session-{n}", f"OnlyKey-{n:04d}", "", "",
                     "2026-01-01T00:00:00Z", f"synthetic::{n}", "unknown", n, 0, 0, "", 0)
                    for n in range(600)))
                index.db.commit()
                for _ in range(2):
                    self.assertEqual(index.matches("not-present", limit=5, include_total=True), ([], 0))
                self.assertTrue(index._search_fts_build_pending)
                self.assertFalse(index._search_fts_ready)
                index.db.execute("UPDATE sessions SET title='changed title' WHERE ref='claude:0000000000000000'")
                index.db.commit()
                index._mark_search_fts_dirty()
                self.assertFalse(index._search_fts_build_pending)
                self.assertEqual(index._search_sparse_query_counts, {})
                for _ in range(2):
                    self.assertEqual(index.matches("not-present", limit=5, include_total=True), ([], 0))
                self.assertTrue(index._search_fts_build_pending)

                dense, total = index.matches("OnlyKey", limit=5, include_total=True)
                self.assertEqual((len(dense), total), (5, 599))
                self.assertFalse(index._search_fts_ready)
                repeated, repeated_total = index.matches("not-present", limit=5, include_total=True)
                self.assertEqual((repeated, repeated_total), ([], 0))
                self.assertTrue(index._search_fts_ready)
            finally:
                index.close()

            one_off = Index(Path(td) / "one-off", [ADAPTERS["claude"]([])])
            try:
                one_off.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"claude:{n:016x}", "claude", f"session-{n}", f"OnlyKey-{n:04d}", "", "",
                     "2026-01-01T00:00:00Z", f"synthetic::{n}", "unknown", n, 0, 0, "", 0)
                    for n in range(600)))
                one_off.db.commit()
                for query in ("OnlyKey-0173", "OnlyKey-0517"):
                    self.assertEqual(one_off.matches(query, limit=5, include_total=True)[1], 1)
                self.assertFalse(one_off._search_fts_build_pending)
                self.assertFalse(one_off._search_fts_ready)
            finally:
                one_off.close()

    def test_dense_query_candidate_probe_is_cached_for_the_process(self):
        with tempfile.TemporaryDirectory() as td, patch("agentref.index._SEARCH_FTS_MIN_ROWS", 0):
            index = Index(Path(td), [ADAPTERS["claude"]([])])
            try:
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"claude:{n:016x}", "claude", f"session-{n}", "common title", "", "",
                     "2026-01-01T00:00:00Z", f"synthetic::{n}", "unknown", n, 0, 0, "", 0)
                    for n in range(600)))
                index.db.commit()
                index._search_page_queries = 8
                index._search_sparse_queries = 1
                index._search_fts_build_pending = True

                page, total = index.matches("common title", "claude", limit=10,
                                            include_total=True)
                self.assertEqual((len(page), total), (10, 600))
                self.assertTrue(index._search_fts_ready)
                self.assertIn((("claude",), "common title"), index._search_dense_queries)
                with patch.object(index, "_ensure_search_fts",
                                  side_effect=AssertionError("dense query should bypass FTS")):
                    page, total = index.matches("common title", "claude", limit=10,
                                                include_total=True)
                self.assertEqual((len(page), total), (10, 600))
            finally:
                index.close()

    def test_bulk_session_writes_invalidate_process_local_trigram_index(self):
        with tempfile.TemporaryDirectory() as td, patch("agentref.index._SEARCH_FTS_MIN_ROWS", 0):
            index = Index(Path(td), [ADAPTERS["claude"]([])])
            try:
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"claude:{n:016x}", "claude", f"session-{n}", f"old-title-{n}", "", "",
                     "2026-01-01T00:00:00Z", f"synthetic::{n}", "unknown", n, 0, 0, "", 0)
                    for n in range(5)))
                index.db.commit()
                index._search_page_queries = 8
                index._search_sparse_queries = 1
                index._search_fts_build_pending = True
                index.matches("not-present", "claude", limit=5, include_total=True)
                self.assertTrue(index._search_fts_ready)

                index.db.executemany("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"claude:{n:016x}", "claude", f"session-{n}", "fresh-batch-word", "", "",
                     "2026-01-02T00:00:00Z", f"synthetic::{n}", "unknown", n, 0, 0, "", 0)
                    for n in range(3)))
                index.db.commit()
                index._mark_search_fts_dirty()
                rows, total = index.matches("fresh-batch-word", "claude", limit=5,
                                            include_total=True)
                self.assertEqual((total, len(rows)), (3, 3))
                self.assertFalse(index._search_fts_ready)
                self.assertIsNone(index.db.execute(
                    "SELECT 1 FROM temp.sqlite_master WHERE name='agentref_search'").fetchone())
            finally:
                index.close()

    def test_activity_only_refresh_keeps_trigram_document_current(self):
        with tempfile.TemporaryDirectory() as td, patch("agentref.index._SEARCH_FTS_MIN_ROWS", 0):
            root = Path(td)
            source = root / "sessions"
            source.mkdir()
            path = source / "session.jsonl"
            fixture = (Path(__file__).parent / "fixtures" / "claude-normal.jsonl").read_bytes()
            path.write_bytes(fixture)
            (source / "session-two.jsonl").write_bytes(fixture)
            index = Index(root / "index", [ADAPTERS["claude"]([source])])
            try:
                self.assertFalse(index.refresh()["errors"])
                self.assertTrue(index._ensure_search_fts())
                self.assertFalse(index._search_fts_dirty)
                before = index.db.execute("SELECT rowid FROM sessions WHERE sourcePath=?",
                                          (str(path),)).fetchone()[0]
                with path.open("a", encoding="utf-8") as stream:
                    stream.write('{"type":"assistant","timestamp":"2026-09-26T10:00:00Z",'
                                 '"message":{"role":"assistant","content":"another update"}}\n')
                changed = index.refresh()
                self.assertFalse(changed["errors"])
                self.assertEqual(changed["changed"], 1)
                after = index.db.execute("SELECT rowid FROM sessions WHERE sourcePath=?",
                                         (str(path),)).fetchone()[0]
                self.assertNotEqual(before, after)
                self.assertEqual(index.refresh()["changed"], 0)
                self.assertTrue(index._search_fts_ready)
                self.assertFalse(index._search_fts_dirty)
                results, total = index.matches("registry", "claude", limit=10, include_total=True)
                self.assertEqual((total, len(results)), (2, 2))
            finally:
                index.close()

    def test_keyword_pages_keep_cwd_basename_and_session_prefix_matches(self):
        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td), [ADAPTERS["claude"]([])])
            try:
                rows = [
                    ("project", "C:\\work\\TargetProject", "other-session"),
                    ("other", "C:\\work\\elsewhere", "unique-session-42"),
                    ("neither", "C:\\work\\elsewhere", "unrelated"),
                ]
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"claude:{n:016x}", "claude", session_id, title, cwd, "", "2026-01-01T00:00:00Z",
                     f"synthetic::{n}", "unknown", n, 0, 0, "", 0)
                    for n, (title, cwd, session_id) in enumerate(rows)))
                index.db.commit()
                project, project_total = index.matches("TargetProject", "claude", limit=10,
                                                       include_total=True)
                prefix, prefix_total = index.matches("unique-session", "claude", limit=10,
                                                     include_total=True)
                self.assertEqual((project_total, [row["sessionId"] for row in project]),
                                 (1, ["other-session"]))
                self.assertEqual((prefix_total, [row["sessionId"] for row in prefix]),
                                 (1, ["unique-session-42"]))
            finally:
                index.close()

    def test_sql_session_order_matches_python_for_offsets_fallback_and_extreme_years(self):
        rows = [
            ("a", "0001-01-01T00:00:00+14:00", "", 0),
            ("b", "9999-12-31T23:59:59-14:00", "", 0),
            ("c", "2026-01-01T00:30:00+01:00", "", 0),
            ("d", "invalid", "2025-12-31T23:45:00Z", 0),
            ("e", "invalid", "also invalid", 1_800_000_000_000_000_000),
        ]
        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td), [ADAPTERS["claude"]([])])
            try:
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"claude:{n:016x}", "claude", ref, ref, "", "", updated, ref,
                     "unknown", mtime, 0, 0, "", 0)
                    for n, (ref, updated, created, mtime) in enumerate(rows)))
                index.db.execute("UPDATE sessions SET createdAt=? WHERE sessionId='d'", (rows[3][2],))
                index.db.execute("UPDATE sessions SET createdAt=? WHERE sessionId='e'", (rows[4][2],))
                index.db.commit()

                actual = index.sessions(limit=len(rows))
                expected = sorted(actual, key=lambda row: (session_time(row), row["ref"]), reverse=True)
                self.assertEqual([row["ref"] for row in actual], [row["ref"] for row in expected])
                unbounded = index.sessions()
                self.assertEqual([row["ref"] for row in unbounded], [row["ref"] for row in expected])
                batches = list(index.iter_session_batches(batch_size=2))
                self.assertTrue(all(0 < len(batch) <= 2 for batch in batches))
                batched = [row["ref"] for batch in batches for row in batch]
                self.assertEqual(batched, [row["ref"] for row in expected])
            finally:
                index.close()

    def test_exact_ref_and_session_id_matches_use_indexed_branches(self):
        with tempfile.TemporaryDirectory() as td:
            names = ("claude", "codex")
            index = Index(Path(td), [ADAPTERS[name]([]) for name in names])
            try:
                index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    (f"{agent}:{n:016x}", agent, session_id, f"title-{agent}", "", "",
                     "2026-01-01T00:00:00Z", f"synthetic::{agent}:{n}", "unknown", n, 0, 0, "", 0)
                    for n, (agent, session_id) in enumerate((("claude", "shared-sid"),
                                                              ("codex", "shared-sid"),
                                                              ("codex", "other-sid")))))
                index.db.commit()
                rows, total = index.matches("shared-sid", limit=10, include_total=True)
                self.assertEqual(total, 2)
                self.assertEqual({row["agent"] for row in rows}, {"claude", "codex"})
                source, source_total = index.matches("claude:shared-sid", limit=10,
                                                     include_total=True)
                self.assertEqual((source_total, [row["agent"] for row in source]), (1, ["claude"]))
                ref = index.matches("claude:0000000000000000", limit=10)
                self.assertEqual([row["sessionId"] for row in ref], ["shared-sid"])
                empty, empty_total = index.matches("shared-sid", limit=0, include_total=True)
                self.assertEqual((empty, empty_total), ([], 2))
            finally:
                index.close()

    def test_agent_index_is_created_for_existing_database(self):
        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td), [])
            index.db.execute("DROP INDEX sessions_agent")
            index.db.execute("CREATE INDEX sessions_agent ON sessions(agent)")
            index.db.execute("PRAGMA user_version=2")
            index.db.commit()
            index.close()
            index = Index(Path(td), [])
            try:
                names = [row[1] for row in index.db.execute("PRAGMA index_list(sessions)")]
                self.assertIn("sessions_agent", names)
                plan = index.db.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM sessions WHERE agent=? "
                    "ORDER BY agentref_session_order(updatedAt,createdAt,mtime) DESC,ref DESC",
                    ("claude",),
                ).fetchall()
                details = " ".join(row[3] for row in plan)
                self.assertIn("sessions_agent", details)
                self.assertNotIn("TEMP B-TREE", details)
                names = [row[1] for row in index.db.execute("PRAGMA index_list(sessions)")]
                self.assertIn("sessions_sessionid", names)
                id_plan = index.db.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM sessions WHERE agent IN (?,?) AND sessionId=?",
                    ("claude", "codex", "synthetic"),
                ).fetchall()
                self.assertIn("sessions_sessionid", " ".join(row[3] for row in id_plan))
                self.assertEqual(index.db.execute("PRAGMA user_version").fetchone()[0], 4)
                index.db.execute("DROP INDEX sessions_sessionid")
                index.db.commit()
            finally:
                index.close()
            index = Index(Path(td), [])
            try:
                names = [row[1] for row in index.db.execute("PRAGMA index_list(sessions)")]
                self.assertIn("sessions_sessionid", names)
            finally:
                index.close()

    def test_alias_lookup_index_is_created_for_existing_database(self):
        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td), [])
            index.db.execute("DROP INDEX mention_aliases_alias_ref")
            index.db.commit()
            index.close()
            index = Index(Path(td), [])
            try:
                names = [row[1] for row in index.db.execute("PRAGMA index_list(mention_aliases)")]
                self.assertIn("mention_aliases_alias_ref", names)
                plan = index.db.execute(
                    "EXPLAIN QUERY PLAN SELECT agent,ref FROM mention_aliases WHERE alias=?", ("synthetic",)
                ).fetchone()[3]
                self.assertIn("mention_aliases_alias_ref", plan)
            finally:
                index.close()

    def test_streaming_jsonl_benchmark_confirms_equivalent_records(self):
        result = check_jsonl_streaming(records=40, width=256)
        self.assertTrue(result["synthetic"])
        self.assertTrue(result["equivalent"])
        self.assertEqual(result["list"]["records"], 40)
        self.assertEqual(result["stream"]["records"], 40)
