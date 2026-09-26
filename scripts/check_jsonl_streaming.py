"""Compare bounded JSONL list parsing with streaming consumption on synthetic data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentref.parser import MAX_LINE, read_jsonl, scan_jsonl

MAX_FILE_BYTES = 256 * 1024 * 1024


def digest(records):
    result = hashlib.sha256()
    for record in records:
        result.update(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        result.update(b"\n")
    return result.hexdigest()


def measure_list(path):
    tracemalloc.start()
    records, end, warnings = read_jsonl(path)
    checksum = digest(records)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"records": len(records), "end": end, "warnings": warnings,
            "sha256": checksum, "peakBytes": peak}


def measure_stream(path):
    count = 0
    checksum = hashlib.sha256()

    def consume(record):
        nonlocal count
        checksum.update(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        checksum.update(b"\n")
        count += 1

    tracemalloc.start()
    end, warnings = scan_jsonl(path, consume=consume)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"records": count, "end": end, "warnings": warnings,
            "sha256": checksum.hexdigest(), "peakBytes": peak}


def check(records=2500, width=16384):
    estimated = records * width
    if not 1 <= records <= 50000 or not 1 <= width <= MAX_LINE - 256 or estimated > MAX_FILE_BYTES:
        raise ValueError("bounded input required: records 1..50000, width <= MAX_LINE-256, total <= 256 MiB")
    with tempfile.TemporaryDirectory(prefix="agentref-jsonl-stream-") as temp:
        path = Path(temp) / "synthetic.jsonl"
        text = "x" * width
        record = {"type": "user", "sessionId": "synthetic", "message": {"content": text}}
        encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for _ in range(records):
                stream.write(encoded)
        listed = measure_list(path)
        streamed = measure_stream(path)
        if {k: listed[k] for k in ("records", "end", "warnings", "sha256")} != {
                k: streamed[k] for k in ("records", "end", "warnings", "sha256")}:
            raise AssertionError("Streaming JSONL semantics changed")
        return {"synthetic": True, "source": "temporary", "fileBytes": path.stat().st_size,
                "equivalent": True,
                "list": {"records": listed["records"], "peakMiB": round(listed["peakBytes"] / 1048576, 2)},
                "stream": {"records": streamed["records"], "peakMiB": round(streamed["peakBytes"] / 1048576, 2)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=2500)
    parser.add_argument("--width", type=int, default=16384)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.records, args.width)))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
