# AgentRef OpenCode TUI

Native pre-send session selection for the OpenCode 1.18.16 TUI extension API.
The plugin uses public prompt slots, prompt references, keymaps, and the host's
`DialogSelect`. It does not patch the OpenCode executable.

Type `@claude`, `@codex`, `@grok`, `@opencode`, `@antigravity` or `@dsh` at the
end of the draft and press **Tab**. Use the dialog's search box or Up/Down, then
**Enter** or **Tab** to select. **Esc** cancels. `@codex:keyword` filters by title,
workspace or reference before opening the list (up to 50 results).

Opening, searching and highlighting browse local metadata only. Selecting a
specific item reads its exact reference and inserts a tracked text attachment
in the draft. The selected historical context is expanded by OpenCode when the
user sends the draft. Cancelling or editing the draft rejects stale results.
The plugin never submits a prompt or resumes a foreign session itself.

Install from the AgentRef repository:

```powershell
python -X utf8 scripts/configure_opencode_tui.py --apply
```

Restart OpenCode after installation. The script manages one plugin entry in
`~/.config/opencode/tui.json` (or strict-JSON `tui.jsonc`), preserving other
settings. To remove only this entry:

```powershell
python -X utf8 scripts/configure_opencode_tui.py --rollback --apply
```

The `command` option is an executable path, and optional `args` are passed as an
argument array through `execFile`. No shell is used. A linked checkout can use
its `.venv` automatically, then fall back to `AGENTREF_COMMAND` or `agentref`.
No network or model is needed to select a session. Index warnings are shown in
the dialog title; an incomplete index does not imply there are no more sessions.

Validation:

```powershell
node --test integrations/opencode/agentref-tui/test/*.test.mjs
```

This integration targets the full OpenCode **TUI**, not `--mini` or its Web UI.
Host versions without these TUI APIs need the post-send session-reference skill.
