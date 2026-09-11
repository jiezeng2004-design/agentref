# Changelog

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
