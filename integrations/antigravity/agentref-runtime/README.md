# AgentRef AGY runtime menu

This is an opt-in, reversible adapter for Antigravity 2.14.0. It attaches to
an already-running AGY renderer through an existing loopback DevTools endpoint;
it does not start a debugger port, patch `app.asar`, install a plugin, or
change AGY settings.

Requires Node.js 22 or later for its built-in WebSocket client.

It recognizes `@claude`, `@codex`, `@grok`, `@opencode`, `@antigravity`, and
`@dsh` at the end of the Lexical composer. `Tab` opens a metadata-only list of
up to 50 recent matches; if more exist, add a more specific `@agent:keyword`
before pressing Tab again. The query is applied by the local index. Arrow keys
or mouse browse; `Enter`/`Tab` reads only the explicitly selected
exact reference and inserts a visible read-only text attachment. `Esc`, draft
edits, stale tickets, disconnects, and expired selections cancel safely. It
never submits the prompt.

## Use

The current AGY process must be launched with a DevTools endpoint that writes
`%APPDATA%\antigravity\DevToolsActivePort`. If AGY is already open without one,
close it using AGY's normal UI, start it through the user's existing AGY
launcher with its documented remote-debugging option, and reopen the target
conversation. This adapter never adds that option itself.

```powershell
node runtime.mjs --status
node runtime.mjs --apply
node runtime.mjs --stop
```

`--apply` stays attached until Ctrl+C, AGY disconnects, or `--stop` is used in
another process. `--fixture` is for the isolated browser test only and never
reads private sessions. Use the two `.cmd` wrappers as convenience launchers.

## Checks

```powershell
node --check cdp.mjs
node --check broker.mjs
node --check runtime.mjs
node --check client.js
node --test test/*.test.mjs
$env:NODE_PATH = 'C:\Users\<user>\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
node test/browser.cjs
```

The browser test uses synthetic data and a real CDP WebSocket. It is not a
claim that a live AGY model or private session was used. Live acceptance is
complete only when the UI visibly shows the AgentRef list, selection inserts
the attachment, and the prompt remains unsent.

## Rollback

Stop the runtime process. If it disconnects, no code remains injected in the
renderer. No AGY installation or configuration file is modified.
