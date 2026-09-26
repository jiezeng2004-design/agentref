# AgentRef v0.1 architecture

Local cross-agent session reference layer. Python 3.11+, SQLite,
JSONL adapters, terminal picker and a local stdio MCP server. No network client,
model calls, telemetry, session resume, or transcript command execution.

DSH compressed sessions use `zstandard` on Python below 3.14 and the standard
library compression module on Python 3.14+.

Flow: vendor JSONL -> tolerant adapter -> Session IR -> current workspace evidence
-> continuation context -> CLI / MCP resources and tools.

Adapters own all vendor-specific fields. Core exposes discoverSessions,
getSessionMetadata, readSession, readSessionIncrementally, extractWorkspace and
getSessionStatus. Unknown schemas degrade with warnings; EOF never proves success.
The index uses explicit `index_mode` (`incremental` or `snapshot`), described by
the protocols in `core.py`, rather than inferring a mode from optional methods.
All adapters own `read_indexed(row)` and enforce their source locator boundary.
Metadata-only `overlay_metadata(rows)` and incremental `metadata_needs_refresh`
hooks keep source-specific title policy out of the index. The existing Codex
cache migration remains in the index because it belongs to the database schema.
Grok walks the live workspace/session tree with non-following directory scans and
rejects linked source ancestors before reading summary metadata.
SQLite stores metadata and byte offsets only, never conversation bodies. Listing
filters enabled/requested sources in SQL using an additive agent index, then sorts
by normalized session time and exact ref in Python. Source refresh still
stats discovered files and reads only appended bytes for changed files. Context
reads the selected source afresh. Incomplete last lines are retried next refresh.
Large histories may build a process-local FTS5 trigram index after repeated
sparse-result searches. It contains title, session ID and cwd metadata only;
dense-result searches and dynamic title overlays use the exact SQL/Python fallback.
Refresh invalidates it when search-document fields or session membership change;
activity-only metadata updates retain the cache. External DB changes invalidate it
through `data_version`. Dense candidate decisions are held in a bounded,
process-local cache to avoid repeating the FTS probe. The index stores casefolded
trigrams without positional detail; the exact matcher filters candidate false positives.

Workspace is supplied explicitly by the caller; a transcript cwd alone does not
authorize reading it. Git invocations are fixed read-only argument arrays, with
optional locks disabled, no external diff or textconv. File evidence is confined
to the resolved workspace and excludes sensitive paths and symlink escapes.
Historical tool success is historical evidence, not proof that current tests pass.
Natural-language claims remain uncertain. File existence never proves a feature.

State: COMPLETED, PARTIAL, NOT_STARTED, FAILED, UNCERTAIN, each with evidence.
COMPLETED applies to evidenced operations, not inferred product acceptance.
Handoff includes provenance and treats all foreign text as untrusted data.

Codex sideband `patch_apply_end` events are recognized only for the observed
add-file shape. The adapter records historical success/failure, exact UTF-8
content hashes and event provenance without interpreting opaque JavaScript.
Identical event duplicates collapse; matching direct patch evidence retains its
original order. Conflicting status/hash evidence stays uncertain. Other change
types or malformed shapes retain warnings. The base adapter's event-operation
hook preserves tool chronology without embedding vendor fields in shared logic.
Index version 2 invalidates warning-bearing Codex metadata once; version 3 replaces
the agent-only session index with an agent/order/ref index for bounded recent pages;
version 4 adds a session-ID index for exact session lookup. These migrations retain
the indexed rows and touch only AgentRef-owned metadata.

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

`adapters/registry.py` registers Claude, Codex, Grok, OpenCode, Antigravity and DSH.
`sources.py` owns source labels, format descriptions and explicit Codex-menu
visibility. Source support is not the same as host menu visibility. Contract
tests keep the registry and self-contained JavaScript integrations consistent.
See [development checks](docs/DEVELOPMENT_CHECKS.md) for catalog and isolated-wheel
verification commands and their evidence boundaries.
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
