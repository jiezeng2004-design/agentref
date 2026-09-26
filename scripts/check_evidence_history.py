"""Compare top-k continuation ranking with the prior full-sort semantics."""
import argparse
import gc
import json
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentref.evidence import continuation_candidates

PRIORITY = {"NOT_STARTED": 0, "PARTIAL": 1, "FAILED": 2, "UNCERTAIN": 3}


def full_sort_reference(work, limit=12):
    candidates = [item for item in work if item["status"] != "COMPLETED"
                  and "supersededBy" not in item and item.get("planStatus") != "completed"]
    ordered = sorted(enumerate(candidates), key=lambda pair: (PRIORITY[pair[1]["status"]], -pair[0]))
    tasks = list(dict.fromkeys(item["task"] for _, item in ordered))
    return {"candidates": tasks[:limit], "omittedCandidates": max(0, len(tasks) - limit)}


def measure(function, work, limit):
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    result = function(work, limit)
    elapsed_ms = (time.perf_counter() - started) * 1000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed_ms, peak_bytes


def check(records=50000, unique_tasks=1000, repeats=5, limit=12):
    if not 1 <= records <= 500000 or not 1 <= unique_tasks <= records:
        raise ValueError("records must be 1..500000 and unique_tasks 1..records")
    if not 1 <= repeats <= 20 or not 0 <= limit <= 1000:
        raise ValueError("repeats must be 1..20 and limit 0..1000")
    statuses = ("NOT_STARTED", "PARTIAL", "FAILED", "UNCERTAIN")
    work = []
    for n in range(records):
        item = {"task": f"synthetic-task-{n % unique_tasks}", "status": statuses[n % len(statuses)],
                "evidence": ["synthetic"]}
        if n % 13 == 0:
            item["supersededBy"] = n + 1
        if n % 17 == 0:
            item["planStatus"] = "completed"
        work.append(item)

    results = {"reference": [], "current": []}
    outputs = {}
    for iteration in range(repeats + 1):
        order = ("reference", "current") if iteration % 2 == 0 else ("current", "reference")
        for name in order:
            function = full_sort_reference if name == "reference" else continuation_candidates
            result, elapsed_ms, peak_bytes = measure(function, work, limit)
            outputs[name] = result
            if iteration:
                results[name].append((elapsed_ms, peak_bytes))

    for key in ("candidates", "omittedCandidates"):
        if outputs["reference"][key] != outputs["current"][key]:
            raise AssertionError("Continuation candidate ordering changed")
    return {"synthetic": True, "records": records, "uniqueTasks": unique_tasks,
            "limit": limit, "repeats": repeats, "equivalent": True,
            "medianMs": {name: round(statistics.median(value[0] for value in samples), 2)
                         for name, samples in results.items()},
            "peakMiB": {name: round(statistics.median(value[1] for value in samples) / 1048576, 2)
                        for name, samples in results.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=50000)
    parser.add_argument("--unique-tasks", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.records, args.unique_tasks, args.repeats, args.limit)))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
