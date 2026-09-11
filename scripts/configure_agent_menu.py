"""Install the unified personal @ganetref entry; dry run unless --apply."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    helpers = Path.home() / ".codex/skills/.system/plugin-creator/scripts"
    target = Path.home() / "plugins/ganetref"
    exe = repo / ".venv/Scripts/agentref.exe"
    source = repo / "integrations/codex/ganetref"
    if not exe.is_file():
        raise SystemExit("Install AgentRef into .venv first")
    if target.exists():
        manifest = json.loads((target / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        if manifest.get("name") != "ganetref" or not manifest.get("description", "").startswith("AgentRef:"):
            raise SystemExit("Refusing to replace unrelated ganetref plugin")
    if not args.apply:
        print(json.dumps({"plugin": "ganetref@personal", "target": str(target),
                          "operation": "Install unified agent picker only", "applied": False}))
        return

    def run(*command):
        return subprocess.check_output(command, text=True, encoding="utf-8", timeout=60,
                                       env=dict(os.environ, PYTHONUTF8="1"))

    marketplace = run(sys.executable, str(helpers / "read_marketplace_name.py")).strip()
    if marketplace != "personal":
        raise SystemExit("Expected personal marketplace")
    if not target.exists():
        print(run(sys.executable, str(helpers / "create_basic_plugin.py"), "ganetref",
                  "--with-skills", "--with-mcp", "--with-marketplace"))
    shutil.copyfile(source / ".codex-plugin/plugin.json", target / ".codex-plugin/plugin.json")
    skill_dir = target / "skills/agent-entry"
    skill_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "skills/agent-entry/SKILL.md", skill_dir / "SKILL.md")
    (target / ".mcp.json").write_text(json.dumps({"mcpServers": {"ganetref": {
        "command": str(exe), "args": ["agent-menu"]}}}, indent=2) + "\n", encoding="utf-8")
    print(run(sys.executable, str(helpers / "validate_plugin.py"), str(target)))
    print(run(sys.executable, str(helpers / "update_plugin_cachebuster.py"), str(target)))
    print(run(shutil.which("codex"), "plugin", "add", "ganetref@personal", "--json"))


if __name__ == "__main__":
    main()
