import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from agentref.adapters.base import BaseAdapter
from agentref.adapters.codex import CodexAdapter
from agentref.adapters.registry import ADAPTERS
from agentref.adapters.snapshot import SnapshotAdapter
from agentref.core import SessionIR
from agentref.index import Index


class AdapterContractTests(unittest.TestCase):
    def test_all_sources_declare_complete_index_contract(self):
        for name, factory in ADAPTERS.items():
            with self.subTest(agent=name):
                adapter = factory([])
                expected = "incremental" if name in ("claude", "codex") else "snapshot"
                self.assertEqual(adapter.index_mode, expected)
                methods = ["read_indexed", "overlay_metadata"]
                methods += (["discoverSessions", "consume", "metadata_needs_refresh", "readSessionIncrementally"]
                            if expected == "incremental" else ["scan_metadata"])
                for method in methods:
                    self.assertTrue(callable(getattr(adapter, method)))
                if expected == "snapshot":
                    self.assertEqual(adapter.scan_errors, [])

    def test_incremental_mode_does_not_infer_snapshot_from_method(self):
        class FileSource(BaseAdapter):
            agent = "fixture"

            def scan_metadata(self):
                raise AssertionError("Wrong scan mode")

        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td) / "index", [FileSource([])])
            try:
                self.assertEqual(index.refresh()["files"], 0)
            finally:
                index.close()

    def test_snapshot_virtual_read_and_metadata_hook_are_dispatched(self):
        class VirtualSource(SnapshotAdapter):
            agent = "fixture"

            def scan_metadata(self):
                yield SessionIR(agent=self.agent, sessionId="one", sourcePath="virtual::one")

            def read_indexed(self, row):
                return SessionIR(agent=self.agent, sessionId=row["sessionId"])

            def overlay_metadata(self, rows):
                for row in rows:
                    row["title"] = "metadata only"

        with tempfile.TemporaryDirectory() as td:
            index = Index(Path(td) / "index", [VirtualSource([])])
            try:
                index.refresh()
                row = index.sessions()[0]
                self.assertEqual(row["title"], "metadata only")
                page = index.matches("metadata", limit=1)
                self.assertEqual([item["title"] for item in page], ["metadata only"])
                self.assertEqual(index.read(row).sessionId, "one")
            finally:
                index.close()

    def test_snapshot_metadata_reuses_stable_sources_and_invalidates_wal_changes(self):
        class FileSnapshot(SnapshotAdapter):
            agent = "fixture"
            metadata_cache_enabled = True
            metadata_uses_wal = True

            def __init__(self, roots, path):
                super().__init__(roots)
                self.path = path
                self.reads = 0

            def scan_metadata(self):
                def read(path):
                    self.reads += 1
                    title = path.read_text(encoding="utf-8")
                    return SessionIR(agent=self.agent, sessionId="one", title=title,
                                     sourcePath=str(path))
                yield from self.scan_files([self.path] if self.path.is_file() else [], read)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "source"
            root.mkdir()
            path = root / "snapshot.json"
            path.write_text("one", encoding="utf-8")
            adapter = FileSnapshot([root], path)
            index = Index(Path(td) / "index", [adapter])
            try:
                self.assertEqual(index.refresh()["files"], 1)
                self.assertEqual(adapter.reads, 1)
                self.assertEqual(index.refresh()["files"], 1)
                self.assertEqual(adapter.reads, 1)
                index.db.execute("UPDATE sessions SET sourcePath=sourcePath || '::external'")
                index.db.commit()
                index.refresh()
                self.assertEqual(adapter.reads, 2)
                self.assertEqual(len(index.sessions()), 1)

                index.db.execute("DELETE FROM sessions WHERE agent='fixture'")
                index.db.commit()
                index.refresh()
                self.assertEqual(adapter.reads, 3)
                self.assertEqual(len(index.sessions()), 1)

                path.write_text("two", encoding="utf-8")
                index.refresh()
                self.assertEqual(adapter.reads, 4)
                self.assertEqual(index.sessions()[0]["title"], "two")

                Path(str(path) + "-wal").write_bytes(b"changed")
                index.refresh()
                self.assertEqual(adapter.reads, 5)

                path.unlink()
                index.refresh()
                self.assertEqual(index.sessions(), [])
                path.write_text("new", encoding="utf-8")
                index.refresh()
                self.assertEqual(adapter.reads, 6)
                self.assertEqual(index.sessions()[0]["title"], "new")
            finally:
                index.close()

    def test_file_indexed_read_rejects_escape_before_reading(self):
        with tempfile.TemporaryDirectory() as td:
            source = BaseAdapter([Path(td) / "source"])
            with patch.object(source, "readSession") as read:
                with self.assertRaises(ValueError):
                    source.read_indexed({"sourcePath": str(Path(td) / "outside.jsonl")})
                read.assert_not_called()

    def test_codex_title_policy_is_metadata_only(self):
        source = CodexAdapter([])
        self.assertTrue(source.metadata_needs_refresh({"title": "<injected>"}))
        self.assertFalse(source.metadata_needs_refresh({"title": "User request"}))
        rows = [{"sessionId": "one", "title": "one"}, {"sessionId": "two", "title": "two"}]
        with patch.object(source, "saved_titles", return_value={"one": "Renamed"}), patch.object(source, "readSession") as read:
            source.overlay_metadata(rows)
            self.assertEqual([row["title"] for row in rows], ["Renamed", "未命名会话"])
            read.assert_not_called()

    def test_invalid_mode_fails_before_index_creation(self):
        source = BaseAdapter([])
        source.agent = "fixture"
        source.index_mode = "unknown"
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "index"
            with self.assertRaises(ValueError):
                Index(home, [source])
            self.assertFalse(home.exists())
