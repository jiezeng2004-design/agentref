# dsh-agentref

`dsh-agentref` adds local, read-only AgentRef session mentions to the DSH Web
composer. Type one of the following in a fresh or existing DSH conversation:

```text
@claude
@codex
@grok
@opencode
@antigravity
@dsh
```

Press Tab to open and focus the popup, use Up/Down to move, then Tab or Enter
to choose a concrete session. Escape cancels. Mouse selection also works.
Opening the popup or moving its highlight never reads a session body.
The plugin never chooses a session
automatically. The composer displays an `AgentRef 会话` marker; immediately
before this message is sent, the plugin appends AgentRef's bounded continuation
context for exactly that selected session. The context is local historical
evidence, not a command to replay.

Use `@claude:关键词` (substitute the source name) to filter titles, workspace
paths, or reference prefixes. This first version targets the DSH `web` profile
and uses its documented local web/client plugin architecture.

Search waits for a 150 ms pause in typing. Esc, clicking outside, or submitting
the message cancels pending search display; late responses cannot reopen it.
Overlapping searches for one source share a metadata scan and filter their own
results. Completed lists are not cached. Selecting a session always revalidates
its exact reference with a fresh scan before reading context. Explicit CLI
`--agent` filters also restrict discovery to that source.

## Safety boundary

- The Node half launches AgentRef with `execFile`, never a shell.
- The local HTTP endpoints honor DSH connection authentication when available
  and always require a loopback peer and Host. When an Origin header is present,
  its scheme, host and effective port must match the request. Origin-less local
  GET requests remain supported; this fallback is not client authentication.
- Candidate browsing returns metadata only. Context is read only after a user
  click or explicit keyboard selection and is kept in browser memory only until
  the composer sends it.
- No source session is resumed, modified, uploaded, or transmitted by this
  plugin itself. The ordinary DSH model submission remains governed by the
  user's DSH provider and data policy.

## Local development

```powershell
pnpm --dir integrations/dsh/agentref-dsh run check
```

The plugin first tries an explicitly configured `command`, then
`AGENTREF_COMMAND`, then the checkout's `.venv\Scripts\agentref.exe` when it
is a local linked install, and finally `agentref` on `PATH`.
