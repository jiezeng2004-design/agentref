# Local acceptance — 2026-09-13

## Implemented and installed

- OpenCode **1.18.16 full TUI**: public prompt slots, Tab keymap and native
  session dialog. Both the home prompt and an existing synthetic session were
  exercised in the installed executable through Windows ConPTY.
- Six source names open their own metadata list. Up/Down moves; Enter or a
  second Tab selects. Escape cancels without reading context. Shell-mode Tab
  falls through to the host. Chinese prefixes and attachment ranges use
  terminal display cells, including newlines, rather than JavaScript length.
- The local user `tui.json` now points to this checkout's plugin and AgentRef
  executable. Re-running the installer reports no change. Rollback was tested
  against fixtures and previewed against the installed entry.
- DSH Web's linked local plugin was rebuilt with keyboard navigation. Its
  current `web` profile points at `integrations/dsh/agentref-dsh` via a junction.

## Evidence and limits

- OpenCode TUI interactions used an isolated config/database and synthetic
  source rows. Only explicit selections triggered fixture `context` calls.
  No provider was enabled and no prompt was submitted to a model.
- Separately, the installed OpenCode command configuration was used to list
  real local metadata from all six adapters. Counts were Claude 35, Codex 1358,
  Grok 59, OpenCode 37, Antigravity 35 and DSH 134. Claude and Codex report
  incomplete-index warnings; these pre-existing warnings remain unresolved.
  Real session bodies were not read by this acceptance test.
- OpenCode interaction tests: **7 passed**. Installer preservation, idempotency,
  rollback and conflict tests: **2 passed**.
- DSH syntax/build/server/client tests: **16 passed**. A real Chromium page
  loaded the built DSH client against a synthetic loopback HTTP fixture: six
  sources, zero context reads while browsing/cancelling, one exact context read
  on selection, and one synthetic submission on the subsequent Enter.
  The menu remained inside the viewport and there were no page errors.
- DSH's complete application and live model flow were **not** exercised. The
  browser fixture verifies the compiled DOM integration, not every downstream
  DSH skin/composer version. Restart DSH Web and refresh its page to load it.
- The Codex and Claude integrations were not changed or re-verified here.
  Grok and Antigravity still use the post-send numbered fallback; no supported
  pre-send composer menu extension was found in the inspected interfaces.

Local evidence (ignored by Git): `output/native-mentions/opencode-tui-result.json`,
`opencode-fixture/calls.jsonl`, `installed-client-result.json`,
`dsh-browser-result.json` and `dsh-keyboard-menu.png`.

No commit, push, release, host binary patch, provider change or personal-session
write was performed. Existing dirty files outside this change's allowlist kept
their recorded baseline hashes.

## Use and rollback

Restart OpenCode, type `@grok` (or another source name), then Tab. A query such
as `@codex:keyword` narrows the source list before the 50-row display limit.
See [README](README.md) for installation and scoped rollback commands.

For DSH Web, restart/reload the existing linked plugin. The browser fixture can
be repeated with `node scripts/check_dsh_mentions_browser.cjs` when Playwright
is installed or available through `NODE_PATH`.
