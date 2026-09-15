"""Install the user-requested post-send @agent workflow; preview by default.

Only the named AgentRef MCP entry and a new dedicated skill are managed. No
provider, permission, credential, session, or unrelated plugin is modified.
Rollback removes exact owned additions and refuses changed ones. Config snapshots
are hashes only: secrets and previous complete configs are never persisted.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import tomllib

try:
    from scripts.setup_common import atomic_write, local_executable, read_current
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from setup_common import atomic_write, local_executable, read_current

REPO = Path(__file__).resolve().parents[1]
NAME = "agentref-session-reference"
BEGIN = "# BEGIN AgentRef receiving host v1"
END = "# END AgentRef receiving host v1"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_entry(raw, key, expected, rollback=False):
    """Preserve every unrelated semantic value; refuse ambiguous JSONC."""
    before = json.loads(raw.decode("utf-8-sig")) if raw else {}
    after = copy.deepcopy(before)
    servers = after.setdefault(key, {})
    if not isinstance(servers, dict):
        raise ValueError("MCP table must be an object")
    if "agentref" in servers and servers["agentref"] != expected:
        raise ValueError("Existing agentref entry differs; refusing overwrite")
    if rollback:
        if "agentref" not in servers:
            return raw
        del servers["agentref"]
    else:
        if servers.get("agentref") == expected:
            return raw
        servers["agentref"] = expected
    encoded = (json.dumps(after, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    check = json.loads(encoded)
    for data in (before, check):
        if isinstance(data.get(key), dict):
            data[key].pop("agentref", None)
            if not data[key]:
                data.pop(key)
    if before != check:
        raise ValueError("Unrelated JSON setting changed")
    return encoded


def toml_entry(raw, expected, rollback=False):
    text = raw.decode("utf-8-sig")
    before = tomllib.loads(text)
    block = (f"{BEGIN}\n[mcp_servers.agentref]\ncommand = "
             + json.dumps(expected["command"]) + "\nargs = "
             + json.dumps(expected["args"]) + f"\nenabled = true\n{END}\n")
    existing = before.get("mcp_servers", {}).get("agentref")
    wanted = {**expected, "enabled": True}
    if existing is not None and existing != wanted:
        raise ValueError("Existing Grok agentref entry differs; refusing overwrite")
    if rollback:
        if existing is None:
            return raw
        if block in text:
            result = text.replace(block, "", 1)
        else:
            # Grok rewrites TOML on startup and can drop a leading marker.
            # Ownership is still checked by the exact parsed command/args above.
            # Remove only this table's assignments, retaining adjacent comments.
            header = re.search(r"(?m)^\[mcp_servers\.agentref\][ \t]*\r?\n", text)
            if not header:
                raise ValueError("Cannot locate exact Grok table; refusing rollback")
            following = re.search(r"(?m)^\[", text[header.end():])
            end = header.end() + following.start() if following else len(text)
            lines = text[header.end():end].splitlines(keepends=True)
            kept, seen, number = [], set(), 0
            while number < len(lines):
                line = lines[number]
                if not line.strip() or line.lstrip().startswith("#"):
                    if line.strip() not in (BEGIN, END):
                        kept.append(line)
                    number += 1
                    continue
                statement = ""
                while number < len(lines):
                    statement += lines[number]
                    number += 1
                    try:
                        value = tomllib.loads(statement)
                    except tomllib.TOMLDecodeError:
                        continue
                    break
                else:
                    raise ValueError("Incomplete Grok table; refusing rollback")
                if len(value) != 1:
                    raise ValueError("Unexpected Grok assignment; refusing rollback")
                key = next(iter(value))
                if key in seen or key not in wanted or value[key] != wanted[key]:
                    raise ValueError("Changed Grok assignment; refusing rollback")
                seen.add(key)
            if seen != set(wanted):
                raise ValueError("Missing Grok assignment; refusing rollback")
            result = text[:header.start()] + "".join(kept) + text[end:]
            result = re.sub(r"(?m)^" + re.escape(BEGIN) + r"\r?\n", "", result)
    elif existing == wanted:
        return raw
    else:
        if BEGIN in text or END in text:
            raise ValueError("Malformed AgentRef block")
        result = text + ("\n" if text else "") + block
    after = tomllib.loads(result)
    for data in (before, after):
        if "mcp_servers" in data:
            data["mcp_servers"].pop("agentref", None)
            if not data["mcp_servers"]:
                del data["mcp_servers"]
    if before != after:
        raise ValueError("Unrelated Grok setting changed")
    return result.encode("utf-8")


def build_plan(home, repo, rollback=False, *, command=None, workspace_root=None):
    exe = Path(command) if command is not None else local_executable(repo)
    exe = exe.expanduser().absolute()
    if not exe.is_file():
        raise ValueError("Install the repository venv first")
    allow_root = Path(workspace_root).expanduser().absolute() if workspace_root is not None else repo.parents[1]
    expected = {"command": str(exe), "args": ["mcp", "--allow-workspace-root", str(allow_root)]}
    skill = (repo / "integrations/shared/session-reference/SKILL.md").read_text(encoding="utf-8")
    # Single-quoted PowerShell paths escape apostrophes by doubling them.
    skill = skill.replace("__AGENTREF_EXE__", str(exe).replace("'", "''")).encode("utf-8")
    configs = [
        (home / ".grok/config.toml", "toml", expected),
        (home / ".config/opencode/opencode.jsonc", "mcp",
         {"type": "local", "command": [expected["command"], *expected["args"]], "enabled": True}),
        (home / ".gemini/config/mcp_config.json", "mcpServers", expected),
    ]
    skill_roots = [".grok/skills", ".claude/skills", ".codex/skills",
                   ".config/opencode/skills", ".gemini/config/skills",
                   ".gemini/antigravity-cli/skills", ".dsh/skills"]
    plans = []
    for path, kind, entry in configs:
        before = read_current(path)
        after = toml_entry(before, entry, rollback) if kind == "toml" else json_entry(before, kind, entry, rollback)
        plans.append((path, before, after, "mcp"))
    for relative in skill_roots:
        path = home / relative / NAME / "SKILL.md"
        before = read_current(path)
        if before and before != skill:
            raise ValueError("Existing skill differs; refusing overwrite: " + str(path))
        plans.append((path, before, b"" if rollback else skill, "skill"))
    for path, _, _, _ in plans:
        if not path.resolve().is_relative_to(home.resolve()):
            raise ValueError("Target escapes user home")
        if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
               for p in (path, *path.parents) if p != home.parent):
            raise ValueError("Reparse-point target refused: " + str(path))
    return plans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--command", type=Path, help="Explicit AgentRef executable path")
    parser.add_argument("--workspace-root", type=Path, help="Explicit allowed workspace root")
    args = parser.parse_args()
    plans = build_plan(Path.home(), REPO, args.rollback, command=args.command, workspace_root=args.workspace_root)
    report = {"applied": args.apply, "rollback": args.rollback, "interaction": "post-send numbered selection",
              "changes": [{"path": str(p), "kind": k, "changed": b != a,
                           "beforeSha256": digest(b), "afterSha256": digest(a)} for p, b, a, k in plans]}
    if args.apply:
        # Check the complete plan before the first write.
        for path, before, _, _ in plans:
            if read_current(path) != before:
                raise ValueError("Concurrent change; retry")
        for path, before, after, kind in plans:
            if before == after:
                continue
            if args.rollback and kind == "skill":
                if read_current(path) != before:
                    raise ValueError("Concurrent skill change")
                path.unlink()  # Exactly one verified owned file; no recursive deletion.
            else:
                atomic_write(path, before, after)
            if (path.read_bytes() if path.exists() else b"") != after:
                raise ValueError("Post-write verification failed")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
