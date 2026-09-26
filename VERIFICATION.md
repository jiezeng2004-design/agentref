# Verification — 2026-09-05

> Current evidence and open gates: [acceptance matrix](docs/CURRENT_ACCEPTANCE.md).
> Published alpha.2 checks: [release readiness](RELEASE_READINESS.md).
> The dated sections below retain historical evidence and limitations.

**Status: working local alpha; v0.1 real cross-agent acceptance NOT passed.**

## DSH prerelease fixes — 2026-09-08

- Fixed exact selected-session validation to run before the 50-row menu limit.
  A synthetic 51-row route regression confirms an older searched session can
  supply context; an absent ref still cannot trigger a context read.
- Removing a selection marker before sending now clears that selection without
  leaving the composer in its flushing state. A VM regression verifies that a
  subsequent selection appends only the new context, once.
- Origin-bearing requests must match the transport scheme, Host and effective
  port. Cross-port/protocol/host requests and malformed origins are rejected.
  Same-origin HTTP/TLS, default ports, IPv6 loopback and origin-less local GETs
  remain supported. Host authentication rejection remains authoritative; the
  origin-less fallback is not client authentication.
- `pnpm --dir integrations/dsh/agentref-dsh run check` passes: syntax, build and
  all 7 tests. Both distributed `lib` files were rebuilt and syntax-checked.
  Independent read-only candidate review found no concrete bypass/regression.
- All 107 Python tests and the synthetic bidirectional demo pass. These are
  local automated results, not live DSH/Desktop UI or real-model acceptance.
  No host configuration, credentials, version, commit or release was changed.


## Reverse real continuation and extra agents — 2026-09-06

- The user authorized source generation and deferred desktop UI acceptance.
  An invocation-local `-c windows.sandbox="unelevated"` with the existing
  `--sandbox workspace-write` enabled the Codex source harness to create register
  and enter its separate pause command. No global configuration was changed.
- Exact real Codex session `01a07741-3fe0-7e83-8aef-13f9f3f7dfac` was read through
  AgentRef's resource implementation. Its generated context was supplied to a
  fresh independent `ocx claude` process. That recipient added rollback and passed
  the two original tests. Independent verification confirmed the completed
  register prefix, tests and source transcript were unchanged.
- Evidence is in `demo-artifacts/codex-1788707157635548700/acceptance/`, including
  before-files, context, manifest, recipient log, final tests and result.json.
  The earlier ocx Claude -> current Codex case and this Codex -> independent
  ocx Claude case now establish both real source directions for the small task.
  The earlier direction still used the current Codex recipient, and neither case
  proves native mention UI. These tests cover register/set and rollback/remove
  of an existing key; they do not establish broader feature semantics.
- Additional installed metadata checks pass: Grok 62, OpenCode 36, Antigravity 35
  main-session records at this snapshot, with candidate declaration/completion and
  no detected metadata indexing errors. No unrelated private context was selected.
- Fresh Grok execution returned 402 usage balance exhausted; OpenCode's default
  xAI route returned 403 spending-limit. Neither produced stage-one code. AgentRef
  can read these exact failed test sessions; Grok reports the unknown `retry_state`
  record as uncertain. This is failed-source parsing evidence, not continuation.
- Additional evidence is in `demo-artifacts/additional-agent-validation/result.json`.
  An invocation-local OpenCode retry using the configured
  `opencodex/gpt-5.4-mini` route produced no log output or registry file within the
  150-second harness deadline; its owned process tree was stopped. The cause is
  unclassified; no successful model response or source generation is claimed.
  Result: `demo-artifacts/opencode-live-1788707486953776200/result.json`.
  Antigravity remains metadata/protocol tested and experimental; no real model
  continuation was attempted. Desktop UI is explicitly deferred by the user.

## Real source via ocx claude — 2026-09-06

- Fresh `ocx claude config status` reports enabled. The user selected this entry
  point because native Claude subscription/login is unavailable; no credentials,
  subscription, provider or persistent host settings were changed.
