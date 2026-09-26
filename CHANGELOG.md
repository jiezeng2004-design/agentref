# Changelog

## 0.1.0-alpha.3 — 2026-09-26

GitHub prerelease only; publication status and final commit/asset evidence are
recorded on the release page. No PyPI/npm publication or new native-host/model
acceptance is implied by this version entry.

- OpenCode TUI and the opt-in Antigravity menu now ask the local index for a
  bounded 51-row query page before showing at most 50 choices. A final sentinel
  reports that more matches exist; selecting one revalidates its exact ref.
  Older AgentRef CLIs fall back to their compatible full-list behavior, subject
  to the existing subprocess output bound.
- Node CI now syntax-checks the Antigravity runtime and runs its broker contract
  tests alongside the DSH and OpenCode integration suites.
- Codex add-file `patch_apply_end` sideband evidence now retains exact content
  hashes and provenance, deduplicates compatible records and leaves conflicts
  uncertain. Unsupported change shapes still warn. Prior warning-bearing Codex
  metadata is rechecked once through index version 2; source files are untouched.
- Live source harness now requires `--allow-live`, preserves configured model
  routes, validates a per-run pause and protected stage before passing, returns
  nonzero for failed acceptance, and cleans up its owned child on interruption.
  DSH plugin installation now previews by default and requires `--apply`.
- DSH metadata reads use a separate 8 MiB transport budget; selected context
  retains its 256 KiB limit. The CLI now filters and bounds session rows before
  serialization; exact selection revalidates one row. Older CLIs fall back to
  the legacy full-list call, which can still exceed the metadata limit.
- DSH menus preserve an incomplete-index signal from successful CLI diagnostics,
  including empty results, without exposing raw stderr on that success path.
- Added real child-process overflow tests and synthetic-browser warning checks;
  browser evidence now uses unique output directories to preserve earlier runs.
- Added a current acceptance matrix separating released CI, unpublished local
  checks and native-host/model gates. No new release or host reload is implied.
- Added backward-compatible `sessions --query --limit --offset` options and
  routed DSH search and exact-reference revalidation through bounded CLI output.
- Preserved adapter diagnostics during metadata indexing and corrected a stale
  test expectation for timestamped session labels.
- Unfiltered `sessions` pages now use SQLite ordering and pagination before
  Python row materialization; the synthetic benchmark checks page equivalence.
- The `sessions_agent` index now includes the recent-order key and ref, so
  source-filtered pages and keyword pages can avoid a temporary sort. Existing
  AgentRef indexes migrate transactionally; unbounded full-list ordering remains
  in Python where it measured faster.
- Exact ref and session-ID probes now use separate indexed branches; schema version
  4 adds a session-ID index so an absent exact match does not scan all sessions.
- Bounded multi-source keyword pages now take an ordered top-K slice per source
  before merging; exact totals use a count query in the same SQLite read snapshot.
- Repeated keyword pages on large indexes can use a process-local FTS5 trigram
  candidate index after repeated sparse-result searches. Refresh invalidates it only
  when indexed search fields or membership change; activity-only changes retain it.
  External DB changes rebuild it, while dynamic-title sources use the exact fallback.
  It stores casefolded trigrams with `detail=none`; dense-result choices are cached
  in a bounded per-process set and exact matching filters trigram false positives.
- The SQLite keyword matcher now uses one connection-lifetime dispatcher instead
  of registering and unregistering its callback for each search; this avoids a
  large empty-result FTS query failure and reuses prepared matcher statements.
- Repeating the same sparse keyword page twice can now activate the process-local
  FTS candidate index on that query's next use; mixed one-off sparse terms retain
  the existing broader activation threshold, and the pending build waits for the
  repeated query instead of penalizing an unrelated dense request.
- MCP completion now reads only matching base aliases in bounded batches and
  checks numbered conflicts by exact key, avoiding a full historical alias scan.
