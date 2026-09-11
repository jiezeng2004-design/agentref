# Claude Code CLI and Desktop

This machine's user scope and Store Desktop configuration are already configured.
Actual Claude CLI @codex dynamic completion and selection were observed. See
[local setup](../../LOCAL_SETUP.md) for current login/provider limitations.

Install AgentRef in a dedicated venv first. Replace absolute paths in these
examples. Registration is a user action; AgentRef never edits host settings.

CLI, project-scoped:

```sh
claude mcp add --scope project codex -- /absolute/agentref/.venv/bin/agentref mcp --agent codex --template-menu --workspace /absolute/project
```

Windows executable: `C:\path\agentref\.venv\Scripts\agentref.exe`.
Or merge the example server entry into the project's `.mcp.json`.

Type `@codex`, select the diamond `codex:agentref://session/` template, then Tab.
The input menu now shows date/title abbreviations newest first. Arrow keys and
Tab select and insert a concrete reference. Typing `@codex:agentref://session/`
directly opens the same completion. This occurs before sending a prompt.
The first-level search also contains ordinary matching files. Claude currently
shows up to 15 completions; type a title keyword to narrow the list. Short tokens
resolve uniquely to an exact indexed ref, so later title/rank changes cannot
redirect an inserted reference. The older exact resource URI still works.
The `--template-menu` flag avoids Claude's ordinary fuzzy re-ranking of static
resources, which does not preserve chronological order. If completion is
not supported by the host, ask Claude to call AgentRef `sessions` with agent `codex`, present
titles/workspaces/times/states, wait for a selection, then call `context`.
The CLI fallback is `agentref pick codex --workspace /absolute/project`.

Desktop local Code tab shares `.mcp.json` / user MCP settings per official docs.
For Desktop chat, merge the same mcpServers entry into its MCP configuration.
This integration reads Claude Code local JSONL, not Desktop chat history.
Resource attachment rendering in either Desktop surface still needs a live check.
Project workspace is fixed at MCP startup, preventing transcript-driven path reads.

No UserPromptSubmit hook is installed: it cannot create a native autocomplete
menu and would intercept all prompts unnecessarily. No session is resumed.

Rollback: remove only the server entry you added, then restart that host.
