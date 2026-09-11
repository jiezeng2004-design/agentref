# AgentRef

[Alpha release & demo](https://github.com/jiezeng2004-design/agentref/releases/tag/v0.1.0-alpha.1)

Download `AgentRef-Showcase.zip` from the release, extract it and open `index.html`
for an offline presentation. `AgentRef-Demo.mp4` is also available separately.
The 37-second recording shows native entry lookup and session-list browsing in
Codex and Claude Code; it does not demonstrate end-to-end task continuation.

> Local prerelease check (2026-09-11): 132 Python tests (one Windows symlink skip), 9 DSH tests,
> synthetic bidirectional integration and alpha wheel build passed.
> The supplied demo shows native entry lookup and session-list browsing.
> See [release readiness](RELEASE_READINESS.md) for current evidence and open gates.

Reference another AI coding agent's session and keep working.

Claude Code: `@codex` -> choose a Codex session -> inspect what finished, what
was interrupted, and the current workspace before continuing.

Codex: `@claude` -> same idea in reverse.

**Local-only · Read-only · Claude / Codex / Grok / OpenCode / Antigravity / DSH · CLI + Desktop integration**

Additional local sources: `@grok`, `@opencode`, and `@antigravity` in Codex,
with matching MCP resource menus in Claude. Antigravity is experimental: public
conversation text and command evidence are decoded, while other tool payloads
are explicitly marked uncertain. Gemini CLI and Qoder are not enabled.
See [current local setup](LOCAL_SETUP.md) for installation and verification limits.

> v0.1 alpha: Codex's `@claude` plugin now exposes a native session submenu using
> the installed desktop client's mention extension; its app-server call/read chain
> passes. Claude Code's `@codex` -> diamond entry -> Tab opens chronological session
> abbreviations before sending; real terminal selection was verified. Codex Desktop
> click/chip rendering and full cross-agent model continuation remain separate
> acceptance gates; see [verification](VERIFICATION.md). MCP forms stay opt-in.
> Maintainer-machine setup history: [本机使用记录](LOCAL_SETUP.md).
> These historical records do not configure a fresh installation.

## Run locally

Python 3.11+ and Git for workspace evidence. DSH Zstandard logs use Python 3.14's
standard library, or the `zstandard` dependency installed on Python 3.11–3.13.

```sh
python -m venv .venv
# Windows: .venv\Scripts\python -m pip install -e .
# macOS/Linux: .venv/bin/python -m pip install -e .
python -m agentref sessions
python -m agentref sessions --agent codex
python -m agentref pick codex --workspace /absolute/project
python -m agentref inspect codex:registry
python -m agentref context claude:registry --workspace /absolute/project
python -m agentref doctor
```

Direct `python -m agentref` works from the checkout without installation. Installation
may download setuptools into a temporary isolated build environment; runtime is offline.
An installed `agentref` command works from any directory. An ambiguous alias
opens a numbered picker on a terminal; noninteractive callers receive an error.
Aliases match title, workspace basename or session-ID prefix. MCP clients list
sessions first and use the selected exact ref, without asking users for UUIDs.

Default discovery: `~/.claude/projects`, `$CODEX_HOME/sessions` and
`$CODEX_HOME/archived_sessions` (`~/.codex` by default). `CLAUDE_CONFIG_DIR` is
respected. Use `--claude-root` / `--codex-root` **before** the subcommand for
explicit roots. Supplying either disables unspecified personal roots. Metadata
index: `~/.agentref/index.sqlite3`, overridden by `AGENTREF_HOME` or `--data-dir`.

## Connect

DSH as a source: `@dsh` in Codex or the DSH Web composer lists DSH sessions;
`@dsh:keyword` filters the DSH Web list. Install the personal Codex plugin with
`.venv\Scripts\python scripts/configure_dsh.py`, then use a new Codex task.
The existing DSH Web plugin must be reloaded/restarted to pick up its rebuilt
server and client. No automatic restart is performed.

Discovery uses `$DSH_HOME` (default `~/.dsh`), specifically `sessions/*/*/session.jsonl`
or `session.jsonl.zstd`, and identity-matched title projection caches. Use
`--dsh-root <DSH home>` before the CLI subcommand for an explicit root.
Listing reads headers and title metadata only; selected context reads the
version-0 event stream and applies its message replacement operations.
Subagents and recovery backups are excluded. Unknown versions, ambiguous
log representations and corrupt streams are reported instead of repaired.
Native Desktop rendering and real-model continuation remain separate
acceptance gates from the synthetic tests and app-server checks.

- [Claude CLI / Desktop local Code tab](integrations/claude/README.md)
- [Codex CLI / Desktop local tasks](integrations/codex/README.md)

All surfaces share the same MCP server. Use `--workspace` for a fixed project, or
`--allow-workspace-root` with the receiving task's explicit workspace argument.
`--agent` filters the exposed source agent. Normal package installation
does not alter host configuration. The explicit local setup script registers the
user-requested integrations; see [local setup](LOCAL_SETUP.md).

The source filter also accepts `grok`, `opencode`, and `antigravity`. New roots:
`~/.grok/sessions`, `$XDG_DATA_HOME/opencode` (default `~/.local/share/opencode`),
and `~/.gemini/antigravity{,-cli}/conversations`. The latter belongs to Antigravity,
not Gemini CLI. Use `--grok-root`, `--opencode-root`, or `--antigravity-root`
before the subcommand for isolated/custom stores; any explicit root disables all
unspecified personal roots. OpenCode roots contain `opencode.db`.

The explicit Windows setup script `python scripts/configure_extra_agents.py`
previews its three-plugin / existing-Claude-host scope; add `--apply` to install.
`--apply --rollback` removes those installed plugin entries and owned Claude MCP
entries while retaining source folders, marketplace entries and all sessions.

## Evidence, not optimistic summaries

AgentRef separates completed operations, partial writes, pending structured plans,
failed commands and uncertain state. It correlates tool calls/results, preserves
incomplete calls and malformed-tail warnings, compares exact write hashes where
possible, and records current Git status/diff statistics/log. A historical test
success is not a fresh test run. Natural-language plans are uncertain; feature
completion and dependency order still require the receiving agent's judgment.

Workspace inspection requires explicit `--workspace`; session cwd is only evidence.
Only referenced non-sensitive files within that root are inspected (1 MiB each).
No test or transcript command is executed by AgentRef. Context reads only the
selected session. Claude/Codex picker refresh reads changed file tails; snapshot
sources enumerate summaries or database metadata (Antigravity may read the first
user step for its title). A full context read scales with that session's size;
the index retains metadata only.

## Privacy

AgentRef is local-only. No conversations leave the machine **through AgentRef**.
No cloud backend. No account required. No telemetry by default (none implemented).
Foreign sessions are read-only. SQLite stores titles, paths, timestamps, IDs and
offsets, not full transcripts. Generated context is streamed to the local caller;
it is not saved automatically. Titles and paths themselves may be private.

When a receiving Claude/Codex client attaches the context to a hosted model, that
client's normal data transmission and privacy policies apply. AgentRef cannot
promise that a separate hosted agent keeps referenced content on-device. Context
can contain source-session secrets; review before sharing. No secret scanner is
claimed. AgentRef excludes common sensitive workspace paths but is not a sandbox.

## Develop

### Local titles for unnamed sessions

After explicit authorization to inspect unnamed sessions, run:

```sh
python -m agentref.titles
# Optional: restrict to a source or use an isolated AgentRef cache.
python -m agentref.titles --agent dsh --data-dir /path/to/agentref-cache
```

The command refreshes source metadata first, then extracts a short title from a
bounded number of user messages only for sessions still unnamed. JSONL extraction
reads at most 2 MiB and 2,000 records per session, with a 256 KiB record limit;
database extraction uses bounded queries. It skips common injected headers,
generic acknowledgments and credential-like lines. It does not call a model or
modify source histories. These are derived display titles, not recovered official
names. Existing source titles always take precedence.

The local `derived-titles.json` file in `AGENTREF_HOME` (default `~/.agentref`)
stores the title, source marker, generation time and a session identity digest.
Mention browsing reads this cache without triggering extraction. Rerun the command
to process newly unnamed sessions; it skips already titled sessions. No background
job is installed. To undo generated names, rename this cache file outside its
configured name. Titles themselves can be private; the filters are not a complete
secret scanner. Missing files, unsupported records, or the read limit can leave
some sessions unnamed.

```sh
python -m unittest discover -s tests -v
python scripts/demo.py
```

Tests and deterministic demo use synthetic fixtures and temporary workspaces,
never personal agent data. [Architecture](ARCHITECTURE.md),
[format findings](SESSION_FORMAT_FINDINGS.md), [plan](IMPLEMENTATION_PLAN.md).
MIT licensed. No cloud sync, orchestration, vector database or long-term memory.
