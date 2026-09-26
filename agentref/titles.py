"""Explicit, bounded local title extraction. Never called by mention browsing."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from .adapters.base import text_content
from .adapters.snapshot import SnapshotAdapter
from .mentions import is_unnamed, short_text

MAX_BYTES = 2 * 1024 * 1024
MAX_LINE = 256 * 1024
CACHE = "derived-titles.json"


def identity(row):
    fields = [row.get(k, "") for k in ("agent", "sessionId", "sourcePath", "createdAt", "cwd")]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()


def load_cache(home, strict=False):
    try:
        path = Path(home) / CACHE
        if path.stat().st_size > 16 * 1024 * 1024:
            if strict:
                raise ValueError("title cache exceeds limit")
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if strict and not isinstance(data, dict):
            raise ValueError("invalid title cache")
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        if strict:
            raise
        return {}


def apply_cached_titles(home, rows, cache=None):
    if cache is None:
        cache = load_cache(home)
    if not cache:
        return
    for row in rows:
        record = cache.get(row["ref"])
        if (is_unnamed(row) and isinstance(record, dict) and record.get("identity") == identity(row)
                and isinstance(record.get("title"), str) and record["title"]):
            row["title"] = record["title"]
            row["titleSource"] = record.get("source", "local-user-request")


def request_title(text):
    if not isinstance(text, str):
        return ""
    text = text[:MAX_LINE]
    if "## My request:" in text:
        text = text.rsplit("## My request:", 1)[1]
    text = text.strip()
    if text.startswith(("<", "# AGENTS.md", "# Files", "## Referenced chats", "You are ",
                        "This is an authorized interrupted", "<environment_context>")):
        return ""
    line = next((s.strip().lstrip("# ") for s in text.splitlines() if s.strip()), "")
    if line.casefold() in ("继续", "继续吧", "好的", "好", "是", "ok", "yes", "continue", "授权"):
        return ""
    # Avoid copying credential-like strings, URLs or personal contact details into menus.
    if re.search(r"(?i)(api[_ -]?key|token|password|secret|密码|密钥)\s*[:=：]|sk-[\w-]+|"
                 r"https?://\S+|[\w.+-]+@[\w.-]+\.[a-z]+|[A-Za-z0-9_+/=-]{32,}|\b\d{11,}\b", line):
        return ""
    return short_text(line, 60)


def bounded_records(stream):
    used = 0
    for _ in range(2000):
        line = stream.readline(min(MAX_LINE + 1, MAX_BYTES - used + 1))
        if not line:
            break
        used += len(line)
        if used > MAX_BYTES or len(line) > MAX_LINE or not line.endswith(b"\n"):
            break
        value = json.loads(line)
        if isinstance(value, dict):
            yield value


def user_texts(adapter, row):
    """Read only bounded records/columns, without constructing continuation context."""
    agent = row["agent"]
    guard = SnapshotAdapter(adapter.roots)
    if agent == "opencode":
        source, sid = row["sourcePath"].rsplit("::", 1)
        if sid != row["sessionId"]:
            raise ValueError("identity mismatch")
        with adapter.database(source) as db:
            meta = db.execute("SELECT * FROM session WHERE id=? AND parent_id IS NULL", (sid,)).fetchone()
            current = vars(adapter.metadata(meta, Path(source))) if meta is not None else None
            if current is None or identity(current) != identity(row):
                raise ValueError("identity mismatch")
            if not is_unnamed(current):
                return
            revert = json.loads(meta["revert"] or "{}") if "revert" in meta.keys() else {}
            cutoff = revert.get("messageID")
            user_messages = []
            for msg in db.execute("SELECT id,substr(data,1,262144) AS data FROM message WHERE session_id=? ORDER BY time_created,id LIMIT 128", (sid,)):
                if msg["id"] == cutoff:
                    break
                if json.loads(msg["data"]).get("role") != "user":
                    continue
                user_messages.append(msg["id"])
            if user_messages:
                part_queries = []
                params = []
                for order, message_id in enumerate(user_messages):
                    part_queries.append("SELECT ? AS message_order,part_id,data,time_created FROM ("
                                        "SELECT id AS part_id,substr(data,1,262144) AS data,time_created "
                                        "FROM part WHERE message_id=? AND session_id=? "
                                        "ORDER BY time_created,id LIMIT 8)")
                    params.extend((order, message_id, sid))
                sql = " UNION ALL ".join(part_queries) + " ORDER BY message_order,time_created,part_id"
                for part in db.execute(sql, params):
                    data = json.loads(part["data"])
                    if data.get("type") == "text" and not data.get("ignored") and not data.get("synthetic"):
                        yield data.get("text", "")
        return
    path = guard.checked(row["sourcePath"])
    if agent == "antigravity":
        from .adapters.antigravity import user_text
        from .adapters.protobuf import fields
        with adapter.database(path) as db:
            current = adapter.metadata(db, path)
            if current is None or identity(vars(current)) != identity(row):
                raise ValueError("identity mismatch")
            for step in db.execute("SELECT step_payload,step_format FROM steps WHERE step_type=14 AND length(step_payload)<=262144 ORDER BY idx LIMIT 8"):
                if step[1] == 0:
                    yield user_text(fields(step[0]))
        return
    if agent == "dsh":
        current = adapter.metadata(path)
        if current is None or identity(vars(current)) != identity(row):
            raise ValueError("identity mismatch")
        with adapter.stream(path) as stream:
            adapter.header(stream)
            for record in bounded_records(stream):
                data = record.get("data") or {}
                if (record.get("type") == "user/message" and record.get("surfaceOp") == "append"
                        and data.get("source", {}).get("kind") == "user"):
                    yield text_content(data.get("content"))
        return
    if agent == "grok":
        if identity(vars(adapter.metadata(path))) != identity(row):
            raise ValueError("identity mismatch")
        path = guard.checked(path.parent / "updates.jsonl")
    with path.open("rb") as stream:
        verified = agent == "grok"
        chunks = []
        for record in bounded_records(stream):
            if agent == "claude":
                if record.get("sessionId"):
                    if record["sessionId"] != row["sessionId"]:
                        raise ValueError("identity mismatch")
                    verified = True
                if verified and record.get("type") == "user" and not record.get("isMeta") and not record.get("isSidechain"):
                    content = record.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        content = [p for p in content if isinstance(p, dict) and p.get("type") == "text"]
                    yield text_content(content)
            elif agent == "codex":
                payload = record.get("payload") or {}
                # Forked histories can retain older metadata records. The first
                # header owns identity, matching CodexAdapter.consume.
                if record.get("type") == "session_meta" and not verified:
                    if (payload.get("id") or payload.get("session_id")) != row["sessionId"]:
                        raise ValueError("identity mismatch")
                    verified = True
                if verified and record.get("type") == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
                    yield text_content(payload.get("content"))
            elif agent == "grok":
                update = record.get("params", {}).get("update", {})
                if update.get("sessionUpdate") == "user_message_chunk":
                    chunks.append(text_content(update.get("content")))
                elif chunks:
                    yield "".join(chunks)
                    chunks = []
        if chunks:
            yield "".join(chunks)


def organize(index):
    cache = load_cache(index.home, strict=True)
    stats = Counter()
    by_agent = {}
    for row in index.sessions():
        if not is_unnamed(row):
            continue
        stats["candidates"] += 1
        group = by_agent.setdefault(row["agent"], Counter())
        group["candidates"] += 1
        try:
            title = ""
            with closing(user_texts(index.adapters[row["agent"]], row)) as texts:
                for number, text in enumerate(texts):
                    title = request_title(text)
                    if title or number >= 7:
                        break
            if title:
                cache[row["ref"]] = dict(identity=identity(row), title=title, source="local-user-request",
                                          generatedAt=datetime.now(timezone.utc).isoformat())
                stats["derived"] += 1
                group["derived"] += 1
            else:
                stats["no_usable_request_within_limit"] += 1
                group["no_usable_request_within_limit"] += 1
        except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
            stats["errors"] += 1
            group["errors"] += 1
    target = index.home / CACHE
    fd, temporary = tempfile.mkstemp(prefix=".derived-titles-", suffix=".tmp", dir=index.home)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(cache, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return dict(stats=stats, byAgent=by_agent, cache=str(target))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    parser.add_argument("--agent", choices=("claude", "codex", "dsh", "grok", "opencode", "antigravity"))
    args = parser.parse_args()
    from .index import Index, default_adapters
    adapters = [a for a in default_adapters() if not args.agent or a.agent == args.agent]
    index = Index(args.data_dir, adapters)
    try:
        refreshed = index.refresh()
        result = organize(index)
        result["refreshWarningCount"] = len(refreshed["errors"])
        print(json.dumps(result, ensure_ascii=False))
    finally:
        index.close()


if __name__ == "__main__":
    main()
