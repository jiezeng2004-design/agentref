import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.setup_common import atomic_write, local_executable, read_current
from scripts.configure_receiving_hosts import build_plan

REPO = Path(__file__).resolve().parents[1]


class SetupCommonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "config.json"

    def test_platform_paths(self):
        self.assertEqual(local_executable(self.root, "nt"), self.root / ".venv/Scripts/agentref.exe")
        self.assertEqual(local_executable(self.root, "posix"), self.root / ".venv/bin/agentref")

    def test_create_replace_and_noop(self):
        atomic_write(self.path, b"", b"original")
        atomic_write(self.path, b"original", b"updated")
        with patch("scripts.setup_common.os.replace") as replace:
            atomic_write(self.path, b"updated", b"updated")
            replace.assert_not_called()
        self.assertEqual(self.path.read_bytes(), b"updated")
        self.assertEqual(list(self.root.glob(".agentref-*")), [])

    def test_changed_or_removed_config_is_not_overwritten(self):
        self.path.write_bytes(b"user edit")
        with self.assertRaises(ValueError):
            atomic_write(self.path, b"original", b"new")
        self.assertEqual(self.path.read_bytes(), b"user edit")
        self.path.unlink()
        with self.assertRaises(ValueError):
            atomic_write(self.path, b"original", b"new")
        self.assertFalse(self.path.exists())

    def test_replace_failure_cleans_staging_and_preserves_original(self):
        self.path.write_bytes(b"original")
        with patch("scripts.setup_common.os.replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                atomic_write(self.path, b"original", b"new")
        self.assertEqual(self.path.read_bytes(), b"original")
        self.assertEqual(list(self.root.glob(".agentref-*")), [])

    def test_change_during_staging_is_rechecked(self):
        self.path.write_bytes(b"original")

        def concurrent_edit(_):
            self.path.write_bytes(b"user edit")

        with patch("scripts.setup_common.os.fsync", side_effect=concurrent_edit):
            with self.assertRaises(ValueError):
                atomic_write(self.path, b"original", b"new")
        self.assertEqual(self.path.read_bytes(), b"user edit")
        self.assertEqual(list(self.root.glob(".agentref-*")), [])

    def test_link_and_directory_targets_are_rejected(self):
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ValueError):
                read_current(self.path)
        with self.assertRaises(ValueError):
            read_current(self.root)

    def test_receiving_plan_explicit_paths_is_preview_only(self):
        executable = self.root / "agent ref.exe"
        executable.write_bytes(b"fixture only")
        home = self.root / "home"
        allowed = self.root / "workspace"
        plans = build_plan(home, REPO, command=executable, workspace_root=allowed)
        self.assertFalse(home.exists())
        self.assertEqual(len(plans), 10)
        config = next(after for path, _, after, _ in plans if path.name == "opencode.jsonc")
        command = json.loads(config)["mcp"]["agentref"]["command"]
        self.assertEqual(command, [str(executable), "mcp", "--allow-workspace-root", str(allowed)])

    def test_tui_real_script_preview_apply_and_rollback_with_fixture_config(self):
        self.path = self.root / "tui.json"
        original = {"theme": "user-theme", "plugin": ["user-plugin"]}
        self.path.write_text(json.dumps(original), encoding="utf-8")
        before = self.path.read_bytes()
        command = [sys.executable, "-B", "-X", "utf8", str(REPO / "scripts/configure_opencode_tui.py"),
                   "--config-dir", str(self.root), "--command", "fixture-agentref"]
        for flags in ([], ["--apply"], ["--apply"], ["--apply", "--rollback"]):
            result = subprocess.run(command + flags, cwd=self.root, capture_output=True, text=True,
                                    encoding="utf-8", timeout=30, check=True)
            self.assertEqual(json.loads(result.stdout)["applied"], "--apply" in flags)
            if not flags:
                self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(json.loads(self.path.read_bytes()), original)

    def test_receiving_script_import_works_outside_checkout(self):
        result = subprocess.run([sys.executable, "-B", str(REPO / "scripts/configure_receiving_hosts.py"), "--help"],
                                cwd=self.root, capture_output=True, text=True, timeout=30, check=True)
        self.assertIn("--workspace-root", result.stdout)
