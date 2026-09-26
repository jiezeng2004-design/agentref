# Documentation guide

This guide describes implementation boundaries in the working checkout. It is
not a claim that every installed host version or the published alpha implements
the same interaction. A source adapter and a receiving-host integration are
different capabilities.

## Sources

| Source | Parsed store | Important boundary |
| --- | --- | --- |
| Claude | Content-block JSONL | Incremental metadata indexing; selected body read |
| Codex | Rollout JSONL and adjacent title index | Incremental indexing; saved-title overlay |
| Grok | Summary metadata and ACP updates | Raw-chat fallback is explicitly warned |
| OpenCode | SQLite message/part records | Read-only database with WAL visibility |
| Antigravity | SQLite and Step protobuf | Experimental; unsupported tool payloads remain uncertain |
| DSH | Version-0 JSONL / JSONL.zstd | Unknown versions and ambiguous representations fail closed |

The machine-readable descriptions live in `agentref/sources.py`; registration
lives in `agentref/adapters/registry.py`. Gemini CLI and Qoder are not enabled.

## Choose a receiving interaction

| Receiving surface | Implementation path | Setup and limits |
| --- | --- | --- |
| Codex | MCP mention/resource integration and agent-entry menu | [Codex integration](../integrations/codex/README.md) |
| Claude | MCP resources / ordered template completion | [Claude integration](../integrations/claude/README.md) |
| DSH Web | Composer list, explicit marker, CLI-generated context | [DSH Web integration](../integrations/dsh/agentref-dsh/README.md) |
| OpenCode TUI | Native dialog, selected draft attachment, CLI | [OpenCode TUI integration](../integrations/opencode/agentref-tui/README.md) |
| Other configured receiving hosts | Post-send numbered selection skill | [Shared integration](../integrations/shared/README.md) |

Opening a list does not authorize selecting a session. An exact selection permits
reading that session; the current request still determines which work is allowed.
The receiving model/client may transmit attached context under its own policies.

## Verification

- [Current acceptance matrix](CURRENT_ACCEPTANCE.md): baseline commit, local
  unpublished changes, dated remote evidence and remaining native/model gates.
- [Development checks](DEVELOPMENT_CHECKS.md): reproducible local commands and their limits.
- [Script safety index](SCRIPTS.md): synthetic checks versus installed-host inspection,
  configuration writes, and real-model execution.
- [Dated verification notes](VERIFICATION_HISTORY.md): former README snapshots,
  preserved as historical observations rather than current acceptance.
- [Detailed verification history](../VERIFICATION.md): dated protocol, UI and
  continuation evidence, including partial and failed checks.
- [Release readiness](../RELEASE_READINESS.md): dated release-local evidence and
  remaining release/host gates; not a live remote CI or registry status page.
- [OpenCode TUI verification](../integrations/opencode/agentref-tui/VERIFICATION.md):
  integration-specific evidence and limitations.

## Architecture and maintenance

- [Architecture](../ARCHITECTURE.md): adapter, index, evidence and context boundaries.
- [Format findings](../SESSION_FORMAT_FINDINGS.md): source-format observations.
- [Implementation plan](../IMPLEMENTATION_PLAN.md): design/planning history, not a test result.
- [Maintainer setup history](../LOCAL_SETUP.md): machine-specific configuration notes,
  not proof that another machine is configured.
- [Main README](../README.md): local startup, privacy and explicit title extraction.
