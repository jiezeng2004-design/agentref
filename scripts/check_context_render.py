"""Compare bounded context JSON rendering with its prior full-list path."""
import argparse
import gc
import json
from pathlib import Path
import re
import statistics
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentref.context_render import bounded_json, clip_text
from agentref.handoff import recent_decisions


def reference_bounded_json(value, limit):
    raw = json.dumps(value, ensure_ascii=False, indent=2)
    if len(raw) <= limit:
        return raw
    items = value if isinstance(value, list) else [value]
    kept = []
    for item in reversed(items):
        trial = [item, *kept]
        candidate = {"TRUNCATED": True, "omittedOlderEntries": len(items) - len(trial), "items": trial}
        if len(json.dumps(candidate, ensure_ascii=False, indent=2)) > limit:
            if not kept:
                text = json.dumps(item, ensure_ascii=False, indent=2)
                size = max(64, limit // 2)
                while True:
                    candidate["items"] = [{"excerpt": clip_text(text, size)}]
                    rendered = json.dumps(candidate, ensure_ascii=False, indent=2)
                    if len(rendered) <= limit:
                        return rendered
                    size //= 2
            break
        kept = trial
    return json.dumps({"TRUNCATED": True, "omittedOlderEntries": len(items) - len(kept),
                       "items": kept}, ensure_ascii=False, indent=2)


def measure(function, value, limit):
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    rendered = function(value, limit)
    elapsed_ms = (time.perf_counter() - started) * 1000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return rendered, elapsed_ms, peak_bytes


def reference_recent_decisions(messages, limit=8):
    decisions = [{"claim": line[:800],
                  "evidence": "assistant statement; rationale and validity not independently verified"}
                 for message in messages if message["role"] == "assistant"
                 for line in message["text"].splitlines()
                 if re.search(r"(?i)(decided|chosen|we will use|because|决定|选择|采用|原因)", line)]
    return decisions[-limit:]


def measure_decisions(function, messages):
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    result = function(messages)
    elapsed_ms = (time.perf_counter() - started) * 1000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed_ms, peak_bytes


def check(rows=50000, limit=1200, repeats=5):
    if not 1 <= rows <= 100000 or not 256 <= limit <= 32000 or not 1 <= repeats <= 20:
        raise ValueError("bounded input required: rows 1..100000, limit 256..32000, repeats 1..20")
    value = [{"task": f"synthetic task {n}", "status": "UNCERTAIN", "evidence": ["fixture"]}
             for n in range(rows)]
    samples = {"reference": [], "current": []}
    outputs = {}
    for iteration in range(repeats + 1):
        order = ("reference", "current") if iteration % 2 == 0 else ("current", "reference")
        for name in order:
            function = reference_bounded_json if name == "reference" else bounded_json
            rendered, elapsed_ms, peak_bytes = measure(function, value, limit)
            outputs[name] = rendered
            if iteration:
                samples[name].append((elapsed_ms, peak_bytes))
    if json.loads(outputs["reference"]) != json.loads(outputs["current"]):
        raise AssertionError("Bounded JSON output changed")
    if len(outputs["current"]) > limit:
        raise AssertionError("Current JSON exceeded its budget")
    messages = [{"role": "assistant", "text": f"We decided synthetic option {n}"} for n in range(rows)]
    decision_samples = {"reference": [], "current": []}
    decision_outputs = {}
    for iteration in range(repeats + 1):
        order = ("reference", "current") if iteration % 2 == 0 else ("current", "reference")
        for name in order:
            function = reference_recent_decisions if name == "reference" else recent_decisions
            result, elapsed_ms, peak_bytes = measure_decisions(function, messages)
            decision_outputs[name] = result
            if iteration:
                decision_samples[name].append((elapsed_ms, peak_bytes))
    if decision_outputs["reference"] != decision_outputs["current"]:
        raise AssertionError("Recent-decision output changed")
    return {"synthetic": True, "rows": rows, "limit": limit, "repeats": repeats,
            "equivalent": True,
            "medianMs": {name: round(statistics.median(value[0] for value in values), 2)
                         for name, values in samples.items()},
            "peakMiB": {name: round(statistics.median(value[1] for value in values) / 1048576, 2)
                        for name, values in samples.items()},
            "recentDecisions": {"equivalent": True,
                                "medianMs": {name: round(statistics.median(value[0] for value in values), 2)
                                             for name, values in decision_samples.items()},
                                "peakMiB": {name: round(statistics.median(value[1] for value in values) / 1048576, 2)
                                            for name, values in decision_samples.items()}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=50000)
    parser.add_argument("--limit", type=int, default=1200)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.rows, args.limit, args.repeats)))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
