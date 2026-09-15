# Sending @agent and choosing a session

This receiving-host integration handles a submitted `@claude`, `@codex`, `@grok`,
`@opencode`, `@antigravity`, or `@dsh` message. The receiving agent lists numbered
local sessions, waits for the user to choose, and then reads the exact selected
reference. Existing native menus remain available where previously configured.

For sending-time UI, use the native [OpenCode TUI](../opencode/agentref-tui/README.md)
or [DSH Web](../dsh/agentref-dsh/README.md) integration instead. Their first Tab
opens or focuses a metadata-only session list; explicit selection attaches the
chosen reference to the draft. This skill does not add a Tab menu to Grok or
Antigravity.
This integration does not add an autocomplete popup to Grok's file picker.

The skill uses an available AgentRef MCP `sessions` / `context` tool, or the
installed local CLI. Source-only requests never authorize a context read, even
when there is only one result. A number stays bound to the displayed exact ref.

## Explicit Windows installation

From the AgentRef checkout with its installed `.venv`:

```powershell
.venv/Scripts/python.exe scripts/configure_receiving_hosts.py
.venv/Scripts/python.exe scripts/configure_receiving_hosts.py --apply
```

The preview lists every path and before/after hash. Installation adds one
`agentref` MCP entry to Grok, OpenCode, and the shared Antigravity configuration,
and a dedicated `agentref-session-reference` skill for Grok, Claude, Codex,
OpenCode, Antigravity (shared and CLI skill roots), and DSH. CLI fallback covers
sources absent from a host's existing per-agent MCP entries.

Other server entries and provider settings are preserved. Conflicting AgentRef
entries or skills are refused. The installer currently accepts plain JSON in
the OpenCode `.jsonc` file; commented JSONC is refused without changing it.
Original sessions and credentials are not copied or changed.

Reload or reopen receiving clients so they discover the skill. In a new Grok
session, **send** `@codex` or `@claude`, wait for the numbered list, then reply
with a number and the work you want to continue. `/agentref-session-reference`
is an explicit skill entry in hosts that expose user-invocable skills.

## Verification and limits

```powershell
.venv/Scripts/python.exe scripts/check_receiving_hosts.py
.venv/Scripts/python.exe -m unittest discover -s tests -q
```

The first check verifies installed bytes, metadata-only results for all six
sources, Grok skill discovery/MCP handshake, and OpenCode skill/config discovery
with external OpenCode plugins disabled for that check. It writes counts and
booleans to `output/receiving-host-check/report.json`, never private titles or
session bodies. Counts are capped by the MCP `sessions` tool at 50.

On this machine, the full Python suite passed (one symlink skip); all six sources
returned metadata, Grok loaded its skill and discovered four MCP tools, and
OpenCode found its skill and configured MCP. Existing source parsing warnings
still produce `indexIncomplete`; the list must not be presented as exhaustive.
Antigravity and DSH skill files were installed, but their live UI/model skill
activation was not established by those checks. Codex discovered the new skill
in the active host's skill catalog. Cross-agent model continuation is a separate
acceptance step, not implied by installation or protocol tests.

After explicit authorization for candidate metadata transmission, one real Grok
headless `@codex` test passed: the model read the installed skill, requested
sessions, returned a numbered list, and asked for selection. No private context
tool was requested. This does not validate the second-turn context read, TUI
rendering, or other hosts' model behavior.

`scripts/check_grok_postsend.py` defaults to a no-model preview. Its optional
`--allow-live-metadata` check invokes the configured Grok model with `@codex`.
It requires authorization to send candidate metadata (up to 50 titles, workspace
paths, times, states and refs) to that provider. Context/picker tools and other
MCP servers are denied for this test. It does not select a private session body.
Only a sanitized status report is saved locally; Grok may retain its own normal
session history. It verifies post-send headless behavior, not TUI rendering.

## Scoped rollback

```powershell
.venv/Scripts/python.exe scripts/configure_receiving_hosts.py --rollback
.venv/Scripts/python.exe scripts/configure_receiving_hosts.py --apply --rollback
```

Rollback removes matching added AgentRef entries and the exact matching skill
files; changed entries are refused. It preserves other config values and leaves
directories, native plugins, original sessions, and providers in place. Do not
restore a complete old user configuration over current settings.
