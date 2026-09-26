# Local development checks

Run from the checkout with Python 3.11+ and Node available:

Use an isolated environment with the project's declared dependencies installed.
Python 3.11–3.13 need `zstandard`; Python 3.14 uses its standard-library codec.
Running the suite with a bare older interpreter can fail the compressed DSH
fixtures even when the source is correct. CI uses Node 22; a local run on another
supported Node version is not evidence that the Node 22 job passed.

```text
python -X utf8 -m unittest discover -s tests -q
node --test integrations/dsh/agentref-dsh/test/*.test.mjs integrations/opencode/agentref-tui/test/*.test.mjs integrations/antigravity/agentref-runtime/test/*.test.mjs
node --check integrations/antigravity/agentref-runtime/cdp.mjs
node --check integrations/antigravity/agentref-runtime/broker.mjs
node --check integrations/antigravity/agentref-runtime/runtime.mjs
node --check integrations/antigravity/agentref-runtime/client.js
python -X utf8 scripts/check_scale.py --sessions 3 --turns 3 --width 64
python -X utf8 scripts/check_index_query.py --rows 12000 --repeats 5
python -X utf8 scripts/check_jsonl_streaming.py --records 2500 --width 16384
python -X utf8 scripts/check_dsh_event_streaming.py --events 50000
python -X utf8 scripts/check_context_render.py --rows 50000 --limit 1200 --repeats 5
python -X utf8 scripts/check_evidence_history.py --records 50000 --unique-tasks 1000 --repeats 5
python -X utf8 scripts/check_tool_call_index.py --calls 5000 --repeats 5
python -X utf8 scripts/check_wheel.py
```

The Python suite includes source-catalog consistency checks. When adding a
source, update `agentref/sources.py`, its adapter registration and the source
lists/mention patterns in the self-contained JavaScript integrations. The tests
reject drift. Codex-host menu visibility is an explicit policy separate from
whether a source can be read; the Codex source does not appear in that menu.

The wheel check copies only packaging inputs to a temporary directory, builds
the wheel and dependency wheels, then installs them offline into a fresh venv.
The build phase may access the configured package index. It verifies import
provenance, all bundled asset hashes, the installed CLI, doctor, and an MCP
initialize/list/selected-resource-read flow using one generated Codex fixture.
It removes its temporary environment on exit and does not change host settings
or read personal sessions. It is a package smoke test, not six-source end-to-end
acceptance. CI runs it across its existing OS/Python matrix.

These commands do not establish native host UI behavior, live-model continuation,
remote CI success or release publication. Historical acceptance records remain
in `VERIFICATION.md` and `RELEASE_READINESS.md`.

## Adapter contracts and host setup

`tests/test_live_demo.py` validates the live harness using synthetic local Python
children (including owned-process termination, timeout and interruption cleanup),
never Codex/Claude or a model. `tests/test_dsh_config.py` verifies preview-only
installation behavior without invoking host/helper programs or reading settings.
Neither proves real host permissions, successful plugin installation or model
continuation. DSH's explicit apply path still lacks transactional rollback.

The Antigravity runtime broker tests run in Node CI. `test/browser.cjs` is an
additional synthetic Chromium/CDP check using an isolated temporary profile;
it does not connect to Antigravity or a model. The runtime uses Node.js 22 or
later for its built-in WebSocket client. Real Antigravity UI acceptance remains
a separate host check.

`tests/test_adapter_contracts.py` checks explicit incremental/snapshot modes,
indexed-read routing, metadata-only title policy and source-boundary rejection.
New adapters must declare their mode and implement the corresponding protocol
in `agentref/core.py`; the index no longer probes for optional scan/read methods.

`scripts/setup_common.py` shares executable-path selection and guarded atomic
file replacement between the receiving-host and OpenCode TUI installers. Host
formats, ownership checks and rollback decisions remain in each installer.
`tests/test_setup_common.py` uses temporary fixture configurations only, including
a real TUI installer subprocess running outside the checkout. No actual host
installation or reload is part of these tests.

Receiving-host setup accepts optional `--command` and `--workspace-root` paths;
omitting them preserves the local-venv and repository-ancestor defaults. Use the
same explicit options on rollback so ownership checks match installed entries.
This does not make the PowerShell receiving-host skill cross-platform.

The shared writer refuses linked paths, checks the current bytes before staging
and again before replacement, cleans its staging file after failures, and checks
the result. It is not an OS-level compare-and-swap or a multi-file transaction:
close the affected host before applying changes. Earlier successfully written
files can remain if a later file fails; do not restore whole old configurations.

## Index-query benchmark

`scripts/check_index_query.py` creates a temporary index with evenly distributed
synthetic records for six sources. It compares the current listing against the
former full-table implementation, alternates execution order, discards warmup,
checks complete row/order equality and reports medians and Python row-object counts.
There is no wall-clock pass/fail threshold. The unit suite uses 60 rows; the command
above uses 12,000. It compares 50-row all-source and keyword pages, an exact keyword
total, and an empty keyword result against the full Python reference path. Neither
reads real sessions or measures refresh/UI latency; SQLite's internal sort memory
is not measured.

Source filtering uses parameterized SQL. Schema version 3 replaces the old
agent-only `sessions_agent` index with an expression index on agent, session order
and ref; version 4 adds `sessions_sessionid`. Bounded pages use indexed ordering
and LIMIT/OFFSET, while unbounded listings retain the Python final sort. Earlier
schema steps invalidate selected cached metadata for reparsing; source sessions
are not modified. Large repeated sparse searches may build a connection-local
FTS5 candidate table with exact-match fallback.

Do not assume an older AgentRef executable can reuse the upgraded cache: the
expression index depends on a registered SQL function. Downgrade compatibility
has not been validated. Use a separate `--data-dir` for an older executable and
preserve the current cache and source sessions.

Local Windows observation on 2026-09-14 (12,000 records, five measured repetitions):

| Scenario | Full-table median | Current median | Materialized rows, old -> current |
| --- | --- | --- | --- |
| Source-filtered list | 141.60 ms | 58.73 ms | 12,000 -> 2,000 |
| Single-source server | 224.97 ms | 81.36 ms | 12,000 -> 2,000 |
| All enabled sources | 661.96 ms | 443.35 ms | 12,000 -> 12,000 |

These are machine/load-dependent synthetic observations, not performance promises.
The all-source path also avoids the former redundant SQL sort. Separate pre-change
all-source scale checks (300 sessions/source, 60 long messages, width 512) preserved
context and source hashes but observed DSH menu times around 3.1–3.7 seconds.
That path includes snapshot refresh; query filtering does not eliminate its work.
Snapshot caching remains a separate optimization: it needs measured invalidation
rules for summary/log changes, database WAL commits, deletion and partial failures
before it can safely replace fresh metadata scans.
