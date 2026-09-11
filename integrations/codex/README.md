# Codex CLI and Desktop

The local `claude` plugin template in this directory supplies the native @claude
entry and a native session submenu. `search_mentions` advertises the installed
desktop client's `openai/extensions` / `mentions/search` capability, returning
structured resource candidates newest first. Select the plugin's submenu, choose
a session, then send the task. The app-server inventory/call/read chain is tested;
Desktop click/chip rendering remains unverified. See [local setup](../../LOCAL_SETUP.md).
The skill's `pick_session` is a conversation fallback for clients without this
extension. Native MCP elicitation forms remain opt-in, not the default menu.

After local venv installation, register explicitly:

```sh
codex mcp add claude -- /absolute/agentref/.venv/bin/agentref mcp --workspace /absolute/project
```

Windows executable: `C:\path\agentref\.venv\Scripts\agentref.exe`.
Alternatively merge the example into project `.codex/config.toml` for a trusted
project or use Desktop Settings -> MCP servers -> Add server -> STDIO -> Restart.
CLI and local Desktop share MCP configuration on the same host.

Ask: "Use AgentRef sessions to list Claude sessions; let me choose a title,
then use context to reconcile and continue." The context tool accepts an exact
indexed reference after selection. Users do not need to copy UUIDs.

Fallback terminal picker: `agentref pick claude --workspace /absolute/project`.
Standalone MCP registration alone does not add the plugin @claude entry.
No fork, hooks, app-server resume, process locks or UI injection are used.

Rollback: remove only the server entry you added, then restart the host.
