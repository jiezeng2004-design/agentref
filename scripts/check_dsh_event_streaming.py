"""Measure DSH event-list memory against streaming selected-session reads."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentref.adapters.dsh import DshAdapter
from agentref.parser import read_jsonl


def measure(events=50000):
    if not 1 <= events <= 500000:
        raise ValueError("events must be between 1 and 500000")
    with tempfile.TemporaryDirectory(prefix="agentref-dsh-events-") as temp:
        root = Path(temp)
        folder = root / "sessions/project/session-synthetic"
        folder.mkdir(parents=True)
        path = folder / "session.jsonl"
        header = dict(type="session", version=0, id="session-synthetic", createdAt=1700000000000,
                      cwd=str(root), delegationDepth=0)
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            header_line = json.dumps(header, separators=(",", ":")) + "\n"
            stream.write(header_line)
            header_end = len(header_line.encode("utf-8"))
            for seq in range(events):
                stream.write(json.dumps({"seq": seq, "type": "step/start", "data": {"step": seq}},
                                        separators=(",", ":")) + "\n")
            stream.write(json.dumps({"seq": events, "type": "turn/end", "data": {"reason": {"kind": "completed"}}},
                                    separators=(",", ":")) + "\n")

        tracemalloc.start()
        started = time.perf_counter()
        session = DshAdapter([root]).readSession(path)
        stream_ms = (time.perf_counter() - started) * 1000
        _, stream_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        tracemalloc.start()
        started = time.perf_counter()
        records, end, warnings = read_jsonl(path, header_end)
        list_ms = (time.perf_counter() - started) * 1000
        _, list_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        expected_events = events + 1
        if (len(records) != expected_events or end != path.stat().st_size or warnings
                or session.latestAgentState != "turn_ended" or session.parseWarnings):
            raise AssertionError("DSH streaming result or list reference did not validate")
        return {"synthetic": True, "events": expected_events, "fileBytes": path.stat().st_size,
                "equivalentState": True, "listParseMs": round(list_ms, 2),
                "streamReadMs": round(stream_ms, 2),
                "listPeakMiB": round(list_peak / 1048576, 2),
                "streamPeakMiB": round(stream_peak / 1048576, 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=50000)
    args = parser.parse_args()
    try:
        print(json.dumps(measure(args.events)))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