- Ran the existing live harness with its Claude child routed through the installed
  OpenCodex CLI `claude` command, retaining safe-mode and the tool allowlist.
  The real Claude Code session wrote working `register` plus an unimplemented
  `rollback` stub, then invoked the requested 120-second pause. The harness
  interrupted only its child process tree after observing the stage-one file.
- AgentRef selected exact real session `22ee7171-3dd7-4181-8436-0e150d7069d9`
  and generated context through its MCP Server resource-read implementation.
  The current Codex model consumed this context, checked the actual workspace,
  observed register passing / rollback failing, and replaced only the rollback
  TODO/pass with `d.pop(key, None)`. Both final tests pass.
- Verification confirms the completed register prefix, original test file and
  source transcript remain unchanged. This establishes real ocx-launched Claude
  source -> AgentRef context -> current Codex implementation/tests for this small
  case. It does not establish a fresh independent Codex recipient or native UI.
- Evidence: `demo-artifacts/claude-1788706372871317900/acceptance/` contains the
  exact context, source/test hashes, before-files, final tests and result.json.
- The opposite independent source-host direction remains blocked: the latest
  Codex CLI attempt reported read-only sandbox rejection and created no registry
  file. Native desktop mention selection remains unverified. Full bidirectional
  release acceptance is still not passed.

## Audit fixes — 2026-09-06

- **105 automated tests pass** on Windows / Python 3.14.6 (14.035 s), including
  six new audit regression tests in `tests/test_audit_regressions.py`.
- Out-of-range numeric snapshot timestamps now become source diagnostics rather
  than uncaught overflow exceptions. Regression coverage checks extreme positive
  and negative numbers, huge integers, infinity and NaN, source immutability,
  healthy/cached inventory availability, recovery and a subsequent MCP ping.
- With an incomplete index, CLI aliases require explicit terminal selection or
  an exact indexed ref in noninteractive use. Listing emits diagnostics on stderr
  without changing its JSON array format; selected inspect/context output retains
  index warnings. Selection and cancellation are covered.
- Unknown JSONL record types now reach index/menu diagnostics, survive warm
  refreshes and valid appends, and clear after source repair. Legacy metadata
  caches are invalidated once using index `user_version=1`; the first subsequent
  Claude/Codex refresh reparses sources. This can increase first-refresh time.
  Normal tool results do not acquire false orphan warnings during metadata scans.
- The synthetic bidirectional demo passes. Installed Codex app-server checks pass
  for Claude, Grok, OpenCode and Antigravity; Claude/Grok/Antigravity also pass the
  existing corrupt-source diagnostic checks. No private history or model was used.
- Scope: three implementation files, one new regression test file and this record.
  No persistent host configuration, source sessions, commits or releases changed.
  Pre-edit copies and hashes are in
  `demo-artifacts/audit-fix-baseline-20260906-223037/`.
- Desktop click/chip/submission and real bidirectional model continuation were
  not run. These fixes do not satisfy the outstanding real cross-agent release gate.

## Expanded local validation — 2026-09-06

The user deferred Claude login and requested continued local validation. No
authentication/provider/sandbox setting was changed. Native desktop control is
not available in this task; no Desktop UI pass is claimed.

- **99 automated tests pass**. Normal installed app-server checks pass for Claude,
  Grok, OpenCode and Antigravity. Existing bidirectional fixture checks pass.
- Fixed a newly reproduced workspace-history bug: tool calls now capture cwd at
  call time. A later turn's cwd cannot retroactively identify earlier commands.
  Full-write supersession also requires a known matching cwd. Historical relative
  paths from an earlier, different source workspace are left uncertain instead
  of being compared to an unrelated current file with the same name.
- Malformed JSONL warnings now survive warm metadata refreshes. Appending valid
  records does not erase earlier corruption; changed sources with warnings are
  fully re-read so diagnostics clear only after repair. This trades incremental
  speed for correctness while a source remains malformed.
- Fault injection through the **installed app-server** passes for Claude, Grok
  and Antigravity. Corrupt synthetic sources cause `indexIncomplete` and warnings
  in search results; reading the healthy selected resource retains the warning.
  This proves transport, not visual presentation of warnings in the composer.
  Reproduce: `python scripts/check_native_mentions.py --agent claude --source-error`.
