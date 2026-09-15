# Historical README verification notes

The following blocks were moved from the README without upgrading their evidence.
Counts, installed-host behavior and release artifacts describe their original
snapshot, not the current checkout. Use [development checks](DEVELOPMENT_CHECKS.md)
for reproducible current local checks and [the guide](README.md#verification) for
the other evidence records. No remote release or CI state was rechecked by this move.

## Local prerelease check — 2026-09-11

132 Python tests (one Windows symlink skip), 9 DSH tests, synthetic bidirectional
integration and alpha wheel build passed. The supplied demo shows native entry
lookup and session-list browsing. See [release readiness](../RELEASE_READINESS.md)
for the associated evidence and open gates.

## Follow-up local fixes — 2026-09-11

136 Python tests (one Windows symlink skip), 13 DSH tests, synthetic bidirectional
integration and all-source scale checks passed, including plain and compressed
DSH logs. Pending-search cancellation, whitespace-preserving mention replacement
and source-scoped queries are fixed. The DSH bundle was rebuilt; host UI and a new
release package were not revalidated.

## Earlier v0.1 alpha host observation — undated README snapshot

Codex's `@claude` plugin exposes a native session submenu using the installed
desktop client's mention extension; its app-server call/read chain passes.
Claude Code's `@codex` -> diamond entry -> Tab opens chronological session
abbreviations before sending; real terminal selection was verified. Codex Desktop
click/chip rendering and full cross-agent model continuation remain separate
acceptance gates; see [verification](../VERIFICATION.md). MCP forms stay opt-in.
Maintainer-machine setup history: [本机使用记录](../LOCAL_SETUP.md).
These historical records do not configure a fresh installation.
