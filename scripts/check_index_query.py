"""Compare indexed listing with the former full-table path using synthetic rows.

Measures query/materialization only, not source refresh, disk discovery or UI.
No personal source is opened; the complete database is temporary.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentref.adapters.registry import ADAPTERS
from agentref.index import Index
from agentref.mentions import session_time
from agentref.titles import apply_cached_titles


def full_table_reference(index, agent):
    rows = index.db.execute("SELECT * FROM sessions ORDER BY mtime DESC").fetchall()
    result = [dict(row) for row in rows if row["agent"] in index.adapters
              and (agent is None or row["agent"] == agent)]
    for name, adapter in index.adapters.items():
        if agent is None or name == agent:
            adapter.overlay_metadata([row for row in result if row["agent"] == name])
    apply_cached_titles(index.home, result)
    return sorted(result, key=lambda row: (session_time(row), row["ref"]), reverse=True)


def check(rows=12000, repeats=5):
    with tempfile.TemporaryDirectory(prefix="agentref-query-") as td:
        index = Index(Path(td) / "index", [factory([]) for factory in ADAPTERS.values()])
        try:
            names = list(ADAPTERS)
            index.db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                (f"{names[n % len(names)]}:{n:016x}", names[n % len(names)], f"session-{n}",
                 f"Synthetic title {n}", "", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
                 f"synthetic::{n}", "unknown", n, 0, 0, "", 0) for n in range(rows)))
            index.db.commit()
            report = []
            adapters = dict(index.adapters)
            for scenario, enabled, agent in (
                ("source-filter", adapters, "claude"),
                ("single-source-server", {"claude": adapters["claude"]}, None),
                ("all-sources", adapters, None),
            ):
                index.adapters = enabled
                count = [0]

                def counted_row(cursor, values):
                    count[0] += 1
                    return sqlite3.Row(cursor, values)

                index.db.row_factory = counted_row
                timings = {"reference": [], "current": []}
                materialized = {}
                for iteration in range(repeats + 1):
                    results = {}
                    # Alternate execution order; discard the warmup sample.
                    order = ("reference", "current") if iteration % 2 else ("current", "reference")
                    for mode in order:
                        count[0] = 0
                        started = time.perf_counter()
                        results[mode] = full_table_reference(index, agent) if mode == "reference" else index.sessions(agent)
                        if iteration:
                            timings[mode].append((time.perf_counter() - started) * 1000)
                        materialized[mode] = count[0]
                    if results["reference"] != results["current"]:
                        raise AssertionError("Listing semantics changed: " + scenario)
                report.append({"scenario": scenario, "returned": len(results["current"]),
                               "materializedRows": materialized,
                               "medianMs": {key: round(statistics.median(value), 2) for key, value in timings.items()}})
            return {"synthetic": True, "sourceRefreshMeasured": False, "rows": rows, "repeats": repeats,
                    "resultsEquivalent": True, "scenarios": report}
        finally:
            index.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=12000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if not 6 <= args.rows <= 100000 or not 1 <= args.repeats <= 20:
        parser.error("rows must be 6..100000; repeats must be 1..20")
    print(json.dumps(check(args.rows, args.repeats)))
