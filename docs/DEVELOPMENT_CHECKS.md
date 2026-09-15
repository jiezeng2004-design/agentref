# Local development checks

Run from the checkout with Python 3.11+ and Node available:

```text
python -X utf8 -m unittest discover -s tests -q
node --test integrations/dsh/agentref-dsh/test/*.test.mjs integrations/opencode/agentref-tui/test/*.test.mjs
python -X utf8 scripts/check_scale.py --sessions 3 --turns 3 --width 64
python -X utf8 scripts/check_index_query.py --rows 12000 --repeats 5
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
checks complete row/order equality and reports medians and materialized row counts.
There is no wall-clock pass/fail threshold. The unit suite uses 60 rows; the command
above uses 12,000. Neither reads real sessions or measures refresh/UI latency.

Source filtering now runs in parameterized SQL using an additive `sessions_agent`
index; chronological ordering remains the final Python sort by session time/ref.
Opening an existing AgentRef index creates the SQL index if missing; no source or
session records are migrated. Older code can ignore the additional SQL index.

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