- Keyword pages now apply exact matching, overlay titles, and Unicode `casefold`
  in the SQLite candidate query while returning only the requested rows. Adapters
  without an equivalent title-overlay contract retain the full-list fallback.
- Snapshot refresh now skips SQLite replacement writes when scanned metadata is
  unchanged. DSH reuses already validated paths inside its metadata/read chain;
  every refresh still scans the source, so no invalidation shortcut is implied.
- Grok snapshot discovery now walks the live workspace/session tree with
  non-following `scandir`; unsafe entries keep old index rows on scan errors.
- OpenCode snapshot refresh reuses metadata for an unchanged database within the
  same Index process. The cache checks database/WAL signatures and the exact indexed
  source-path set; changes, replaced/missing rows, or source removal trigger a rescan.
- Snapshot rescans now prefetch existing rows once after the first metadata row
  and batch changed-row writes in groups of 512; cache hits skip this prefetch.
- Snapshot paths under canonical configured roots now use lexical containment plus
  explicit link/junction checks with one `lstat` per checked path, avoiding per-file
  realpath resolution and duplicate Windows link probes; DSH scan readers pass their
  already selected root, and alias-root fallback remains.
- Assistant natural-language plan extraction now reuses a module-level compiled
  pattern instead of resolving the cached regular expression for each line.
- `BaseAdapter.finish()` now skips generic file-path parsing for tool names that
  cannot create file-operation evidence and skips the base no-op event hook when
  an adapter does not override it; Codex event-operation overrides still run.
- Test-run detection in `BaseAdapter.finish()` now reuses a compiled pattern and
  the already stringified command value.
- Completed-call exit-code and file-tool success checks in `BaseAdapter.finish()`
  now reuse compiled patterns.
- The bounded JSONL scanner now tracks remaining bytes within its initial file-end
  snapshot instead of calling `tell()` before and after each record; this preserves
  offsets when the source grows and stops safely if it shrinks during a scan.
- Read-only handoff reconciliation now shallow-copies history records and copies evidence
  arrays only when it adds a supersession annotation; public history helpers retain deep-copy defaults.
- Continuation-candidate ranking packs priority and recency into integer keys for sized inputs,
  reducing per-candidate tuple allocations while preserving the tuple-key fallback for iterators.
- Handoff file-operation reconciliation without a workspace now builds the same uncertain-evidence
  record inline, avoiding an `inspect_operation()` call per file when no root exists.
- Handoff evidence aggregation now chains work/superseded lists instead of concatenating a temporary list.
- DSH compact UTF-8 JSONL object records now use a reusable `JSONDecoder.raw_decode`
  fast path; BOMs, CRLF, whitespace, and noncanonical lines retain `json.loads` fallback.
- The DSH event reader now loads each event envelope's `data` value once before validation
  and reuses it for dispatch.
- DSH surface snapshots now retain only sequence, event type, and data rather than the
  complete JSON event envelope, while preserving later compaction and message processing.
- Ordered DSH surface histories now locate compaction boundaries with binary search; a
  non-tail replacement switches to the original linear lookup to preserve arbitrary-range semantics.
- Pending DSH tool-call history now retains only sequence, name, and argument references
  rather than whole event/data dictionaries; later result matching remains keyed by call ID.
- DSH event-kind dispatch now uses module-level immutable sets for packed, surface, and
  passive event classes, avoiding repeated tuple scans in long histories.
- Empty session-query pages now use the indexed chronological listing path and a
  plain exact-count query instead of invoking the keyword matcher for every row;
  exact ref and session-ID matches retain precedence.
- DSH metadata discovery now reuses the root selected for each discovered path and
  walks the live `sessions/project/session` layout with non-following `scandir`; trusted
  leaves avoid repeating ancestor checks, while linked/failed entries preserve old index rows.
- Antigravity metadata now reads trajectory identity, workspace metadata, first user
  step and latest state with one SQLite statement per trajectory.
