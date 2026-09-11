"""Bounded, valid evidence rendering with recency and visible omissions."""
import json

CONTEXT_LIMIT = 32000  # Characters, not tokenizer-specific tokens.


def clip_text(text, limit):
    if len(text) <= limit:
        return text
    marker = f"\n[TRUNCATED from {len(text)} characters; middle omitted]\n"
    room = max(0, limit - len(marker))
    head = room // 2
    tail = room - head
    return text[:head] + marker + (text[-tail:] if tail else "")


def bounded_json(value, limit):
    """Prioritize newest list entries; never cut serialized JSON mid-record."""
    if limit < 256:
        raise ValueError("JSON evidence budget must be at least 256 characters")
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
                # A single large newest entry still gets a readable excerpt.
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
    return json.dumps({"TRUNCATED": True, "omittedOlderEntries": len(items) - len(kept), "items": kept}, ensure_ascii=False, indent=2)


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
