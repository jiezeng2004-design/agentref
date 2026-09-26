"""Bounded snapshot JSONL reader. Offset is bytes, never characters."""
import json

MAX_LINE = 8 * 1024 * 1024


def scan_jsonl(path, offset=0, consume=None, on_warning=None, collect_warnings=True):
    """Parse a JSONL suffix without retaining records after they are consumed."""
    if consume is None:
        raise TypeError("scan_jsonl requires a record consumer")
    warnings = []

    def warn(message):
        if on_warning is not None:
            on_warning(message)
        if collect_warnings:
            warnings.append(message)

    with path.open("rb") as stream:
        stream.seek(0, 2)
        end = stream.tell()
        if offset > end:
            offset = 0
            warn("source truncated; restart at zero")
        stream.seek(offset)
        remaining = end - offset
        cursor = offset
        while remaining > 0:
            start = cursor
            line = stream.readline(min(MAX_LINE + 1, remaining))
            consumed = len(line)
            if not line:
                # A concurrent truncation can leave the original end offset
                # beyond EOF. Stop at the last completed record boundary.
                break
            remaining -= consumed
            cursor += consumed
            if len(line) > MAX_LINE:
                warn(f"oversize record at byte {start}; skipped")
                while line and not line.endswith(b"\n") and remaining > 0:
                    line = stream.readline(min(MAX_LINE, remaining))
                    consumed = len(line)
                    if not line:
                        break
                    remaining -= consumed
                    cursor += consumed
                offset = cursor
                continue
            if not line.strip():
                offset = cursor
                continue
            try:
                record = json.loads(line.decode("utf-8-sig"))
            except (ValueError, UnicodeError):
                if remaining == 0 and not line.endswith(b"\n"):
                    warn(f"incomplete trailing JSONL at byte {start}; retry later")
                    break
                warn(f"malformed JSONL at byte {start}; skipped")
            else:
                if not isinstance(record, dict):
                    warn(f"non-object at byte {start}; skipped")
                else:
                    consume(record)
            offset = cursor
    return offset, warnings


def read_jsonl(path, offset=0):
    records = []
    end, warnings = scan_jsonl(path, offset, records.append)
    return records, end, warnings
