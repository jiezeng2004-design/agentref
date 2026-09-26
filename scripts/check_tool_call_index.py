"""Compare indexed tool-result correlation with the prior reverse scan."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentref.adapters.base import BaseAdapter
from agentref.core import SessionIR


def check(calls=5000, repeats=5):
    if not 1 <= calls <= 50000 or not 1 <= repeats <= 20:
        raise ValueError("bounded inputs required: calls 1..50000 and repeats 1..20")
    source = [{"id": str(n), "name": "synthetic-tool", "arguments": {}, "cwd": "",
               "output": None, "status": "UNCERTAIN"} for n in range(calls)]
    timings = {"reference": [], "indexed": []}
    for iteration in range(repeats + 1):
        order = ("reference", "indexed") if iteration % 2 == 0 else ("indexed", "reference")
        results = {}
        for mode in order:
            session = SessionIR("synthetic", toolCalls=[dict(call) for call in source])
            started = time.perf_counter()
            if mode == "reference":
                for call_id in map(str, range(calls)):
                    for call in reversed(session.toolCalls):
                        if call["id"] == call_id:
                            call["output"] = "synthetic result"
                            call["status"] = "UNCERTAIN"
                            break
            else:
                adapter = BaseAdapter([])
                for call_id in map(str, range(calls)):
                    adapter.result(session, call_id, "synthetic result")
            elapsed = (time.perf_counter() - started) * 1000
            if iteration:
                timings[mode].append(elapsed)
            results[mode] = session.toolCalls
        if results["reference"] != results["indexed"]:
            raise AssertionError("Tool-result correlation semantics changed")
    return {"synthetic": True, "parallelCalls": calls, "resultsEquivalent": True,
            "medianMs": {name: round(statistics.median(values), 2) for name, values in timings.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=int, default=5000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.calls, args.repeats)))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
