"""Opt-in live SOURCE-stage harness; not full continuation or native UI acceptance.

Default invocation previews only. --allow-live launches the configured native
host, writes a fresh ignored workspace and may incur provider charges. It never
starts a proxy, changes model routes, reads credentials or resumes a session.
Host startup itself can have side effects; authorization must include that host.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
STAGE_ONE = "def register(d, key, value):\n    d[key] = value\n\ndef rollback(d, key):\n    raise NotImplementedError\n"
TESTS = '''import unittest
from registry import register, rollback

class RegistryTests(unittest.TestCase):
    def test_register(self):
        d = {}; register(d, "a", 1); self.assertEqual(d, {"a": 1})
    def test_rollback(self):
        d = {"a": 1, "b": 2}; rollback(d, "a"); self.assertEqual(d, {"b": 2})
    def test_missing_key(self):
        d = {}; rollback(d, "absent"); self.assertEqual(d, {})
'''


def digest(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            return None
        with path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        return hashlib.sha256(data).hexdigest() if len(data) <= 1024 * 1024 else None
    except OSError:
        return None


def stage_one_valid(path):
    """Check the deliberately exact demo stage without executing model code."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
            return False
        with path.open(encoding="utf-8") as stream:
            text = stream.read(8193)
        return len(text) <= 8192 and ast.dump(ast.parse(text)) == ast.dump(ast.parse(STAGE_ONE))
    except (OSError, ValueError, SyntaxError, RecursionError):
        return False


def build_command(agent, executable, workspace):
    # Keep configured model/auth/provider. Never ignore user config or add
    # model/provider/sandbox-bypass overrides to make a test pass.
    if agent == "codex":
        return [executable, "-a", "never", "exec", "--sandbox", "workspace-write",
                "--json", "-C", str(workspace), "-"]
    if agent == "claude":
        return [executable, "--safe-mode", "--strict-mcp-config", "--permission-mode", "acceptEdits",
                "--tools", "Write,Read,Bash", "--allowedTools", "Write", "Read", "Bash(python *)",
                "--output-format", "stream-json", "--verbose", "-p"]
    raise ValueError("unsupported live source")


def stop_owned(process):
    """Only a still-running child owned by this invocation, never a name lookup."""
    if process.poll() is not None:
        return False
    if os.name == "nt":
        stopped = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                 capture_output=True, timeout=15)
        if stopped.returncode and process.poll() is None:
            raise RuntimeError("owned process tree could not be stopped")
    else:
        # run_live starts a dedicated session, so children share this group.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return False
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        else:
            raise
    return True


def prepare(parent, agent):
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=agent + "-", dir=parent)).resolve()
    workspace = root / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True, timeout=15,
                   capture_output=True)
    nonce = uuid.uuid4().hex
    files = {"test_registry.py": TESTS,
             "pause.py": "from pathlib import Path\nimport time\n"
                         + f"Path('pause.started').write_text({nonce!r}, encoding='utf-8')\ntime.sleep(120)\n"}
    for name, content in files.items():
        (workspace / name).write_text(content, encoding="utf-8")
    protected = {name: digest(workspace / name) for name in files}
    return root, workspace, nonce, protected


def run_live(agent, executable, parent, timeout=180):
    root, workspace, nonce, protected = prepare(parent, agent)
    prompt = ("Authorized controlled SOURCE-stage test. Work only in this disposable workspace. "
              "Do not read credentials, personal history, parent projects or use external tools/network; "
              "do not launch agents, change configuration, commit or request escalated permissions. "
              "Preserve test_registry.py and pause.py exactly. The eventual goal is register and rollback, "
              "including ignoring absent keys; do NOT complete rollback in this stage. "
              "Create registry.py with exactly the following code (formatting/comments may vary):\n"
              + STAGE_ONE + "\nThen run python pause.py as a separate tool call. The harness will stop "
              "only this owned process tree when the readiness marker appears. Do not run tests or "
              "finish rollback before the pause. If permission/auth fails, report it and stop.")
    report = {"agent": agent, "workspace": str(workspace), "sourceSynthetic": False,
              "modelRouteOverride": False, "nativeUIVerified": False,
              "bidirectionalAcceptancePassed": False, "sourceStagePassed": False,
              "hostLaunched": False, "pauseObserved": False, "interruptedByHarness": False}
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    process = None
    log = root / "host-output.log"
    try:
        with log.open("wb") as output:
            process = subprocess.Popen(build_command(agent, executable, workspace), cwd=workspace,
                                       stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT, env=env,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                       start_new_session=os.name != "nt")
            report.update(hostLaunched=True, ownedPid=process.pid)
            try:
                process.stdin.write(prompt.encode("utf-8"))
                process.stdin.close()
                deadline = time.monotonic() + timeout
                progress = time.monotonic()
                marker_hash = hashlib.sha256(nonce.encode()).hexdigest()
                while process.poll() is None and time.monotonic() < deadline:
                    if any(digest(workspace / name) != expected for name, expected in protected.items()):
                        report["stopReason"] = "protected-file-changed"
                        break
                    if digest(workspace / "pause.started") == marker_hash:
                        report["pauseObserved"] = True
                        report["stopReason"] = "pause-observed"
                        break
                    if time.monotonic() - progress >= 15:
                        print(json.dumps({"phase": "source-running", "workspace": str(workspace),
                                          "stageOneValid": stage_one_valid(workspace / "registry.py")}), flush=True)
                        progress = time.monotonic()
                    time.sleep(0.1)
                report.setdefault("stopReason", "source-exited-before-pause" if process.poll() is not None else "timeout")
            finally:
                try:
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
                finally:
                    report["interruptedByHarness"] = stop_owned(process)
                    report["exitCode"] = process.poll()
    except (OSError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        # No raw logs or exception strings (which may contain credentials).
        report["harnessError"] = type(exc).__name__
    report["protectedFilesUnchanged"] = all(digest(workspace / name) == expected for name, expected in protected.items())
    report["stageOneValid"] = stage_one_valid(workspace / "registry.py")
    report["sourceStagePassed"] = bool(report["pauseObserved"] and report["interruptedByHarness"]
        and report["protectedFilesUnchanged"] and report["stageOneValid"] and "harnessError" not in report)
    report["logBytes"] = log.stat().st_size if log.exists() else 0
    report["resultPath"] = str(root / "result.json")
    (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", choices=("codex", "claude"))
    parser.add_argument("--allow-live", action="store_true", help="Allow native host/model execution; may incur charges")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args(argv)
    if not 10 <= args.timeout_seconds <= 300:
        parser.error("timeout must be between 10 and 300 seconds")
    if not args.allow_live:
        print(json.dumps({"preview": True, "agent": args.agent, "modelCalled": False,
                          "next": "Review host startup side effects, then authorize --allow-live. No files or hosts were touched."}))
        return 0
    executable = shutil.which(args.agent)
    if not executable:
        print(json.dumps({"sourceStagePassed": False, "error": "native host executable missing"}))
        return 2
    report = run_live(args.agent, executable, REPO / "demo-artifacts", args.timeout_seconds)
    print(json.dumps(report), flush=True)
    return 0 if report["sourceStagePassed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
