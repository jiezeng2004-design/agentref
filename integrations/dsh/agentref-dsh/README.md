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
Overlapping searches for the same source and query share an in-flight metadata
request. Completed lists are not cached. The query and 50-row limit are passed
to the CLI before JSON serialization; selecting a session revalidates its exact
reference with a one-row query before reading context. Explicit CLI `--agent`
filters also restrict discovery to that source.

Metadata subprocess output is bounded separately at 8 MiB; selected context
remains limited to 256 KiB. The index still refreshes the selected source before
searching, but the host process receives only matching rows, up to 50, instead
of the complete inventory. `agentref sessions` also accepts `--query`,
`--limit` (1–500), and `--offset` (0–1000000); calls without these options keep
the original full-list behavior. When an installed CLI does not recognize the
new flags, the plugin retries the legacy full-list command; that fallback can
still exceed the 8 MiB transport limit.

Successful CLI calls with stderr diagnostics return `incomplete: true` alongside
`sessions`. The menu warns that candidates may be missing or stale, including
when the visible list is empty. This is a conservative signal, not a parsed
warning count or classification; raw stderr is not forwarded on this success
path. An older server without the flag remains compatible but cannot supply
this warning. Exact selection still revalidates the source; browsing warnings
never select a session automatically.

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
