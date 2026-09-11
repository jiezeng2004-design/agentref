"""Bounded snapshot JSONL reader. Offset is bytes, never characters."""
import json

MAX_LINE = 8 * 1024 * 1024


def read_jsonl(path, offset=0):
    records, warnings = [], []
    with path.open("rb") as stream:
        stream.seek(0, 2)
        end = stream.tell()
        if offset > end:
            offset = 0
            warnings.append("source truncated; restart at zero")
        stream.seek(offset)
        while stream.tell() < end:
            start = stream.tell()
            line = stream.readline(min(MAX_LINE + 1, end - start))
            if len(line) > MAX_LINE:
                warnings.append(f"oversize record at byte {start}; skipped")
                while line and not line.endswith(b"\n") and stream.tell() < end:
                    line = stream.readline(min(MAX_LINE, end - stream.tell()))
                offset = stream.tell()
                continue
            if not line.strip():
                offset = stream.tell()
                continue
            try:
                record = json.loads(line.decode("utf-8-sig"))
                if not isinstance(record, dict):
                    warnings.append(f"non-object at byte {start}; skipped")
                else:
                    records.append(record)
            except (ValueError, UnicodeError):
                if stream.tell() == end and not line.endswith(b"\n"):
                    warnings.append(f"incomplete trailing JSONL at byte {start}; retry later")
                    break
                warnings.append(f"malformed JSONL at byte {start}; skipped")
            offset = stream.tell()
    return records, offset, warnings