- Fixed the installed-entrypoint checker to compare full inventory totals, not
  the capped menu length. Fresh real metadata-only checks: Grok 60 sessions in
  0.433 s, OpenCode 34 in 0.248 s, Antigravity 35 in 0.645 s; no detected indexing
  errors. These timings include process startup/search/completion; no private
  context was selected and no model was called. They are point-in-time snapshots.

### Five-source long-session / scale validation

`scripts/check_scale.py` generates synthetic JSONL/SQLite/protobuf sources,
hash-checks them before/after, and verifies the original goal, newest intent,
recent handoff message, reasoning exclusion and 32,000-character context budget.
Both tiers passed for all five agents: 300 sessions / 600 long messages, then
1,000 sessions / 3,000 long messages of 4,096 characters in the selected session.
Other sessions remain small metadata fixtures; this is not 1,000 huge sessions.

| Source | Warm refresh | Menu search | Context with memory tracing | Peak traced Python allocations |
|---|---:|---:|---:|---:|
| Claude | 376 ms | 399 ms | 1.80 s | 14.37 MiB |
| Codex | 438 ms | 479 ms | 1.71 s | 15.57 MiB |
| Grok | 738 ms | 738 ms | 1.80 s | 17.65 MiB |
| OpenCode | 25 ms | 33 ms | 1.77 s | 12.63 MiB |
| Antigravity | 1,242 ms | 1,231 ms | 1.82 s | 12.48 MiB |

Context outputs were 7,570–8,074 characters. These are local synthetic samples,
not a latency guarantee or a semantic model-quality evaluation. Traced allocation
peaks are not process RSS. The zero `bytesRead` counter represents incremental
JSONL reads only: snapshot adapters still re-read source metadata and SQLite.
The scale harness initially left SQLite fixture handles open on Windows; explicit
connection closing fixed that harness failure and both tiers then completed.

```sh
python scripts/check_scale.py --sessions 1000 --turns 3000 --width 4096 --output demo-artifacts/scale-validation-large.json
```

Local result artifacts: `demo-artifacts/scale-validation.json`,
`demo-artifacts/scale-validation-large.json`, and
`demo-artifacts/extra-agents-installed-check.json`.

### Remaining gates and rollback

