"""Prepare/verify isolated recipient trials. Source history is always synthetic.

This script never implements the missing feature or calls a model. A receiving
agent must do the work between prepare and verify. Native UI is a separate gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from agentref.adapters import ClaudeAdapter, CodexAdapter
from agentref.index import Index
from agentref.mcp import Server

REGISTER = "def register(d, key, value):\n    d[key] = value\n"
TESTS = '''import unittest
from registry import register, rollback

class RegistryTests(unittest.TestCase):
    def test_register(self):
        d = {}
        register(d, "a", 1)
        self.assertEqual(d, {"a": 1})

    def test_rollback(self):
        d = {"a": 1, "b": 2}
        rollback(d, "a")
        self.assertEqual(d, {"b": 2})

    def test_missing_key(self):
        d = {}
        rollback(d, "absent")
        self.assertEqual(d, {})
'''
SCENARIOS = ("interrupted", "workspace_changed", "retry_succeeded", "duplicate_titles")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(agent, workspace, scenario):
    goal = "Implement registry and rollback. rollback must ignore absent keys. Preserve register and run the supplied tests."
    if agent == "claude":
        data = [{"type": "user", "sessionId": "trial-selected", "cwd": str(workspace),
                 "message": {"role": "user", "content": goal}}]
        def call(identifier, name, args, output):
            data.extend([{"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": identifier, "name": name, "input": args}]}},
                {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": identifier, "content": output}]}}])
        call("write", "Write", {"file_path": "registry.py", "content": REGISTER}, "File created successfully")
    else:
        data = [{"type": "session_meta", "payload": {"id": "trial-selected", "cwd": str(workspace)}},
                {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": goal}]}}]
        def call(identifier, name, args, output):
            data.extend([{"type": "response_item", "payload": {"type": "function_call", "call_id": identifier,
                "name": name, "arguments": json.dumps(args)}},
                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": identifier, "output": output}}])
        call("write", "apply_patch", {"patch": "*** Begin Patch\n*** Add File: registry.py\n" + "".join("+" + line + "\n" for line in REGISTER.splitlines()) + "*** End Patch"}, "Success. Updated the following files")
    if scenario == "retry_succeeded":
        # A historical register-only check, not success of the final test suite.
        command = {"command": "python -m unittest test_register", "cwd": str(workspace)}
        for identifier, code in (("failed-check", 1), ("passed-check", 0)):
            call(identifier, "Bash" if agent == "claude" else "exec_command", command, f"Exit code: {code}")
    call("plan", "TodoWrite" if agent == "claude" else "update_plan",
         {"plan": [{"step": "implement rollback and run supplied tests", "status": "pending"}]}, "Plan updated")
    data.append({"type": "system", "subtype": "interrupt"} if agent == "claude"
                else {"type": "event_msg", "payload": {"type": "turn_aborted"}})
    return data


def prepare(agent, scenario, parent=None):
    parent = Path(parent) if parent else REPO / "demo-artifacts"
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=f"recipient-{agent}-{scenario}-", dir=parent)).resolve()
    workspace, source = root / "workspace", root / "source"
    workspace.mkdir()
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    prefix = REGISTER
    if scenario == "workspace_changed":
        prefix = "# User change after interruption: preserve this marker.\nUSER_MARKER = 'keep-me'\n\n" + REGISTER
    (workspace / "registry.py").write_text(prefix, encoding="utf-8")
    (workspace / "test_registry.py").write_text(TESTS, encoding="utf-8")
    data = records(agent, workspace, scenario)
    selected = source / "selected.jsonl"
    selected.write_text("".join(json.dumps(r) + "\n" for r in data), encoding="utf-8")
    if scenario == "duplicate_titles":
        decoy = json.loads(json.dumps(data).replace("trial-selected", "trial-decoy"))
        (source / "decoy.jsonl").write_text("".join(json.dumps(r) + "\n" for r in decoy), encoding="utf-8")
    adapter = (ClaudeAdapter if agent == "claude" else CodexAdapter)([source])
    index = Index(root / "index", [adapter])
    try:
        server = Server(index, workspace=workspace, agent=agent)
        index.refresh()
        row = next(r for r in index.sessions() if r["sessionId"] == "trial-selected")
        uri = next(item["resourceUri"] for item in server.mention_items({"query": ""})["items"]
                   if item["resourceUri"].endswith(row["ref"]))
        context = server.dispatch("resources/read", {"uri": uri})["contents"][0]["text"]
        (root / "context.md").write_text(context, encoding="utf-8")
    finally:
        index.close()
    manifest = {"format": 1, "agent": agent, "scenario": scenario, "selectedRef": row["ref"],
                "sourceSynthetic": True, "modelCalledByHarness": False, "nativeUIVerified": False,
                "protectedPrefix": prefix, "testsSha256": digest(workspace / "test_registry.py"),
                "sources": {p.name: digest(p) for p in source.glob("*.jsonl")}}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    workspace = root / "workspace"
    preserved = (workspace / "registry.py").read_text(encoding="utf-8").startswith(manifest["protectedPrefix"])
    tests_unchanged = digest(workspace / "test_registry.py") == manifest["testsSha256"]
    sources_unchanged = all(digest(root / "source" / name) == expected for name, expected in manifest["sources"].items())
    # Do not execute modified acceptance tests; never execute transcript commands.
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_registry.py", "-v"],
                            cwd=workspace, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30) if tests_unchanged else None
    report = {"sourceSynthetic": True, "modelExecution": "external, not established by verifier", "nativeUIVerified": False,
              "completedCodePreserved": preserved, "testsUnchanged": tests_unchanged, "sourcesUnchanged": sources_unchanged,
              "testsPassed": result is not None and result.returncode == 0}
    report["passed"] = all(report[key] for key in ("completedCodePreserved", "testsUnchanged", "sourcesUnchanged", "testsPassed"))
    (root / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if result:
        (root / "verification.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("prepare")
    create.add_argument("--agent", choices=("claude", "codex"), required=True)
    create.add_argument("--scenario", choices=SCENARIOS, default="interrupted")
    check = commands.add_parser("verify")
    check.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        root = prepare(args.agent, args.scenario)
        print(json.dumps({"root": str(root), "context": str(root / "context.md"), "workspace": str(root / "workspace"),
                          "next": "Give context.md to the receiving agent and ask it to finish rollback in workspace while preserving existing code and tests. Then run verify. This is a synthetic-source trial, not native UI proof."}))
        return 0
    report = verify(args.root)
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
