# AgentRef v0.1 architecture

Local cross-agent session reference layer. Python 3.11+ standard library, SQLite,
JSONL adapters, terminal picker and a local stdio MCP server. No network client,
model calls, telemetry, session resume, or transcript command execution.

Flow: vendor JSONL -> tolerant adapter -> Session IR -> current workspace evidence
-> continuation context -> CLI / MCP resources and tools.

Adapters own all vendor-specific fields. Core exposes discoverSessions,
getSessionMetadata, readSession, readSessionIncrementally, extractWorkspace and
getSessionStatus. Unknown schemas degrade with warnings; EOF never proves success.
SQLite stores metadata and byte offsets only, never conversation bodies. Listing
stats discovered files and reads only appended bytes for changed files. Context
reads the selected source afresh. Incomplete last lines are retried next refresh.

Workspace is supplied explicitly by the caller; a transcript cwd alone does not
authorize reading it. Git invocations are fixed read-only argument arrays, with
optional locks disabled, no external diff or textconv. File evidence is confined
to the resolved workspace and excludes sensitive paths and symlink escapes.
Historical tool success is historical evidence, not proof that current tests pass.
Natural-language claims remain uncertain. File existence never proves a feature.

State: COMPLETED, PARTIAL, NOT_STARTED, FAILED, UNCERTAIN, each with evidence.
COMPLETED applies to evidenced operations, not inferred product acceptance.
Handoff includes provenance and treats all foreign text as untrusted data.

`evidence.py` annotates conservative historical supersession without mutating the
Session IR. Exact command/cwd retries and successful full writes can supersede
older entries for continuation purposes; history and original statuses survive.
Explicit pending plans precede opaque historical operations in suggestions.
An acknowledged completed plan remains agent-reported, not verified completion.
Tool calls capture cwd when observed, before subsequent turn-context changes.
File supersession requires matching known source directories; relative file paths
from another source directory are not silently mapped to the current workspace.

Within the handoff layer, `inspect_operation` owns bounded per-file evidence and
failure isolation; `reconcile` assembles current state; `recent_conversation`
allocates a bounded context across recent turns, preserving both ends of long
messages. `build_context` composes that evidence and the receiving-task policy.
`context_render.py` owns per-section allocations within a 32,000-character total
ceiling. Structured truncation retains newest entries, emits valid JSON and makes
omissions visible. Original goal, latest intent and current state receive reserved
space before historical details; this is still a lossy evidence view.
A native resource read may have no workspace: the recipient must reconcile its
explicit current workspace before continuing. Selection is reference authority;
the current user's request determines implementation authority.

The MCP boundary validates tool arguments using its advertised tool schemas, so
discovery and execution share one argument contract. Invalid inputs are rejected
before index or workspace access. Metadata timestamps tolerate invalid source
values and fall back to file time (or the epoch when that is invalid too).
Detected refresh failures propagate diagnostics to MCP callers; partial inventory
never silently establishes a unique alias selection. Native search caps output
at 100 candidates while filtering the full inventory. JSONL discovery failures
retain cached entries for that adapter, as snapshot failures already do.
JSONL parse warnings survive cache hits. A changed warning-bearing source is
reparsed from zero before clearing its diagnostic, preventing valid appends from
masking earlier corrupt records.

Foreign files are opened read-only. Index lives under AgentRef's own data home.
MCP exposes only indexed identifiers, never an arbitrary file-read or execute tool.
No global integration settings are modified by installation or tests.

## Additional sources

`adapters/registry.py` registers Claude, Codex, Grok, OpenCode and Antigravity.
CLI options and MCP source schemas derive from that registry / exposed adapters.
A filtered MCP process discovers only its selected source. Shared-index cleanup
is scoped by agent, so concurrent source-specific servers cannot purge each other.

Snapshot adapters expose `scan_metadata()` and `read_indexed(row)`. Grok indexes
main-session summaries, then reads the selected authoritative ACP update stream
(raw chat fallback is warned). OpenCode enumerates main-session SQL rows and
uses a virtual `database-path::session-id` locator, validated against configured
roots before a parameter-bound read. Databases use SQLite `mode=ro`, query-only
transactions and WAL-aware reads; they are never opened with `immutable=1`.
Transient metadata failure retains prior entries and reports an error.

Antigravity indexes main trajectories from Desktop and CLI stores. It interprets
only field numbers verified against the installed protobuf descriptors, rejects
malformed wire data, and excludes thinking/signatures. Unknown tool payloads stay
explicitly uncertain. This adapter is experimental and needs schema revalidation
after upstream format changes. No generic binary-string extraction is used.
