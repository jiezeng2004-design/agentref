"""Bounded, valid evidence rendering with recency and visible omissions."""
import json
from collections import deque

CONTEXT_LIMIT = 32000  # Characters, not tokenizer-specific tokens.


def clip_text(text, limit):
    if len(text) <= limit:
        return text
    marker = f"\n[TRUNCATED from {len(text)} characters; middle omitted]\n"
    room = max(0, limit - len(marker))
    head = room // 2
    tail = room - head
    return text[:head] + marker + (text[-tail:] if tail else "")


def _nested_json_size(value, budget):
    size, lines = 0, 1
    encoder = json.JSONEncoder(ensure_ascii=False, indent=2)
    for chunk in encoder.iterencode(value):
        size += len(chunk)
        lines += chunk.count("\n")
        nested = size + 4 * lines
        if nested > budget:
            return None
    return size + 4 * lines


def _encoded_excerpt(value, retain):
    prefix, prefix_size = [], 0
    tail_parts, tail_size = deque(), 0
    total = 0
    encoder = json.JSONEncoder(ensure_ascii=False, indent=2)
    for chunk in encoder.iterencode(value):
        total += len(chunk)
        if prefix_size < retain:
            head = chunk[:retain - prefix_size]
            prefix.append(head)
            prefix_size += len(head)
        if retain:
            tail_parts.append(chunk[-retain:])
            tail_size += len(tail_parts[-1])
            while tail_size > retain:
                excess = tail_size - retain
                first = tail_parts[0]
                if len(first) <= excess:
                    tail_parts.popleft()
                    tail_size -= len(first)
                else:
                    tail_parts[0] = first[excess:]
                    tail_size -= excess
    return total, "".join(prefix), "".join(tail_parts)


def _clip_encoded_excerpt(prefix, tail, total, limit):
    if total <= limit:
        return prefix[:total]
    marker = f"\n[TRUNCATED from {total} characters; middle omitted]\n"
    room = max(0, limit - len(marker))
    head = room // 2
    tail_size = room - head
    return prefix[:head] + marker + (tail[-tail_size:] if tail_size else "")


def bounded_json(value, limit):
    """Prioritize newest list entries; never cut serialized JSON mid-record."""
    if limit < 256:
        raise ValueError("JSON evidence budget must be at least 256 characters")
    encoder = json.JSONEncoder(ensure_ascii=False, indent=2)
    chunks, size = [], 0
    for chunk in encoder.iterencode(value):
        size += len(chunk)
        if size > limit:
            chunks.clear()
            del chunk
            break
        chunks.append(chunk)
    else:
        return "".join(chunks)

    items = value if isinstance(value, list) else [value]
    kept = []
    nested_total = 0
    prefix = '{\n  "TRUNCATED": true,\n  "omittedOlderEntries": '
    suffix = "\n  ]\n}"
    for item in reversed(items):
        nested_size = _nested_json_size(item, limit)
        if nested_size is None:
            if kept:
                break
            # A single large newest entry still gets a readable excerpt, without
            # holding its complete serialized JSON as an intermediate string.
            retain = max(64, limit // 2)
            total, prefix, tail = _encoded_excerpt(item, retain)
            candidate = {"TRUNCATED": True, "omittedOlderEntries": len(items) - 1, "items": []}
            size = retain
            while size > 0:
                candidate["items"] = [{"excerpt": _clip_encoded_excerpt(prefix, tail, total, size)}]
                rendered = json.dumps(candidate, ensure_ascii=False, indent=2)
                if len(rendered) <= limit:
                    return rendered
                size //= 2
            raise ValueError("newest JSON evidence cannot fit the requested budget")
        trial_count = len(kept) + 1
        omitted = len(items) - trial_count
        candidate_size = (len(prefix) + len(str(omitted)) + len(",\n  \"items\": [\n")
                          + nested_total + nested_size + 2 * len(kept) + len(suffix))
        if candidate_size > limit:
            if not kept:
                total, prefix, tail = _encoded_excerpt(item, max(64, limit // 2))
                candidate = {"TRUNCATED": True, "omittedOlderEntries": len(items) - 1, "items": []}
                size = max(64, limit // 2)
                while size > 0:
                    candidate["items"] = [{"excerpt": _clip_encoded_excerpt(prefix, tail, total, size)}]
                    rendered = json.dumps(candidate, ensure_ascii=False, indent=2)
                    if len(rendered) <= limit:
                        return rendered
                    size //= 2
                raise ValueError("newest JSON evidence cannot fit the requested budget")
            break
        kept.append(item)
        nested_total += nested_size
    return json.dumps({"TRUNCATED": True, "omittedOlderEntries": len(items) - len(kept),
                       "items": list(reversed(kept))}, ensure_ascii=False, indent=2)


class ContextDocument:
    def __init__(self):
        self.sections = ["# Cross-Agent Continuation Context"]

    def add(self, title, value, limit=1400):
        rendered = clip_text(value or "Not established", limit) if isinstance(value, str) else bounded_json(value, limit)
        self.sections.append("## " + title + "\n" + rendered)

    def render(self):
        result = "\n\n".join(self.sections) + "\n"
        # Section allocations are fixed below the global budget. A future edit
        # must allocate space explicitly instead of silently cutting final sections.
        if len(result) > CONTEXT_LIMIT:
            raise ValueError("context section allocations exceed total budget")
        return result
