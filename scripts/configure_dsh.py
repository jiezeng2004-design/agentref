"""Install/update only the personal Codex @dsh plugin; no DSH runtime restart."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from plugin_branding import apply_branding


def main():
    repo = Path(__file__).resolve().parents[1]
    helpers = Path.home() / ".codex/skills/.system/plugin-creator/scripts"
    plugin = Path.home() / "plugins/dsh"
    exe = repo / ".venv/Scripts/agentref.exe"
    if not exe.is_file():
        raise SystemExit("Install AgentRef in .venv first")

    def run(*args):
        return subprocess.check_output(args, text=True, encoding="utf-8",
                                       env=dict(os.environ, PYTHONUTF8="1"), timeout=60)

    marketplace = run(sys.executable, str(helpers / "read_marketplace_name.py")).strip()
    if marketplace != "personal":
        raise SystemExit("Expected personal marketplace")
    if plugin.exists():
        old = json.loads((plugin / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        if old.get("name") != "dsh" or "AgentRef" not in old.get("description", ""):
            raise SystemExit("Existing dsh plugin is not owned by AgentRef")
    else:
        print(run(sys.executable, str(helpers / "create_basic_plugin.py"), "dsh",
                  "--with-skills", "--with-mcp", "--with-marketplace"))
    manifest = json.loads((repo / "integrations/codex/claude/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
    manifest["name"] = "dsh"
    manifest["description"] = "AgentRef: reference local DeepSeek Harness (DSH) sessions in Codex."
    manifest["interface"].update(displayName="DSH 会话 · AgentRef",
                                 longDescription="本地只读 DSH 历史会话引用；选择具体会话后读取上下文并核对当前项目。不启动、不恢复、不修改 DSH 会话。",
                                 defaultPrompt=["选择一个 DSH 历史会话，检查当前项目状态后继续。"])
    apply_branding(plugin, manifest)
    (plugin / ".codex-plugin/plugin.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    entry = {"command": str(exe), "args": ["mcp", "--agent", "dsh", "--allow-workspace-root", str(repo.parents[1])]}
    (plugin / ".mcp.json").write_text(json.dumps({"mcpServers": {"dsh": entry}}, indent=2)+"\n", encoding="utf-8")
    skill = (repo / "integrations/codex/claude/skills/session-reference/SKILL.md").read_text(encoding="utf-8")
    skill = skill.replace("Claude Code", "DeepSeek Harness (DSH)").replace("Claude", "DSH").replace("claude", "dsh")
    skill += "\nDSH 候选只读会话头和标题缓存。选择前不读正文；不自动选中。历史版本或损坏流无法安全读取时报告限制，不重启、修复或迁移来源。\n"
    target = plugin / "skills/session-reference/SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(skill, encoding="utf-8")
    print(run(sys.executable, str(helpers.parent.parent / "skill-creator/scripts/quick_validate.py"), str(target.parent)))
    print(run(sys.executable, str(helpers / "validate_plugin.py"), str(plugin)))
    print(run(sys.executable, str(helpers / "update_plugin_cachebuster.py"), str(plugin)))
    print(run(shutil.which("codex"), "plugin", "add", "dsh@personal", "--json"))


if __name__ == "__main__":
    main()
