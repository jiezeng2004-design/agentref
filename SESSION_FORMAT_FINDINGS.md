# Session format findings

## Additional source investigation (2026-09-05)

- Grok installed README, Session Persistence: `summary.json` is the metadata
  index; `updates.jsonl` is the authoritative ACP restore stream. Local key-only
  probes confirm `params.update.sessionUpdate`, chunk messages, tool-call IDs,
  rawInput/rawOutput, x.ai/tool metadata and terminal statuses. Main paths are
  `<encoded-cwd>/<session-id>/summary.json`; subagent directories are excluded.
  Missing update streams fall back to chat_history with an explicit limitation.
- OpenCode local `opencode.db`: session/message/part tables. Metadata includes
  title, directory, parent_id and millisecond timestamps; part.data carries text
  or tool state. Reads exclude reasoning and reverted suffixes. Populated newer
  session_message projections fail closed instead of guessing their semantics.
  Official CLI session/export docs: https://opencode.ai/docs/cli/.
- Antigravity Desktop and CLI: conversation `.db` stores contain trajectory_meta,
  trajectory_metadata_blob and steps. `step_format=0` stores protobuf Step.
  Field mapping was read from the installed language_server.exe descriptors:
  Step type=1, status=4, metadata=5, user_input=19, planner_response=20,
  run_command=28, command_status=37. UserInput items=3/text=1, query=1,
  user_response=2. PlannerResponse response=1, modified_response=8;
  thinking=3/raw_thinking=16 are explicitly ignored. RunCommand command_line=23,
  cwd=2, optional exit_code=6 and combined_output=21. TrajectoryMetadata uses
  created_at=2, workspace_uris=7, workspaces=1 and subagent_spec=8. These internal
  schemas may drift. Unknown formats/payloads produce warnings, not guessed text.

All new test databases and logs are synthetic; no private conversation body was
copied into fixtures or sent to a model for acceptance testing.

Investigated 2026-09-05. Installed CLI versions: Claude Code 2.1.251;
codex-cli 0.147.0. These are installed versions, not a claim about latest releases.
Live npm registry queries returned Claude Code 2.1.261 and Codex 0.153.4.
Those newer binaries were not installed or runtime-validated in this workspace.

## Evidence

- Claude official storage description: https://code.claude.com/docs/en/how-claude-code-works
- Claude MCP resources and mentions: https://code.claude.com/docs/en/mcp
- Claude Desktop shared configuration: https://code.claude.com/docs/en/desktop
- Codex MCP (redirects to current ChatGPT Learn): https://developers.openai.com/codex/mcp
- Codex current public protocol source: https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs
- Current source revision: `ddf04ad26789d040f9ef6a96736f76602e35a6cc`;
  https://github.com/openai/codex/blob/ddf04ad26789d040f9ef6a96736f76602e35a6cc/codex-rs/rollout/src/recorder.rs
  confirms JSONL persistence and first-SessionMeta canonical identity (forks can
  include later parent metadata). Adapter keeps the first session identity.
- MCP newline-delimited UTF-8 transport: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- Local CLI `--version` and `mcp add --help`; read-only schema-key probe of at
  most 250 records from one recent file per vendor. No private text copied.

## Claude

`~/.claude/projects/**/*.jsonl`. Local records include user, assistant, system,
ai-title, file-history-snapshot, file-history-delta and administrative records.
Envelope: sessionId, cwd, timestamp, version; message.content is text or blocks.
Blocks include tool_use and tool_result; correlate id/tool_use_id. Sidechain
records and subagent files must not be mixed into the main conversation.
Assistant end_turn is a turn ending, not proof of project completion. Errors and
unmatched calls override success assumptions. No reliable crash-vs-close inference.

## Codex

`$CODEX_HOME/sessions/**/*.jsonl` and `archived_sessions/**/*.jsonl` (default
`~/.codex`). Local records include session_meta, response_item, event_msg,
turn_context, world_state, token_usage_record. Metadata payload includes id,
session_id, cwd, cli_version, source. Responses include messages, function/custom
tool calls and corresponding outputs. Reasoning/encrypted content is ignored.
Unknown event types are counted/warned, not interpreted as work completed.

## Extension matrix

| Surface | Official entry | v0.1 approach | Verification limit |
|---|---|---|---|
| Claude CLI | stdio MCP, resource @ mentions, hooks | resources + tools | host UI demo pending |
| Claude Desktop local Code tab | shared MCP configuration | same server | UI demo pending |
| Claude Desktop chat | local MCP config | same server, Code sessions only | chat storage not parsed |
| Codex CLI | stdio MCP | tools/resources + terminal picker | bare @claude not established |
| Codex Desktop local tasks | MCP settings | same server | native picker not established |

Claude's documented syntax is `@server:protocol://resource/path`; resource names
can be searched in its picker. Bare @codex is a target UX, not a promised hook.
Hooks are unnecessary for the baseline and would add prompt interception risk.
Codex MCP tools provide the non-invasive fallback. Desktop cloud/remote tasks and
ordinary Claude chat databases are outside the local coding-session adapter.

Fixtures are authored synthetic examples of observed structures, not exports.
Storage schemas are internal and may drift; supported structural families are
documented instead of promising all releases with the same version number.

Opaque JavaScript orchestration inside Codex `functions.exec` is retained as a
tool call but not executed or semantically decomposed into shell commands.

## Codex sideband patch evidence — 2026-09-17

The exact owned test session generated with CLI 0.147.0 on 2026-09-16 emitted
`event_msg.payload.type=patch_apply_end` separately from an opaque `exec` call.
The observed payload contains `call_id`, `turn_id`, boolean `success`, a
`status` of `completed`, and a `changes` object whose add entries have
`type: add` and full string `content`. The inner event call ID need not equal
the outer JavaScript orchestration call ID. They must not be guessed equivalent.

Only this add-file shape is now supported. Failure/status validation and
duplicate/conflict handling are covered by synthetic tests, not claimed as
observed live failure variants. Exact content hashing preserves newline and
Unicode distinctions; a matching current file proves bytes, not feature
acceptance. Update/delete or unknown variants still warn until verified.
Raw real-session content was not copied into test fixtures.
Such work may be UNCERTAIN even if a human can infer more from the source.