- Antigravity metadata discovery now uses up to eight concurrent read-only workers
  when scanning at least 32 database files; larger inventories submit small batches
  to reduce thread-pool scheduling overhead while preserving path order and per-file error isolation.
- Claude/Codex source discovery now walks with `os.scandir` without following
  symlinks or junctions, carries discovered file mtime/size into indexing, and
  loads existing rows once per source instead of issuing one SQLite query per file.
  The temporary discovered-stat map is released after each refresh.
- Index keyword matching now finds a cwd basename without constructing a `Path`
  for every row; SQL session ordering parses timestamps directly without a
  per-row temporary dictionary and keeps a bounded cache admitted after repeated
  ISO values. Cached order keys now use lock-free reads. Query pages check
  session-ID prefixes before cwd work and reuse up to 1024 cwd-basename results
  within each query.
- Index browsing now reuses the parsed local derived-title cache while its
  file signature is stable, and reloads after external or atomic replacement.
- Empty derived-title caches now skip per-session identity checks during browsing.
- Alias-base normalization now uses a printable-text fast path, C-level ASCII
  translation, and retains the full control-character normalization fallback.
- Dynamic mention completion now keeps stable aliases for an unchanged
  metadata/overlay inventory and queries only the matching page on subsequent
  keystrokes; database, derived-title, and Codex saved-title changes invalidate it.
- Large alias inventories are ordered through bounded SQLite batches instead of
  retaining every session metadata row at once; small inventories keep the faster full-list path.
- The numbered-alias suffix cursor now spans streamed inventory batches so duplicate groups
  continue monotonically when a large metadata refresh crosses batch boundaries, while still
  selecting earlier free suffix gaps behind reused aliases.
- Refreshes that change only activity/status metadata now advance the alias
  inventory version without rebuilding aliases; identity/title changes and deletions invalidate it.
- When a completed refresh changes only a subset of alias identities, the warm inventory
  reconciles those refs incrementally instead of rereading every session row.
- When an agent's alias table is empty, first-time alias reservation now assigns
  aliases in one pass with a per-base suffix cursor, including cross-title suffix conflicts.
- First-time alias inserts are sorted by `(agent, alias)` to improve SQLite primary-key write locality.
- Existing duplicate aliases now preload bounded numbered candidates in batches
  and advance a per-base cursor, preserving ref-owned aliases after inventory
  reordering and avoiding repeated exact queries for every suffix.
- Refresh cleanup now queries stale rows only for enabled adapters, avoiding
  materializing unrelated sources from a shared index; it streams existing
  source paths and batches stale-row deletion.
- Snapshot path checks now use a lexical fast path for canonical roots, while
  retaining the alias fallback and per-ancestor symlink/junction rejection.
- Incremental indexing and selected Claude/Codex/Grok reads now consume JSONL
  records as they parse instead of holding a second session-sized record list.
- Metadata-only index scans count parse warnings as they stream rather than storing
  one warning string per malformed/unknown record.
- DSH selected-session parsing now reduces events as they arrive, retaining only
  the visible surface and latest tool calls instead of an additional full event list.
- Bounded context JSON rendering now stops encoding once the budget is exceeded,
  sizes recent evidence incrementally, and streams excerpts for an oversized newest entry.
- Recent assistant decision extraction now retains only the last eight matching lines
  while scanning messages, avoiding an intermediate list proportional to conversation length.
- Continuation ranking now keeps the best rank per task and selects top-k without
  sorting all historical work entries.
- Tool-result lookup now indexes the latest call per ID, preserving reverse-scan
  behavior for reused IDs while avoiding repeated linear searches.
- Codex patch sideband reconciliation now indexes direct file operations by
  call/path/workspace before merging, retaining conflict handling and file order.
- Codex `patch_apply_end` duplicate detection now indexes evidenced call/turn IDs
  instead of rescanning all earlier tool calls for every event.
