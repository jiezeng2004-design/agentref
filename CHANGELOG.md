# Changelog

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
