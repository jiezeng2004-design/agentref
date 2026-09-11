# Implementation plan

1. Findings and synthetic fixtures; tolerant Claude/Codex adapters and Session IR.
2. Discovery, SQLite metadata-only incremental index, CLI sessions/inspect/picker.
3. Explicit workspace reconciliation, evidence states, bounded handoff context.
4. Claude CLI/Desktop thin MCP configuration examples and resources.
5. Codex CLI/Desktop thin MCP configuration examples and tools.
6. Automated fixture/integration tests, local demo and honest acceptance report.

Release gate: actual Codex-interrupted -> Claude continuation AND reverse, with
real source sessions, current workspace evidence and final tests. Synthetic demos
are parser/integration evidence only. Native @ UI, logged-in host behavior and
model continuation must be reported separately. Never claim core concept accepted
until both real demos pass. Do not silently alter personal host configuration.
