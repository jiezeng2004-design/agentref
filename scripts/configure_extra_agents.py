"""Explicit local setup for Grok/OpenCode/Antigravity references; dry-run by default.

Only adds three AgentRef plugins and three MCP entries to existing Claude hosts.
Never edits providers, credentials, permissions or foreign session data.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = Path.home()
NAMES = ("grok", "opencode", "antigravity")
LABELS = {"grok": "Grok", "opencode": "OpenCode", "antigravity": "Antigravity"}
SKILL_ROOT = HOME / ".codex/skills/.system/plugin-creator"


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            env=dict(os.environ, PYTHONUTF8="1"), timeout=60)
    if result.returncode:
        raise RuntimeError("setup command failed: " + Path(str(args[0])).name + " " + str(args[1]))
    return result.stdout


def atomic_json(path, before, data):
    if path.read_bytes() != before:
        raise RuntimeError("host configuration changed concurrently; retry")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=path.name + ".agentref-", delete=False) as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def entries(exe):
    return {name: {"command": str(exe), "args": ["mcp", "--agent", name,
                  "--allow-workspace-root", str(REPO.parents[1]), "--template-menu"]} for name in NAMES}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    exe = REPO / ".venv/Scripts/agentref.exe"
    if not exe.is_file():
        raise SystemExit("Install AgentRef in the local .venv first")
    expected = entries(exe)
    hosts = [HOME / ".claude.json", HOME / "AppData/Roaming/Claude/claude_desktop_config.json"]
    hosts.extend((HOME / "AppData/Local/Packages").glob("Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json"))
    plans = []
    for path in hosts:
        if not path.is_file():
            continue
        before = path.read_bytes()
        data = json.loads(before.decode("utf-8-sig"))
        servers = data.setdefault("mcpServers", {})
        for name, entry in expected.items():
            if name in servers and servers[name] != entry:
                raise SystemExit("Existing MCP entry differs; refusing overwrite: " + name)
            if args.rollback:
                servers.pop(name, None)
            else:
                servers[name] = entry
        plans.append((path, before, data))
    for name in NAMES:
        path = HOME / "plugins" / name
        if path.exists():
            companion = path / ".mcp.json"
            if not companion.is_file():
                raise SystemExit("Existing plugin is not owned by AgentRef: " + name)
            content = json.loads(companion.read_text(encoding="utf-8"))
            servers = content.get("mcpServers", {})
            owned = servers.get(name, servers.get("agentref", {}))
            if owned.get("command") != str(exe) or owned.get("args", [])[:3] != ["mcp", "--agent", name]:
                raise SystemExit("Existing plugin differs; refusing overwrite: " + name)
    report = {"applied": args.apply, "rollback": args.rollback, "plugins": [n + "@personal" for n in NAMES],
              "hostPaths": [str(p) for p, _, _ in plans], "entries": ["mcpServers." + n for n in NAMES]}
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False))
        return
    marketplace = command([sys.executable, str(SKILL_ROOT / "scripts/read_marketplace_name.py")]).strip()
    if marketplace != "personal":
        raise SystemExit("Expected existing personal marketplace")
    for name in NAMES:
        if args.rollback:
            command([shutil.which("codex"), "plugin", "remove", name + "@" + marketplace])
            continue
        plugin = HOME / "plugins" / name
        if not plugin.exists():
            command([sys.executable, str(SKILL_ROOT / "scripts/create_basic_plugin.py"), name,
                     "--with-skills", "--with-mcp", "--with-marketplace"])
        manifest = json.loads((REPO / "integrations/codex/claude/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
        manifest["name"] = name
        manifest["description"] = "AgentRef: reference local " + LABELS[name] + " sessions in Codex."
        manifest["interface"]["displayName"] = LABELS[name] + " 会话 · AgentRef"
        manifest["interface"]["longDescription"] = "本地只读会话引用，按最近时间选择历史会话后，核对当前工作区继续。"
        if name == "antigravity":
            manifest["interface"]["longDescription"] += "实验性支持：部分工具正文未解析，以资源内警告为准。"
        manifest["interface"]["defaultPrompt"] = ["选择一个 " + LABELS[name] + " 历史会话，检查当前项目状态后继续。"]
        from plugin_branding import apply_branding
        apply_branding(plugin, manifest)
        (plugin / ".codex-plugin/plugin.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        entry = dict(expected[name])
        entry["args"] = entry["args"][:-1]
        (plugin / ".mcp.json").write_text(json.dumps({"mcpServers": {name: entry}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        skill = (REPO / "integrations/codex/claude/skills/session-reference/SKILL.md").read_text(encoding="utf-8")
        skill = skill.replace("Claude Code", LABELS[name]).replace("Claude", LABELS[name]).replace("claude", name)
        skill = skill.replace("显示时间、标题缩写和短 ID", "显示会话名称")
        if name == "antigravity":
            skill += "\nAntigravity 为实验性解析，必须向用户保留资源中的解析限制，不能将未解析工具视为已完成。\n"
        skill_path = plugin / "skills/session-reference/SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(skill, encoding="utf-8")
        command([sys.executable, str(SKILL_ROOT / "scripts/validate_plugin.py"), str(plugin)])
        command([sys.executable, str(SKILL_ROOT.parent / "skill-creator/scripts/quick_validate.py"), str(skill_path.parent)])
        command([sys.executable, str(SKILL_ROOT / "scripts/update_plugin_cachebuster.py"), str(plugin)])
        command([shutil.which("codex"), "plugin", "add", name + "@" + marketplace, "--json"])
    for path, before, data in plans:
        old = json.loads(before.decode("utf-8-sig"))
        atomic_json(path, before, data)
        after = json.loads(path.read_text(encoding="utf-8"))
        for key in set(old) | set(after):
            if key != "mcpServers" and old.get(key) != after.get(key):
                raise RuntimeError("unrelated host setting changed")
        for key, value in old.get("mcpServers", {}).items():
            if key not in NAMES and after["mcpServers"].get(key) != value:
                raise RuntimeError("unrelated MCP entry changed")
    report["unrelatedHostValuesPreserved"] = True
    artifacts = REPO / "demo-artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / ("extra-agents-rollback.json" if args.rollback else "extra-agents-setup.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
