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
| DSH | Version-0/3/4 JSONL / JSONL.zstd | Newest formal generation selected; unknown versions and ambiguous representations fail closed |

The machine-readable descriptions live in `agentref/sources.py`; registration
lives in `agentref/adapters/registry.py`. Gemini CLI and Qoder are not enabled.

## Choose a receiving interaction

| Receiving surface | Implementation path | Setup and limits |
| --- | --- | --- |
| Codex | MCP mention/resource integration and agent-entry menu | [Codex integration](../integrations/codex/README.md) |
| Claude | MCP resources / ordered template completion | [Claude integration](../integrations/claude/README.md) |
| DSH Web | Native input source on the adapted 0.2 host; legacy composer fallback | [DSH Web integration](../integrations/dsh/agentref-dsh/README.md) |
| OpenCode TUI | Native dialog, selected draft attachment, CLI | [OpenCode TUI integration](../integrations/opencode/agentref-tui/README.md) |
| Other configured receiving hosts | Post-send numbered selection skill | [Shared integration](../integrations/shared/README.md) |

Opening a list does not authorize selecting a session. An exact selection permits
reading that session; the current request still determines which work is allowed.
The receiving model/client may transmit attached context under its own policies.

## Find an older session without reading its body

The MCP `sessions` tool accepts a source, optional metadata query and page:

```json
{"agent": "codex", "query": "rollback", "limit": 50, "offset": 0}
```

The query filters titles, project names and session identifiers before the page
limit. The default is 50 rows, the maximum is 100, queries allow 120 characters,
and offsets allow 0 through 1,000,000. The first text content remains the session
array. `_meta.pagination` reports the matching `total`, `hasMore` and, when more
rows remain, `nextOffset`. Pages with more matches or a nonzero offset also include
pagination as text so the receiving agent can explain the list boundary. Index warnings are
reported separately; an unavailable source can leave stale or missing candidates.

Use `nextOffset` with the same source and query for another page, or narrow the
query. Each call refreshes metadata, so new activity can change page order between
calls; bind the user's choice to the exact ref actually displayed, never to a
number re-applied after a refresh. No listing, filtering or paging reads session
context or automatically selects a match. Only read the exact selected ref.

The CLI supports the equivalent metadata query:

```sh
agentref sessions --agent codex --query rollback --limit 50 --offset 0 --json
```

The CLI returns an array and does not include the MCP pagination metadata.
These interfaces describe the working checkout; an installed older alpha may
need updating before accepting the additional MCP arguments.

## Verification

- [Real-host tests, 2026-10-09](REAL_TESTS_2026-10-09.md): real Codex ↔ DSH
  continuation, DSH Web and OpenCode TUI checks, and authentication/UI blockers.
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