- **Deferred:** real Claude source/recipient execution until user login; real
  Codex source demo remains unverified under a writable child execution context.
  The previous child reported read-only execution; its stdout does not by itself
  prove the precise underlying OS denial. Official permission references were
  checked ([Codex security](https://learn.chatgpt.com/docs/security),
  [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)); they
  do not replace local runtime evidence. No sandbox bypass was attempted.
- **Not run:** native Desktop selection/chip/submission and two real agents
  completing one interrupted task in both directions.
- **Deliberate limit:** arbitrary prose plans and semantic feature completion
  remain receiving-agent judgments, rather than being declared complete by
  keyword matching. Long real private histories were not selected for this check.
- Pre-edit copies for the captured files are under
  `demo-artifacts/validation-baseline-20260905-235356/`. The two additional core
  changes have explicit `handoff.py.reverse.patch` and `index.py.reverse.patch`
  there; these are inverse patches, not captured pre-edit snapshots. New files:
  `scripts/check_scale.py` and `tests/test_scale.py`.
- Automatic execution policy rejected removal of three test-created temporary
  directories (`blocked by policy`). They were inspected and have no reparse
  points, but were left in place without retrying deletion: under the system temp
  directory, `agentref-scale-ul4pffjg`, `agentref-scale-hx0ntkwa`, and
  `agentref-scale-nnms0dj7`. No commit/push/release or persistent configuration
  changes were made.

## Continuation accuracy and recipient trials — 2026-09-05

- Fresh automated gate: **94 unittest cases pass**. New coverage includes retry
  supersession, workspace separation, full-write replacement boundaries,
  confirmed versus unconfirmed completed plans, context budgets, source discovery
  failure, partial-inventory selection, and the recipient trial verifier.
- `agentref/evidence.py` preserves historical statuses while annotating older
  entries superseded by later matching successes. Command retries require exact
  command text and a known matching cwd. File replacement requires an evidenced
  successful full write to the exact same path. Generic edits and semantic task
  completion are not inferred. Superseded entries are excluded from continuation
  candidates but retained in history. Agent-reported completed plans remain
  uncertain evidence, without being recommended as new work.
- `agentref/context_render.py` renders recent structured evidence as valid JSON,
  with explicit omission counts and excerpts. Section allocations fit within a
  **32,000-character** document ceiling (not a token count). Goals, latest intent,
  continuation candidates and current Git state precede historical details.
- Detected indexing errors now propagate through tool text/metadata, picker
  responses, native search data, completion/resource metadata and selected context.
  An incomplete inventory cannot automatically resolve an apparently unique
  alias. Transient JSONL discovery failure retains previous index entries.
  Native menus return at most 100 matches with total/hasMore diagnostics; filtering
  still searches the full inventory. Host UI rendering of diagnostics is unverified.
- Fresh installed Codex app-server checks pass for all four exposed source plugins
  (Claude, Grok, OpenCode, Antigravity), using isolated synthetic data. The existing
  bidirectional fixture demo also passes.
- Performance sample, 1,000 synthetic Codex sessions on this machine: cold refresh
  **563.2 ms**, warm refresh **334.7 ms**, warm transcript bytes **0**, native menu
  search **312.2 ms**, 100 returned candidates with hasMore. One local measurement
  is not a production performance guarantee; no speculative cache was introduced.

### Receiving-agent execution observed in this task

The current Codex agent read the selected synthetic Claude context for the
`workspace_changed` scenario, inspected the actual workspace, and implemented
only `rollback`. The verifier confirmed the pre-existing `register` code, user
marker, test file and source transcript remained intact; all three final tests
passed. This establishes **synthetic source -> current receiving model -> local
implementation/tests** for this small case. It does not establish real source
generation, independent recipient behavior, native `@` UI, or the reverse direction.

Local evidence: `demo-artifacts/recipient-claude-workspace_changed-mwhhudt1/`
contains context, source manifest, workspace and verification output. The generic
verifier deliberately does not claim it can identify who edited the files.

### Fresh real source-host attempts

- `python scripts/live_demo.py codex`: no stage-1 file was created. The child
  agent reported that its actual read-only sandbox rejected `registry.py`, despite
  the harness requesting workspace-write. Its process exit code was 0, which is
  **not a successful acceptance**. Broad substring error signals in the harness
  output are not used to classify the failure; the final agent message was read.
- `python scripts/live_demo.py claude`: exit 1, `Not logged in`, no stage-1 file.
- No credential/provider configuration or sandbox bypass was attempted. Real
  interrupted-source -> opposite agent -> final tests remains **BLOCKED** by these
  source-host execution conditions. Desktop click/chip/submission is still **NOT RUN**.

### Repeatable recipient trial

`scripts/continuation_trial.py` prepares isolated synthetic sources and a temporary
Git workspace. It never calls a model or supplies the missing implementation.
Supported scenarios: `interrupted`, `workspace_changed`, `retry_succeeded`, and
`duplicate_titles`, each with Claude or Codex source format.

```sh
python scripts/continuation_trial.py prepare --agent claude --scenario workspace_changed
# Give the returned context.md and workspace to the receiving agent; request continuation.
python scripts/continuation_trial.py verify <returned-trial-root>
```

The verifier fails before implementation, rejects changes to the protected code
prefix, checks source/test hashes, and refuses to execute modified acceptance
tests. Automated verifier tests use a synthetic receiver and are not counted as
model execution. Final acceptance still requires an authenticated/writable source
host and actual native selection in each receiving client.

Local pre-edit copies for this follow-up are under
`demo-artifacts/continuation-baseline-20260905-231547/`, with SHA-256 manifest.
No commit, push, release or persistent host configuration change was made.

## Structure and stability follow-up — 2026-09-05

- Fresh result: **76 automated tests pass** (67 baseline + 9 regression cases).
  `python -m unittest discover -s tests -q` and `python scripts/demo.py` pass.
- MCP validates tool arguments against the same schemas exposed by `tools/list`.
  Malformed queries, argument containers, completion targets and resource URIs
  return errors; subsequent requests remain usable. Fixed workspace paths are
  normalized consistently before authorization checks.
- Workspace file inspection is isolated per operation, reads at most 1 MiB + 1
  byte, and records unavailable files as uncertain. One locked/disappearing file
  no longer prevents the remaining evidence from being returned.
- Recent conversation rendering reserves space across the last eight messages,
  preserves both ends of long messages and emits valid bounded JSON with explicit
  omission markers. It no longer cuts the entire section from its beginning and
  silently loses the newest reply. This remains a lossy context, not a complete
  transcript or a semantic summarizer.
- Native selected resources now carry receiving-task guidance even when the host
  attaches only a resource, without invoking the plugin skill: reconcile current
  files and continue when requested; selection alone does not authorize writes.
  Resource reads without a configured workspace explicitly require the receiving
  agent to check its established current workspace before editing.
- Fresh **installed Codex app-server** checks pass for Claude, Grok, OpenCode and
  Antigravity: native mention extension metadata, candidate search, and selected
  resource reads. Each uses isolated synthetic stores; no private session body or
  model call is involved. Reproduce with `python scripts/check_native_mentions.py
  --agent <name>` (run the command on one line).
- **Goal assessment:** selection and continuation-context transport are implemented
  and verified at the protocol layer. Real Desktop click/chip/submission behavior
  and an actual receiving model completing an interrupted task are still **NOT
  VERIFIED in this follow-up**. Historical authentication failures below have not
  been rechecked and are not claimed as current blockers.
- Remaining acceptance: in a disposable project, select a known interrupted
  session using the real `@` menu and ask the recipient to finish its pending
  feature. Verify it uses the exact selected source, preserves already completed
  work, reconciles current changes and passes the project's final tests. Record
  UI selection and model execution separately, in both directions.
- Scope: local source and documentation only; no host/plugin configuration,
  credentials, source-session files, commit, push or release changes. Pre-edit
  copies and SHA-256 manifest are in the ignored local directory
  `demo-artifacts/structure-stability-baseline/`. All repository content was
  already untracked on unborn `main`; these files must not be treated as newly
  generated by this follow-up.

## Added sources: Grok / OpenCode / Antigravity

- 67 automated tests pass, including the original 56. Added checks cover chunk
  assembly, failed commands, incomplete tails, raw-chat fallback, private reasoning
  exclusion, SQLite WAL visibility and read-only enforcement, reverted history,
  root escape rejection, bounded protobuf parsing, corrupt-source isolation,
  subagent filtering and independent refreshes against a shared index.
- Each new source passed `scripts/check_native_mentions.py --agent <name>` using
  the installed Codex app-server and synthetic data: extension declaration,
  candidate search and selected-resource context read. No model was called.
- `scripts/verify_extra_agents.py` exercised each installed plugin's actual MCP
  command: 60 Grok / 34 OpenCode / 35 Antigravity main-session candidates and
  dynamic completion. This check never selects a private session body.
- Codex plugin list confirms the three new personal plugins installed/enabled;
  the existing Claude plugin remains installed/enabled. Claude `mcp get` reports
  all three Connected. Source plugin and skill validators passed.
- Exact configuration comparison: no non-plugin Codex values changed, existing
  Codex plugins preserved; unrelated Claude settings and MCP entries preserved.
- Antigravity remains experimental: user/assistant text and commands are decoded;
  non-command tool payloads and attachments have explicit uncertainty warnings.
  Newer populated OpenCode event projections are not supported and fail closed.
- NOT RUN: new Desktop visual submenu/chip verification and actual hosted-model
  continuation. MCP/app-server success does not establish those acceptance gates.

The sections below describe the earlier Claude/Codex verification history.

## DSH `@` session-reference plugin

- `integrations/dsh/agentref-dsh` is a local-linked DSH `web` profile plugin.
  Its host route runs the existing AgentRef executable with argument arrays;
  candidate responses are source-filtered, metadata-only, and capped at 50.
  Context requires one exact reference returned by the current candidate list.
- The browser half recognizes `@claude`, `@codex`, `@grok`, `@opencode`, and
  `@antigravity`, presents a local candidate menu, and never chooses a session
  automatically. Selecting a row shows an explicit marker; just before send,
  the client appends the bounded AgentRef continuation context to that one
  message. There is no DSH-native MCP chip API in the installed host, so this
  is an explicit composer marker rather than a hidden resource attachment.
- `pnpm --dir integrations/dsh/agentref-dsh run check` passed (syntax, client
  build, and two host-boundary tests); the existing AgentRef suite passed
  105 tests. A live command-resolution probe returned 34 Claude candidates
  with no source path in the browser-facing metadata. DSH started the composed
  `web` profile on an isolated loopback port; an unauthenticated browser request
  was rejected with HTTP 401.
- NOT RUN: authenticated DSH browser click/marker/submission visual proof and
  hosted-model continuation. Authentication, model credentials, and any source
  session body were not used for these checks.

## Current native mention integration

- 56 automated tests pass, including saved Codex title lookup, rename refresh,
  cached injected-title repair, custom-root isolation, chronological ordering despite copied-file
  mtimes, metadata-only browsing, dynamic completion, exact selected resource reads,
  old URI compatibility and cross-agent isolation.
- Installed Codex app-server 0.147.0: native mention tool metadata survives inventory;
  `mcpServer/tool/call` returns candidates and `mcpServer/resource/read` returns the
  selected synthetic context. Reproduce: `python scripts/check_native_mentions.py`.
- Codex Desktop 26.901.5280.0 bundled code was inspected read-only. It recognizes
  `openai/extensions` -> `mentions/search`, consumes structured `items` with
  `type`, `title`, `resourceUri`, and attaches a submenu to the owning plugin.
  User-provided Desktop screenshot confirms the chronological Claude submenu.
  Submitted real-session context consumption remains unverified.
- Claude Code 2.1.261 actual terminal: `@codex` -> select the diamond template entry
  -> Tab -> newest-first short session candidates -> Tab inserts the reference.
  Ordinary fuzzy resource search was observed reordering older sessions first;
  `--template-menu` uses dynamic completion to preserve server order instead.
- Claude test prompt submission returned `Not logged in`; model continuation is
  still BLOCKED. No credentials or provider settings were changed.
- Both installed integrations updated. See [current usage](LOCAL_SETUP.md).
- Codex names now come from the adjacent `session_index.jsonl` when available;
  actual user requests supply fallback titles. Injected wrapper titles are repaired
  in AgentRef's derived cache without changing source history. Claude completion
  displays names only (up to 36 characters), with numeric suffixes only for
  colliding names. Aliases persist across restarts and renames, while chronological
  order remains independent of labels. Legacy token URIs remain readable. Local
  real-metadata completion and actual Claude terminal menu were checked after this fix.
- Fresh installed MCP metadata inventory: 30 Claude sessions and 1,298 Codex
  sessions, about 650 ms per subprocess query on this machine. No private session
  context was selected for this check; counts are a point-in-time snapshot.

## Historical picker correction (superseded by native menu above)

The earlier real user task returned cancellation instead of
showing a usable picker. Default selection now returns numbered candidates;
MCP forms require explicit --native-picker. Error responses are no longer mapped
to cancellation. 38 tests pass; real local MCP yields 29 candidates with no form
request. This verifies the server, not another live Desktop user attempt.
At that stage, individual session autocomplete in the composer was unimplemented.

## Follow-up: installed local @ integration

See [LOCAL_SETUP.md](LOCAL_SETUP.md). Now installed: `claude@personal` in Codex,
user-scoped `codex` MCP in Claude and Store Desktop MCP entry. Actual Codex CLI
@claude autocomplete and native MCP elicitation session form were observed, with
cancel returning without reading a source body. Actual Claude @codex autocomplete
listed MCP resources. 36 tests now pass. Desktop UI and bidirectional model
continuation remain unverified. `ocx claude` reports its inbound integration disabled;
native Claude remains unauthenticated. No provider switch was made.

The table below records the original alpha baseline; the follow-up above supersedes
its test count, native CLI picker status and statement that no host config changed.

## Evidence by layer

| Layer | Result |
|---|---|
| Format investigation | Official docs, pinned Codex source, bounded local schema-key probe |
| Installed hosts | Claude Code 2.1.251; Codex CLI 0.147.0 |
| Current npm versions | Claude Code 2.1.261; Codex 0.153.4; not installed here |
| Automated tests | 30 unittest cases; temporary synthetic sources only |
| CLI integration | sessions/context via subprocess, doctor, numbered selection logic |
| MCP transport | real stdio subprocess initialize/list; in-process resource/context roundtrip |
| Source immutability | source-byte equality tests; own live Codex session SHA-256 unchanged |
| Packaging | wheel built and installed in repo-owned .venv; console entry starts |
| Synthetic bidirectional demo | both fixture directions pass; not model continuation |
| Real Codex source demo | launched; host refused first write under read-only sandbox; no stage-1 file |
| Real Claude source demo | launched; Not logged in / 403; no stage-1 file |
| Actual interrupted -> other agent -> final tests | BLOCKED in both directions |
| Native bare @ autocomplete | not implemented; resource picker / tools / terminal fallback |
| Desktop live UI | NOT RUN |
| Cross-platform CI | workflow supplied; not run remotely |

Commands:

```sh
python -m unittest discover -s tests -v
python scripts/demo.py
python -m pip wheel --no-deps --wheel-dir dist .
```

## Performance sample

1,000 synthetic small Codex files on this Windows machine: cold metadata index
654.9 ms, warm discovery/stat refresh 340.3 ms, warm transcript bytes read = 0.
This is a single small-file sample, not a guarantee for large histories, slow disks,
network mounts or cold filesystem caches. Selected context currently parses the
whole selected session in memory; picker never stores it in SQLite.

## Real demo attempts

`python scripts/live_demo.py codex` and `python scripts/live_demo.py claude`
created separate repo-owned demo workspaces. Neither reached the controlled pause.
Codex was requested with workspace-write, but its tool result reported a read-only
sandbox rejection. No bypass flag was used. Claude's attempt failed authentication.
The harness never reads, prints, stores or requests credentials and does not change
host config. Raw host logs remain in ignored local demo-artifacts; they are not
fixtures or release content. No host session was resumed or altered by AgentRef.

To finish acceptance, a writable Codex execution environment and an authenticated
Claude CLI are needed. Then start each controlled source demo, select its actual
session through the host integration, have the opposite agent reconcile and finish
rollback, verify registry's completed portion was preserved, and run unittest.
Record native selection separately from a CLI/MCP fallback. Desktop UI remains
a separate manual check; don't label a fixture or tool response as UI proof.

## Current limits

- Deterministic operation evidence only; no LLM summarizer or dependency solver.
- Full-content Write / Add File can be verified by hash. Generic Edit, shell writes,
  opaque JavaScript and semantic feature completion require recipient verification.
- Git evidence uses status, diff statistics and recent log; no arbitrary diff helper,
  fsmonitor, test command or transcript command is executed.
- Explicit workspace must be a Git root for repository-wide evidence. Files outside
  it, sensitive paths and large files are excluded; lack of access stays uncertain.
- Internal storage formats can drift; latest npm binaries and every schema variant
  have not been exercised. Missing terminal events mean incomplete/unknown, not a
  confidently diagnosed crash, Ctrl+C, or quota failure.

## Local changes and rollback

All project code, fixtures, build output, virtualenv and demos are under `agentref/`.
A new main Git repository was initialized; no commits, remote, push or release.
No personal MCP configuration or global package installation was changed.
Uninstalling a future integration means removing only the added server entry.
AgentRef's own index can be rebuilt; foreign session directories must be preserved.
