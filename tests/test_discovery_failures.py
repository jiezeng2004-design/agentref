"""Actual discovery failures must not become a complete empty inventory."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agentref.adapters.claude import ClaudeAdapter
from agentref.index import Index
from agentref.mcp import Server


class DiscoveryFailureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.nested = self.source / "nested"
        self.nested.mkdir(parents=True)
        self.path = self.nested / "session.jsonl"
        self.path.write_text(json.dumps({"type": "user", "sessionId": "synthetic",
            "message": {"content": "Implement search"}}) + "\n", encoding="utf-8")
        self.adapter = ClaudeAdapter([self.source])
        self.index = Index(self.root / "index", [self.adapter])
        self.addCleanup(self.index.close)
        self.index.refresh()
        self.before = self.index.sessions()

    def test_unavailable_directory_retains_cache_warns_and_prevents_unique_auto_read(self):
        scan = os.scandir
        for blocked in (self.source, self.nested):
            with self.subTest(blocked=blocked):
                def unavailable(path):
                    if Path(path) == blocked:
                        raise PermissionError("synthetic locked directory")
                    return scan(path)
                with patch("agentref.adapters.base.os.scandir", side_effect=unavailable):
                    stats = self.index.refresh()
                    self.assertTrue(stats["errors"])
                    self.assertEqual(self.index.sessions(), self.before)
                    self.assertEqual(self.adapter._discovered_stats, {})
                    server = Server(self.index, agent="claude")
                    with patch.object(self.index, "read", side_effect=AssertionError("unselected read")):
                        result = json.loads(server.picker({"query": "Implement search"}))
                        self.assertTrue(result["selectionRequired"])
                        self.assertEqual(result["reason"], "index_incomplete")
                self.assertFalse(self.index.refresh()["errors"])
                self.assertEqual(self.index.sessions(), self.before)

    def test_root_stat_permission_failure_is_not_silently_treated_as_missing(self):
        original = Path.stat
        def unavailable(path, *args, **kwargs):
            if path == self.source:
                raise PermissionError("synthetic unavailable root")
            return original(path, *args, **kwargs)
        with patch.object(Path, "stat", unavailable):
            self.assertTrue(self.index.refresh()["errors"])
        self.assertEqual(self.index.sessions(), self.before)

    def test_entry_stat_failure_preserves_cache_and_clears_partial_stats(self):
        real_scan = os.scandir
        class UnavailableEntry:
            name = "session.jsonl"
            path = str(self.path)
            def is_symlink(self):
                return False
            def is_dir(self, **kwargs):
                return False
            def stat(self, **kwargs):
                raise PermissionError("synthetic unavailable entry")
        class Entries:
            def __enter__(self):
                return iter([UnavailableEntry()])
            def __exit__(self, *args):
                return False
        def scan(path):
            return Entries() if Path(path) == self.nested else real_scan(path)
        with patch("agentref.adapters.base.os.scandir", side_effect=scan):
            self.assertTrue(self.index.refresh()["errors"])
        self.assertEqual(self.index.sessions(), self.before)
        self.assertEqual(self.adapter._discovered_stats, {})

    def test_healthy_discovery_still_removes_actually_deleted_synthetic_sessions(self):
        self.path.unlink()
        self.assertFalse(self.index.refresh()["errors"])
        self.assertEqual(self.index.sessions(), [])

    def test_absent_optional_root_is_allowed(self):
        adapter = ClaudeAdapter([self.root / "not-created"])
        self.assertEqual(adapter.discoverSessions(), [])
