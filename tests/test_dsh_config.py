"""The DSH installer preview must not invoke installed helpers or mutate state."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class DshConfigTests(unittest.TestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location("configure_dsh", ROOT / "scripts/configure_dsh.py")
        module = importlib.util.module_from_spec(spec)
        # Match direct-script imports without touching sys.path permanently.
        with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
            spec.loader.exec_module(module)
        return module

    def test_preview_preserves_existing_plugin_and_never_invokes_helpers(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            existing = home / "plugins/dsh/.codex-plugin/plugin.json"
            existing.parent.mkdir(parents=True)
            existing.write_text('{"name":"unrelated-plugin"}', encoding="utf-8")
            before = existing.read_bytes()
            with patch.object(module.Path, "home", return_value=home), patch.object(module.subprocess, "check_output") as run, patch.object(module, "apply_branding") as branding, patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(module.main([]), 0)
            run.assert_not_called()
            branding.assert_not_called()
            self.assertFalse(json.loads(output.getvalue())["apply"])
            self.assertEqual(existing.read_bytes(), before)
            self.assertEqual([p for p in home.rglob("*") if p.is_file()], [existing])

    def test_preview_does_not_create_missing_home_or_require_helper_installation(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing-home"
            with patch.object(module.Path, "home", return_value=missing), patch.object(module.subprocess, "check_output") as run, patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(module.main([]), 0)
            run.assert_not_called()
            self.assertFalse(missing.exists())

    def test_outside_checkout_preview_and_unknown_flags_never_install(self):
        with tempfile.TemporaryDirectory() as directory:
            for extra, expected in (([], 0), (["--rollback"], 2)):
                result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts/configure_dsh.py"), *extra],
                                        cwd=directory, capture_output=True, text=True, encoding="utf-8", timeout=15)
                self.assertEqual(result.returncode, expected)
                if not extra:
                    self.assertFalse(json.loads(result.stdout)["apply"])
                self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