- Metadata overlays now group rows by source in one pass before dispatching each
  adapter hook, preserving adapter order and row order.
- CLI `inspect` now serializes `SessionIR` fields directly instead of building an
  `asdict()` deep copy before JSON encoding; the existing `to_dict()` API remains.
- OpenCode title derivation now reuses one metadata projection per session; Antigravity
  stops workspace URI parsing at the first local path. OpenCode derives bounded user
  titles with one query for up to 128 messages instead of a parts query per message.
- OpenCode selected-session reads now fetch ordered message parts in one join instead
  of issuing a part query for each message.
- OpenCode snapshot scans now yield metadata directly from the read-only SQLite cursor
  rather than materializing a per-database list of `SessionIR` objects.
- Handoff Git state reads (status, both diff summaries, log, and HEAD) now run in
  parallel after root verification; each command keeps independent timeout/error handling.
- MCP `resources/list` now asks the index for a bounded 101-row page, exposing 100
  results plus a next cursor without materializing the full catalogue in Python.
- MCP `search_mentions` now requests a 100-row page plus an exact SQL total, rather
  than loading every match merely to set `total`/`hasMore`.
- Mention alias allocation now loads existing alias ownership once and batch-inserts
  new reservations inside a write-serialized transaction.
- MCP context reads now validate the exact source/hash reference and use the indexed
  single-row lookup rather than listing every session before reading one selection.
- Mention-alias lookup now has an additive alias-first covering index for resource reads.
- MCP resource completion now filters the already loaded ordered inventory, avoiding a
  second full `sessions` query before stable alias lookup.
- Conversation picker now reads at most 31 candidates to distinguish a unique match
  from an ambiguous list, then displays at most 30.

## 0.1.0-alpha.2 — 2026-09-15

- OpenCode TUI session dialog with explicit selection and draft-only context attachment;
  shared post-send receiving-host integration and guarded, opt-in setup tools.
- DSH keyboard navigation, debounced searches, shared in-flight metadata queries,
  and protection against cancelled/stale responses and overwritten draft edits.
- Source-filtered SQL queries, explicit adapter indexing contracts, a shared source
  catalog, and bounded agent-menu inventory caching.
- Expanded setup preservation, source isolation, Unicode, documentation, integration,
  and installed-wheel checks; wheel smoke tests added to the cross-platform CI matrix.

Local release checks: 167 Python tests (166 passed, one Windows symlink skip),
16 DSH tests, 7 OpenCode TUI tests, synthetic bidirectional demo, seven scale
scenarios across six sources, and a 12,000-row query-equivalence benchmark passed.
Final package and remote CI evidence is recorded in RELEASE_READINESS.md.

GitHub prerelease only; no PyPI/npm publication. DSH remains private. No host
configuration, restart, real-session read, or live-model continuation is performed
by this release. Original alpha.1 demo assets remain historical and unchanged.

## 0.1.0-alpha.1 — 2026-09-11

First public alpha of AgentRef, a local, read-only session reference layer for AI coding agents.

- Claude Code, Codex, Grok, OpenCode, Antigravity (experimental), and DSH session sources.
- CLI and MCP discovery, explicit session selection, and bounded continuation context.
- Codex native mention integration, Claude resource completion, and a DSH Web plugin.
- Source evidence and workspace reconciliation without executing transcript commands.
- Native-menu demo, offline showcase bundle, and an installable Python wheel.
- macOS system ancestor path aliases are accepted without allowing symlinks inside session roots.

Local validation: 132 Python tests (one symlink test skipped on Windows), 9 DSH tests, synthetic bidirectional integration,
wheel installation/startup, and complete video decoding passed. The demo covers entry
lookup and session browsing. Full native selection-to-model continuation is not
certified across all hosts. Host storage formats and mention interfaces may change.

This is a GitHub prerelease. No PyPI or npm publication is included; the DSH package
remains private and is distributed as source. See RELEASE_READINESS.md for limits.
