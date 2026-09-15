"""Opt-in live Grok check: send @codex and wait for a numbered selection.

This invokes the user's configured Grok model. Unlike protocol checks, it may
consume provider credits. No raw model output or private titles are persisted.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-live-metadata', action='store_true',
                        help='Explicitly authorize sending Codex candidate metadata to the configured Grok model')
    options = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if not options.allow_live_metadata:
        print(json.dumps({'modelCalled': False, 'requiresExplicitMetadataAuthorization': True}))
        return 0
    grok = shutil.which('grok')
    inspect = subprocess.run([grok, 'inspect', '--json'], cwd=repo, capture_output=True,
                             text=True, encoding='utf-8', timeout=30)
    info = json.loads(inspect.stdout)
    command = [shutil.which("grok"), "--no-subagents", "--disable-web-search",
        "--max-turns", "4", "--tools", "read_file", "--deny", "MCPTool(*__context)",
        "--deny", "MCPTool(*__pick_session)", "--rules",
        "本次只检查 AgentRef 候选选择。只允许读取 agentref-session-reference 技能和调用 AgentRef 的 sessions。"
        "不要读取任何会话正文、其他文件或调用其他服务器。列出候选后停下等待用户编号。",
        "-p", "@codex", "--output-format", "streaming-json"]
    for server in info.get('mcpServers', []):
        if server.get('name') != 'agentref':
            command.extend(['--deny', 'MCPTool(' + server['name'] + '__*)'])
    report = {"modelAttempted": True, "privateContextRequested": False, "realCandidateMetadataAuthorized": True}
    try:
        process = subprocess.run(command, cwd=repo, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=150)
    except subprocess.TimeoutExpired:
        report.update({"passed": False, "reason": "timeout"})
    else:
        events = []
        for line in process.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        calls = [e for e in events if e.get("type") in ("tool_call", "tool_call_update")]
        names = sorted({name for e in calls if (name := e.get("toolName") or e.get("_meta", {}).get("name"))})
        reply = "".join(e.get('data', '') for e in events if e.get('type') == 'text')
        selected = any("context" in json.dumps(e.get("rawInput", {})) or "pick_session" in json.dumps(e.get("rawInput", {})) for e in calls)
        listed = any("sessions" in json.dumps(e.get("rawInput", {})) or "sessions" in e.get("toolName", "") for e in calls)
        errors = [e for e in events if e.get("type") == "error"]
        # Report only coarse provider error classes; never output raw stderr or prompts.
        combined = process.stderr + " ".join(str(e.get("message", "")) for e in errors)
        error_class = next((code for code in ("402", "401", "403", "429") if code in combined), None)
        report.update({"exitCode": process.returncode, "toolNames": names,
            "eventTypes": sorted({e.get("type", "unknown") for e in events}),
            "sessionsRequested": listed, "privateContextRequested": selected,
            "numberedList": bool(re.search(r"(?:^|\n)\s*1[.、)]", reply)),
            "asksForSelection": bool(re.search(r"选择|编号|选哪|第几", reply)),
            "providerErrorClass": error_class, "replyCharacters": len(reply)})
        report["passed"] = (process.returncode == 0 and listed and not selected
                            and report["numberedList"] and report["asksForSelection"])
    output = Path(__file__).resolve().parents[1] / "output/receiving-host-check/grok-postsend.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get('passed') else 1


if __name__ == "__main__":
    sys.exit(main())
