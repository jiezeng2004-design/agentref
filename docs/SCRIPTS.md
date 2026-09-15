# Script safety index

Run commands from the checkout unless their documentation says otherwise. These
categories describe the scripts, not authorization to execute them. Inspect the
target paths and scope before host checks or installation. Never treat a `check_`
prefix as proof that a script cannot access installed-host metadata.

## Synthetic / isolated checks

| Script | Inputs and effects |
| --- | --- |
| `scripts/demo.py` | Synthetic bidirectional context; temporary files only; no real host/model |
| `scripts/check_scale.py` | Generated stores for all six sources; temporary DB/files; optional `--output` report |
| `scripts/check_index_query.py` | Temporary synthetic index; compares query semantics and timings; no source refresh |
| `scripts/check_wheel.py` | Temporary source copy, wheelhouse and venv; build may download dependencies; CLI/MCP use fixtures |
| `scripts/continuation_trial.py` | `prepare` creates synthetic trial artifacts; `verify` executes bounded trial tests; handing off to a model is separate |
| `scripts/check_dsh_mentions_browser.cjs` | Headless browser, loopback HTTP fixture server and screenshots under `output/`; not a live DSH host |
| `scripts/check_dsh_native_format.mjs` | Imports a supplied installed DSH Session module and writes a synthetic compressed store to the supplied output root |
| `scripts/check_native_mentions.py` | Installed Codex app-server with an isolated synthetic home/source; writes local evidence; no model |

## Installed-host inspection / metadata

These may launch installed host processes, read their configuration or enumerate
private candidate metadata. Host processes can have their own startup side effects.
They are not part of the default synthetic test gate.

| Script | Boundary |
| --- | --- |
| `scripts/check_agent_menu.py` | Installed Codex app-server and agent-entry inventory; executable supplied as argument |
| `scripts/check_installed_plugin_mentions.py` | Installed plugin discovery/mention metadata through Codex app-server |
| `scripts/verify_extra_agents.py` | Runs installed plugin MCP commands; candidate metadata and local report |
| `scripts/check_receiving_hosts.py` | Checks installed bytes, host discovery and six-source metadata; writes sanitized report |
| `scripts/check_grok_postsend.py` | Default preview only prints the authorization requirement; `--allow-live-metadata` inspects Grok and calls the configured model with candidate metadata, requiring separate authorization |

## Configuration writers — explicit installation scope required

| Script | Default / write boundary |
| --- | --- |
| `scripts/configure_local.py` | Requires `--apply`; manages initial Codex/Claude integration |
| `scripts/configure_extra_agents.py` | Preview by default; `--apply` installs; `--rollback --apply` removes owned entries |
| `scripts/configure_receiving_hosts.py` | Preview by default; managed MCP/skill entries; supports explicit executable/workspace root and scoped rollback |
| `scripts/configure_opencode_tui.py` | Preview by default; one TUI plugin tuple; `--config-dir` selects target; scoped rollback |
| `scripts/configure_agent_menu.py` | Preview by default; `--apply` writes the personal agent-entry plugin |
| `scripts/enable_native_menus.py` | Preview by default; `--apply` changes owned Claude-host template-menu arguments |
| `scripts/configure_dsh.py` | **Writes/installs when run; no `--apply` preview gate. Do not use as a diagnostic command.** |

Rollback options are not interchangeable between scripts. Preserve unrelated
entries; do not restore an entire historical configuration. The two installers
using shared atomic writes are described in [development checks](DEVELOPMENT_CHECKS.md).

## Real-model harness

`scripts/live_demo.py` launches a real Claude/Codex child in a dedicated demo
workspace, requests implementation, and interrupts its owned child. It may incur
provider charges and writes ignored host logs/session history. Use only with
explicit real-host/model authorization. It is not a unit test or offline demo.

## Internal helpers

- `scripts/setup_common.py`: executable location and guarded file writes; imported
  by installers, not a standalone install command.
- `scripts/plugin_branding.py`: copies bundled brand resources and updates manifest
  fields when called by setup scripts; not a standalone validation command.

The script inventory is checked by `tests/test_docs.py`. New entrypoints must be
classified here so their data access and write behavior remain visible.
