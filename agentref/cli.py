import argparse
import json
import sys
import sqlite3
from pathlib import Path
from . import __version__
from .adapters import ClaudeAdapter, CodexAdapter
from .adapters.registry import ADAPTERS
from .index import Index, default_adapters
from .handoff import build_context
from .sources import supported_formats


def display(rows, stream=sys.stdout):
    for n, row in enumerate(rows, 1):
        # Escape control characters from untrusted titles/paths before terminal rendering.
        label = f"{row['agent']} | {row['title']}\n   {row['cwd']} | {row['updatedAt']} | {row['latestAgentState']}"
        label = "".join(c if c in "\n" or ord(c) >= 32 and ord(c) != 127 else "?" for c in label)
        print(f"{n}. {label}", file=stream)


def select(rows, require_selection=False):
    if not rows:
        raise ValueError("No matching sessions. Run sessions or doctor.")
    if len(rows) == 1 and not require_selection:
        return rows[0]
    display(rows, sys.stderr)
    if not sys.stdin.isatty():
        raise ValueError("Ambiguous reference or incomplete index; interactive picker required, or use an exact ref from sessions --json.")
    choice = input("Choose session number (blank cancels): ").strip()
    if not choice:
        raise ValueError("Selection cancelled")
    if not choice.isdigit() or not 1 <= int(choice) <= len(rows):
        raise ValueError("Invalid selection")
    return rows[int(choice) - 1]


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="agentref", description="Reference sessions across AI coding agents. Local-only; foreign sessions read-only.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--data-dir", type=Path)
    for name in ADAPTERS:
        parser.add_argument("--" + name + "-root", type=Path, help="Explicit session storage root; disables unspecified personal roots")
    sub = parser.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("sessions")
    ls.add_argument("--agent", choices=list(ADAPTERS))
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--query", default="", help="Filter sessions before serializing results")
    ls.add_argument("--limit", type=int, help="Maximum number of sessions to return (1..500)")
    ls.add_argument("--offset", type=int, default=0, help="Skip this many matching sessions")
    for command in ("inspect", "context", "pick"):
        p = sub.add_parser(command)
        p.add_argument("session", nargs="?", default="")
        p.add_argument("--agent", choices=list(ADAPTERS))
        p.add_argument("--workspace", type=Path, help="Explicitly authorize read-only inspection of this workspace")
    sub.add_parser("doctor")
    sub.add_parser("agent-menu", help="Unified @ganetref agent entry picker; no session indexing")
    mcp = sub.add_parser("mcp")
    mcp.add_argument("--workspace", type=Path)
    mcp.add_argument("--agent", choices=list(ADAPTERS))
    mcp.add_argument("--native-picker", action="store_true", help="Opt in to MCP forms only on a verified compatible host")
    mcp.add_argument("--template-menu", action="store_true", help="Use ordered dynamic resource completion in Claude instead of its fuzzy-ranked static list")
    mcp.add_argument("--allow-workspace-root", action="append", default=[], type=Path)
    args = parser.parse_args(argv)
    if args.command == "sessions":
        if args.limit is not None and not 1 <= args.limit <= 500:
            parser.error("sessions --limit must be between 1 and 500")
        if not 0 <= args.offset <= 1_000_000:
            parser.error("sessions --offset must be between 0 and 1000000")
        if len(args.query) > 120:
            parser.error("sessions --query must be at most 120 characters")
    if args.command == "agent-menu":
        from .agent_menu import AgentMenuServer
        AgentMenuServer().serve()
        return 0
    defaults = {a.agent: a for a in default_adapters()}
    # Supplying fixture roots disables unspecified personal roots.
    roots = {name: getattr(args, name + "_root") for name in ADAPTERS}
    if any(roots.values()):
        defaults = {name: ADAPTERS[name]([root]) for name, root in roots.items() if root}
    # Explicit source filters apply before indexing, not just to displayed rows.
    if getattr(args, "agent", None):
        defaults = {name: adapter for name, adapter in defaults.items() if name == args.agent}
    index = None
    try:
        if args.command in ("inspect", "context", "pick") and args.agent:
            source = args.session.strip().lstrip("@").strip().split(":", 1)[0]
            if source in ADAPTERS and source != args.agent:
                raise ValueError("Reference source conflicts with --agent; select a matching source.")
        index = Index(args.data_dir, list(defaults.values()))
        if args.command == "mcp":
            from .mcp import Server
            Server(index, args.workspace, args.agent, args.allow_workspace_root, args.native_picker, args.template_menu).serve()
            return 0
        stats = index.refresh()
        warnings = list(dict.fromkeys(stats.get("errors", [])))
        if warnings and args.command != "doctor":
            print("agentref: index incomplete; visible matches may be stale or partial. " + "; ".join(warnings), file=sys.stderr)
        if args.command == "doctor":
            from .parser import read_jsonl
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                probe = Path(td) / "probe.jsonl"
                probe.write_bytes(b'{"type":"probe"}\n{"partial":')
                records, _, warnings = read_jsonl(probe)
            result = {"version": __version__, "roots": {name: [{"path": str(p), "exists": p.is_dir()} for p in a.roots] for name, a in defaults.items()}, "database": index.db.execute("PRAGMA quick_check").fetchone()[0], "parser": "ok" if len(records) == 1 and warnings else "failed", "supportedFormats": supported_formats(), "refresh": stats}
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "sessions":
            if args.query:
                rows = index.matches(args.query, args.agent, limit=args.limit, offset=args.offset)
            else:
                rows = index.sessions(args.agent, limit=args.limit, offset=args.offset)
            print(json.dumps(rows, ensure_ascii=False, indent=2)) if args.json else display(rows)
        else:
            query = args.session.strip().lstrip("@").strip()
            rows = index.matches(query, args.agent) if query else index.sessions(args.agent)
            exact_ref = len(rows) == 1 and query == rows[0]["ref"]
            # A source name or empty query opens a picker, even with one candidate.
            bare_source = not query or query in defaults
            row = select(rows, require_selection=bare_source or (bool(warnings) and not exact_ref))
            session = index.read(row)
            session.parseWarnings.extend("index refresh incomplete: " + warning for warning in warnings)
            if args.command == "inspect":
                print(session.to_json())
            else:
                print(build_context(session, args.workspace))
        return 0
    except (ValueError, OSError, sqlite3.Error, KeyboardInterrupt) as exc:
        print("agentref: " + str(exc), file=sys.stderr)
        return 2
    finally:
        if index:
            index.close()
