"""Configure only AgentRef-owned integration entries after explicit user request.

Prerequisite: plugin-creator scaffold of ~/plugins/claude with personal marketplace.
Does not print config contents, read credential stores, change providers or login.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = Path.home()


def digests(path):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8-sig")
    data = tomllib.loads(text) if path.suffix == ".toml" else json.loads(text)
    return {k: hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=True).encode()).hexdigest() for k, v in data.items()}


def main():
    if "--apply" not in sys.argv:
        raise SystemExit("Explicit --apply required; this writes local host configuration.")
    exe = REPO / ".venv" / ("Scripts/agentref.exe" if sys.platform == "win32" else "bin/agentref")
    if not exe.is_file():
        raise SystemExit("Install into the project .venv first")
    plugin = HOME / "plugins/claude"
    if not (plugin / ".codex-plugin/plugin.json").is_file():
        raise SystemExit("Run plugin-creator scaffold before configuration")
    allow_root = REPO.parents[1]
    args = ["mcp", "--agent", "claude", "--allow-workspace-root", str(allow_root)]
    server = {"command": str(exe), "args": args}
    template = REPO / "integrations/codex/claude"
    for relative in (".codex-plugin/plugin.json", "skills/session-reference/SKILL.md"):
        dest = plugin / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template / relative, dest)
    from plugin_branding import apply_branding
    manifest_path = plugin / ".codex-plugin/plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    apply_branding(plugin, manifest)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (plugin / ".mcp.json").write_text(json.dumps({"mcpServers": {"claude": server}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    codex_config = HOME / ".codex/config.toml"
    claude_config = HOME / ".claude.json"
    before = {str(p): digests(p) for p in (codex_config, claude_config)}
    # Native CLI handles additive updates and its own configuration semantics.
    cmd = [shutil.which("claude"), "mcp", "add", "--scope", "user", "codex", "--", str(exe), "mcp", "--agent", "codex", "--allow-workspace-root", str(allow_root), "--template-menu"]
    existing = json.loads(claude_config.read_text(encoding="utf-8-sig")) if claude_config.exists() else {}
    old = existing.get("mcpServers", {}).get("codex")
    expected = {"type": "stdio", "command": str(exe), "args": cmd[cmd.index(str(exe)) + 1:], "env": {}}
    if old and old != expected:
        raise SystemExit("An existing codex MCP entry differs; refusing to overwrite")
    if not old:
        subprocess.run(cmd, check=True, capture_output=True)
    # Store Desktop installations use a package-local redirected Roaming directory.
    desktop_paths = list((HOME / "AppData/Local/Packages").glob("Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json")) if sys.platform == "win32" else []
    standard = HOME / "AppData/Roaming/Claude/claude_desktop_config.json"
    if standard.exists():
        desktop_paths.append(standard)
    desktop_server = {"command": str(exe), "args": expected["args"]}
    for path in desktop_paths:
        before[str(path)] = digests(path)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        entries = data.setdefault("mcpServers", {})
        if "codex" in entries and entries["codex"] != desktop_server:
            raise SystemExit("Desktop codex entry already exists and differs")
        entries["codex"] = desktop_server
        # Atomic replacement; all existing JSON values are preserved.
        temp = path.with_name(path.name + ".agentref.tmp")
        if temp.exists():
            raise SystemExit("Unexpected pending temporary config file")
        with temp.open("x", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        temp.replace(path)
    subprocess.run([shutil.which("codex"), "plugin", "add", "claude@personal", "--json"], check=True, capture_output=True)
    report = {"configuredAt": time.time(), "plugin": "claude@personal", "pluginPath": str(plugin), "workspaceAllowRoot": str(allow_root), "configChanges": {}}
    for raw_path, previous in before.items():
        after = digests(Path(raw_path))
        changed = [k for k in set(previous) | set(after) if previous.get(k) != after.get(k)]
        report["configChanges"][raw_path] = {"changedTopLevelKeys": sorted(changed), "previousKeyDigests": previous}
    out = REPO / "demo-artifacts/local-install.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"plugin": report["plugin"], "workspaceAllowRoot": str(allow_root), "changedConfigKeys": {k: v["changedTopLevelKeys"] for k, v in report["configChanges"].items()}}, ensure_ascii=True))


if __name__ == "__main__":
    main()
