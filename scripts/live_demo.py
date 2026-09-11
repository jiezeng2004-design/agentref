"""Explicit live acceptance harness. Uses installed hosts; never reads credentials.

Run manually: python scripts/live_demo.py codex|claude
Creates a dedicated demo workspace and interrupts only the child it starts.
Raw host logs are local ignored artifacts, never fixture inputs or public output.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

repo = Path(__file__).resolve().parents[1]


def main():
    agent = sys.argv[1]
    if agent not in ("codex", "claude"):
        raise SystemExit("expected codex or claude")
    exe = shutil.which(agent)
    if not exe:
        raise SystemExit("host executable missing")
    root = repo / "demo-artifacts" / (agent + "-" + str(time.time_ns()))
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "test_registry.py").write_text('import unittest\nfrom registry import register, rollback\n\nclass TestRegistry(unittest.TestCase):\n    def test_register(self):\n        d = {}\n        register(d, "a", 1)\n        self.assertEqual(d, {"a": 1})\n    def test_rollback(self):\n        d = {"a": 1}\n        rollback(d, "a")\n        self.assertEqual(d, {})\n', encoding="utf-8")
    prompt = """This is an authorized interrupted-session acceptance demo. Work only in the current demo directory. Do not read credentials, parent projects, network, or invoke other agents. Do not commit. Goal: implement registry.py with register(d,key,value) setting d[key]=value, and rollback(d,key) removing that key. Tests already exist. IMPORTANT controlled interruption: First create registry.py containing ONLY register, leave rollback unimplemented. Then immediately run python -c \"import time; time.sleep(120)\" as a separate tool call. The test harness will interrupt you there. Do not implement rollback before the pause. Do not alter test_registry.py. Use only local file tools and Python commands."""
    if agent == "codex":
        cmd = [exe, "exec", "--ignore-user-config", "--sandbox", "workspace-write", "--json", "-C", str(root), "-"]
    else:
        cmd = [exe, "--safe-mode", "--strict-mcp-config", "--permission-mode", "acceptEdits", "--allowedTools", "Write", "Read", "Bash(python *)", "--output-format", "stream-json", "--verbose", "-p"]
    log = root / "host-output.log"
    with log.open("wb") as output:
        process = subprocess.Popen(cmd, cwd=root, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT)
        process.stdin.write(prompt.encode())
        process.stdin.close()
        deadline = time.monotonic() + 90
        stage1_at = None
        while process.poll() is None and time.monotonic() < deadline:
            if (root / "registry.py").exists() and stage1_at is None:
                stage1_at = time.monotonic()
            if stage1_at and time.monotonic() - stage1_at >= 5:
                break
            time.sleep(0.5)
        interrupted = process.poll() is None
        if interrupted:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
            else:
                process.terminate()
            process.wait(timeout=15)
    raw = log.read_text(encoding="utf-8", errors="replace")
    signals = [phrase for phrase in ("Not logged in", "401", "403", "429", "Missing API key", "requires authentication", "not supported", "stream disconnected", "Unauthorized", "invalid_api_key") if phrase.casefold() in raw.casefold()]
    result = {"agent": agent, "workspace": str(root), "exitCode": process.returncode, "interruptedByHarness": interrupted, "stage1FileCreated": (root / "registry.py").exists(), "errorSignals": signals, "logBytes": log.stat().st_size}
    (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
