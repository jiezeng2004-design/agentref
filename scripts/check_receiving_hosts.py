"""Metadata-only receiving-host checks. Never select a personal session body."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

from configure_receiving_hosts import REPO, NAME, build_plan


def capture(command, cwd=None, timeout=45):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def main():
    report = {"installedFilesMatch": all(b == a for _, b, a, _ in build_plan(Path.home(), REPO)),
              "privateContextSelected": False, "modelCalled": False, "sources": []}
    requests = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": "2025-11-25", "capabilities": {}}}]
    agents = ("claude", "codex", "grok", "opencode", "antigravity", "dsh")
    for number, agent in enumerate(agents, 1):
        requests.append({"jsonrpc": "2.0", "id": number, "method": "tools/call",
                         "params": {"name": "sessions", "arguments": {"agent": agent}}})
    proc = subprocess.run([str(REPO / ".venv/Scripts/agentref.exe"), "mcp"],
                          input="".join(json.dumps(r) + "\n" for r in requests),
                          capture_output=True, text=True, encoding="utf-8", timeout=90)
    responses = {r["id"]: r for r in map(json.loads, proc.stdout.splitlines())}
    for number, agent in enumerate(agents, 1):
        result = responses.get(number, {}).get("result", {})
        success = bool(result.get("content")) and not result.get("isError")
        rows = json.loads(result["content"][0]["text"]) if success else []
        diagnostics = [json.loads(b["text"]) for b in result.get("content", [])[1:]]
        report["sources"].append({"agent": agent, "passed": success,
            "visibleCount": len(rows), "indexIncomplete": any(d.get("indexIncomplete") for d in diagnostics),
            "onlyRequestedSource": all(r.get("agent") == agent for r in rows)})
    grok = shutil.which("grok")
    if grok:
        info = json.loads(capture([grok, "inspect", "--json"]).stdout)
        doctor = json.loads(capture([grok, "mcp", "doctor", "agentref", "--json"]).stdout)
        report["grok"] = {"version": info.get("grokVersion"),
            "skillDiscovered": any(s.get("name") == NAME for s in info.get("skills", [])),
            "mcpHealthy": doctor.get("healthy_count") == 1 and doctor.get("failing_count") == 0}
    opencode = shutil.which("opencode.cmd") or shutil.which("opencode")
    if opencode:
        skills = capture([opencode, "--pure", "debug", "skill"])
        config = capture([opencode, "--pure", "debug", "config"])
        if skills.returncode == 0 and config.returncode == 0:
            discovered = json.loads(skills.stdout)
            resolved = json.loads(config.stdout)
            report["opencode"] = {"skillDiscovered": any(s.get("name") == NAME for s in discovered),
                "mcpConfigured": "agentref" in resolved.get("mcp", {}), "externalPluginsDisabledForCheck": True}
        else:
            report["opencode"] = {"skillExit": skills.returncode, "configExit": config.returncode}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    output = REPO / "output/receiving-host-check/report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    passed = report["installedFilesMatch"] and all(
        s["passed"] and s["onlyRequestedSource"] for s in report["sources"])
    if grok:
        passed = passed and report["grok"]["skillDiscovered"] and report["grok"]["mcpHealthy"]
    if opencode:
        passed = passed and report["opencode"].get("skillDiscovered", False) and report["opencode"].get("mcpConfigured", False)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
