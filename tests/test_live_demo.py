"""Live harness tests use synthetic Python children, never a host or model."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import live_demo


class LiveDemoTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def run_child(self, code, timeout=10):
        command = [sys.executable, "-B", "-c", "import sys; sys.stdin.read(); " + code]
        with patch.object(live_demo, "build_command", return_value=command):
            return live_demo.run_live("codex", "synthetic-only", self.root, timeout)

    def test_default_preview_never_resolves_launches_or_creates_artifacts(self):
        with patch.object(live_demo.shutil, "which") as which, patch.object(live_demo, "run_live") as run:
            for agent in ("claude", "codex"):
                with patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(live_demo.main([agent]), 0)
                self.assertTrue(json.loads(output.getvalue())["preview"])
            which.assert_not_called()
            run.assert_not_called()

    def test_command_preserves_configured_route_and_permission_boundary(self):
        command = live_demo.build_command("codex", "codex", self.root)
        for forbidden in ("--ignore-user-config", "--model", "-m", "--dangerously-bypass-approvals-and-sandbox", "danger-full-access"):
            self.assertNotIn(forbidden, command)
        self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
        self.assertEqual(command[command.index("-a") + 1], "never")
        claude = live_demo.build_command("claude", "claude", self.root)
        self.assertIn("--safe-mode", claude)
        self.assertNotIn("ocx", claude)
        self.assertNotIn("--dangerously-skip-permissions", claude)
        with self.assertRaises(ValueError):
            live_demo.build_command("unknown", "synthetic", self.root)

    def test_exit_zero_without_pause_never_passes(self):
        report = self.run_child("from pathlib import Path; Path('registry.py').write_text(" + repr(live_demo.STAGE_ONE) + ")")
        self.assertEqual(report["exitCode"], 0)
        self.assertTrue(report["stageOneValid"])
        self.assertFalse(report["sourceStagePassed"])
        self.assertFalse(report["interruptedByHarness"])
        self.assertEqual(report["stopReason"], "source-exited-before-pause")

    def test_ready_stage_is_stopped_and_classified_only_as_source_stage(self):
        report = self.run_child("from pathlib import Path; import runpy; Path('registry.py').write_text(" + repr(live_demo.STAGE_ONE) + "); runpy.run_path('pause.py')")
        self.assertTrue(report["pauseObserved"])
        self.assertTrue(report["sourceStagePassed"])
        self.assertTrue(report["protectedFilesUnchanged"])
        self.assertTrue(report["interruptedByHarness"])
        self.assertFalse(report["nativeUIVerified"])
        self.assertFalse(report["bidirectionalAcceptancePassed"])
        self.assertIsNotNone(report["exitCode"])

    def test_pause_with_invalid_or_already_completed_code_never_passes(self):
        for content in ("def register(d,key,value): pass\n", live_demo.STAGE_ONE.replace("raise NotImplementedError", "d.pop(key, None)")):
            report = self.run_child("from pathlib import Path; import runpy; Path('registry.py').write_text(" + repr(content) + "); runpy.run_path('pause.py')")
            self.assertTrue(report["pauseObserved"])
            self.assertFalse(report["sourceStagePassed"])

    def test_protected_files_cannot_be_modified_to_pass(self):
        report = self.run_child("from pathlib import Path; import time; Path('test_registry.py').write_text('changed'); time.sleep(120)")
        self.assertFalse(report["protectedFilesUnchanged"])
        self.assertFalse(report["sourceStagePassed"])
        self.assertTrue(report["interruptedByHarness"])
        self.assertEqual(report["stopReason"], "protected-file-changed")

    def test_timeout_stops_only_owned_child_and_is_not_success(self):
        report = self.run_child("import time; time.sleep(120)", timeout=0.5)
        self.assertEqual(report["stopReason"], "timeout")
        self.assertTrue(report["interruptedByHarness"])
        self.assertFalse(report["sourceStagePassed"])

    def test_wrong_marker_is_not_a_pause_and_modified_helper_fails(self):
        report = self.run_child("from pathlib import Path; import time; Path('pause.started').write_text('wrong-run'); time.sleep(120)", timeout=0.5)
        self.assertFalse(report["pauseObserved"])
        self.assertFalse(report["sourceStagePassed"])
        report = self.run_child("from pathlib import Path; import time; Path('pause.py').write_text('changed'); time.sleep(120)")
        self.assertFalse(report["protectedFilesUnchanged"])
        self.assertEqual(report["stopReason"], "protected-file-changed")

    def test_monitor_interruption_cleans_up_the_owned_child(self):
        # Do not patch the shared time module: POSIX subprocess.wait() uses its
        # sleep too, and cleanup must remain real after the monitor interruption.
        with patch.object(live_demo, "time", wraps=live_demo.time) as clock:
            clock.sleep.side_effect = KeyboardInterrupt
            report = self.run_child("import time; time.sleep(120)")
        self.assertEqual(report["harnessError"], "KeyboardInterrupt")
        self.assertTrue(report["interruptedByHarness"])
        self.assertIsNotNone(report["exitCode"])
        self.assertFalse(report["sourceStagePassed"])

    def test_reports_do_not_guess_authentication_from_prompt_or_echoed_text(self):
        report = self.run_child("print('synthetic 401 403 Unauthorized not supported')")
        self.assertNotIn("errorSignals", report)
        self.assertNotIn("Unauthorized", json.dumps(report))
        self.assertFalse(report["sourceStagePassed"])

    def test_stage_validation_never_executes_model_code(self):
        path = self.root / "registry.py"
        for content in ("raise Exception('do not execute')", "x" * 9000, "def broken("):
            path.write_text(content, encoding="utf-8")
            self.assertFalse(live_demo.stage_one_valid(path))
        path.write_text("# whitespace/comments are allowed\n" + live_demo.STAGE_ONE, encoding="utf-8")
        self.assertTrue(live_demo.stage_one_valid(path))

    def test_already_exited_process_is_never_killed(self):
        process = Mock()
        process.poll.return_value = 0
        with patch.object(live_demo.subprocess, "run") as kill:
            self.assertFalse(live_demo.stop_owned(process))
        kill.assert_not_called()

    def test_main_returns_failure_for_failed_stage_and_missing_executable(self):
        with patch("sys.stdout", new_callable=io.StringIO), patch.object(live_demo.shutil, "which", return_value=None):
            self.assertEqual(live_demo.main(["codex", "--allow-live"]), 2)
        with patch("sys.stdout", new_callable=io.StringIO), patch.object(live_demo.shutil, "which", return_value="synthetic"), patch.object(live_demo, "run_live", return_value={"sourceStagePassed": False}):
            self.assertEqual(live_demo.main(["codex", "--allow-live"]), 2)

    def test_spawn_failure_is_saved_without_raw_exception_text(self):
        with patch.object(live_demo, "build_command", return_value=[str(self.root / "missing-executable")]):
            report = live_demo.run_live("codex", "synthetic", self.root, timeout=1)
        self.assertFalse(report["hostLaunched"])
        self.assertFalse(report["sourceStagePassed"])
        self.assertEqual(report["harnessError"], "FileNotFoundError")
        self.assertTrue(Path(report["resultPath"]).is_file())


if __name__ == "__main__":
    unittest.main()
