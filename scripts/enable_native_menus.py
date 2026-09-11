"""Add/remove only AgentRef's Claude template-menu flag; preserve other settings."""
import argparse
import json
from pathlib import Path
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    expected_exe = repo / ".venv/Scripts/agentref.exe"
    home = Path.home()
    targets = [home / ".claude.json", home / "AppData/Roaming/Claude/claude_desktop_config.json"]
    targets.extend((home / "AppData/Local/Packages").glob("Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json"))
    plans = []
    for path in targets:
        if not path.is_file():
            continue
        before = path.read_bytes()
        data = json.loads(before.decode("utf-8-sig"))
        server = data.get("mcpServers", {}).get("codex")
        if not server:
            continue
        if Path(server.get("command", "")).resolve() != expected_exe.resolve():
            raise SystemExit("Existing codex server is not owned by this AgentRef checkout")
        argv = server.get("args", [])
        if argv[:3] != ["mcp", "--agent", "codex"]:
            raise SystemExit("Unexpected AgentRef server arguments; no settings changed")
        after = [a for a in argv if a != "--template-menu"]
        if not args.rollback:
            after.append("--template-menu")
        if after != argv:
            server["args"] = after
            plans.append((path, before, data))
    if args.apply:
        for path, before, data in plans:
            if path.read_bytes() != before:
                raise SystemExit("Settings changed concurrently; retry after inspection")
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=path.name + ".agentref-", delete=False) as stream:
                stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
                temporary = Path(stream.name)
            temporary.replace(path)
    print(json.dumps({"applied": args.apply, "rollback": args.rollback,
                      "entry": "mcpServers.codex.args", "paths": [str(p) for p, _, _ in plans]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
