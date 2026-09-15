"""Reproducible all-source scale check using generated data, never personal history."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import tracemalloc
from contextlib import contextmanager

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
from extra_fixtures import BUILDERS, proto
from agentref.adapters.registry import ADAPTERS
from agentref.context_render import CONTEXT_LIMIT
from agentref.handoff import build_context
from agentref.index import Index
from agentref.mcp import Server

LATEST = "LATEST_INTENT: keep completed work and finish rollback, then verify current tests."
RECENT = "RECENT_HANDOFF: rollback is still pending; preserve the existing registry."


@contextmanager
def fixture_database(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


def append_jsonl(path, records):
    with path.open("a", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record) + "\n")


def create_sources(agent, root, count, turns, width, dsh_compressed=False):
    root.mkdir(parents=True)
    messages = [("assistant", f"Historical message {i}: " + "x" * width) for i in range(turns)]
    messages += [("user", LATEST), ("assistant", RECENT)]
    if agent == "dsh":
        if dsh_compressed:
            try:
                from compression import zstd
                compress = zstd.compress
            except ImportError:
                import zstandard
                compress = zstandard.ZstdCompressor().compress
        for i in range(count):
            folder = root / "sessions/project" / f"scale-{i}"
            folder.mkdir(parents=True)
            records = [dict(type="session", version=0, id=f"scale-{i}",
                            createdAt=1700000000000, cwd=str(root), delegationDepth=0)]
            turns_data = [("user", "Build a DSH scale sample")]
            if i == 0:
                turns_data += messages
            for seq, (role, content) in enumerate(turns_data):
                message = dict(role=role, content=[dict(type="text", text=content)])
                data = dict(**message, source=dict(kind="user")) if role == "user" else dict(message=message)
                records.append(dict(seq=seq, time=1700000000001 + seq,
                                    type=role + "/message", surfaceOp="append", data=data))
            raw = ("\n".join(map(json.dumps, records)) + "\n").encode("utf-8")
            path = folder / ("session.jsonl.zstd" if dsh_compressed else "session.jsonl")
            path.write_bytes(compress(raw) if dsh_compressed else raw)
            if i == 0:
                selected = path
        return str(selected)
    if agent in ("claude", "codex"):
        template = (REPO / "tests/fixtures" / f"{agent}-normal.jsonl").read_text(encoding="utf-8")
        for i in range(count):
            (root / f"session-{i:04d}.jsonl").write_text(template.replace(f"{agent}-demo", f"scale-{i}"), encoding="utf-8")
        selected = root / "session-0000.jsonl"
        if agent == "claude":
            records = ({"type": role, "message": {"role": role, "content": text}} for role, text in messages)
        else:
            records = ({"type": "response_item", "payload": {"type": "message", "role": role,
                        "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}]}} for role, text in messages)
        append_jsonl(selected, records)
        return str(selected)
    if agent == "grok":
        folder = BUILDERS[agent](root)
        for i in range(1, count):
            target = folder.parent / f"scale-{i}"
            shutil.copytree(folder, target)
            summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
            summary["info"]["id"] = f"scale-{i}"
            (target / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        updates = []
        for role, text in messages:
            updates += [{"params": {"update": {"sessionUpdate": "user_message_chunk" if role == "user" else "agent_message_chunk", "content": {"text": text}}}},
                        {"params": {"update": {"sessionUpdate": "turn_completed"}}}]
        append_jsonl(folder / "updates.jsonl", updates)
        return str(folder / "summary.json")
    BUILDERS[agent](root)
    if agent == "opencode":
        path = root / "opencode.db"
        with fixture_database(path) as db:
            db.execute("CREATE INDEX message_session_order ON message(session_id,time_created,id)")
            db.execute("CREATE INDEX part_message_order ON part(message_id,session_id,time_created,id)")
            for i in range(1, count):
                db.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?)", (f"scale-{i}", None, f"Scale {i}", str(root), 1, 2, None))
            for i, (role, text) in enumerate(messages, 10):
                mid = f"scale-m-{i}"
                db.execute("INSERT INTO message VALUES (?,?,?,?)", (mid, "oc-fixture", i, json.dumps({"role": role})))
                db.execute("INSERT INTO part VALUES (?,?,?,?,?)", (f"scale-p-{i}", mid, "oc-fixture", i, json.dumps({"type": "text", "text": text})))
        return str(path) + "::oc-fixture"
    path = root / "ag-fixture.db"
    for i in range(1, count):
        target = root / f"scale-{i}.db"
        shutil.copyfile(path, target)
        with fixture_database(target) as db:
            db.execute("UPDATE trajectory_meta SET trajectory_id=?", (f"scale-{i}",))
    with fixture_database(path) as db:
        for i, (role, text) in enumerate(messages, 10):
            kind = 14 if role == "user" else 15
            payload = proto((19, proto((3, proto((1, text)))))) if role == "user" else proto((20, proto((1, text))))
            db.execute("INSERT INTO steps VALUES (?,?,?,?,?,0)", (i, kind, 3, b"", proto((1, kind), (4, 3)) + payload))
    return str(path)


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


def check(agent, count=300, turns=600, width=2048, dsh_compressed=False):
    with tempfile.TemporaryDirectory(prefix="agentref-scale-") as temp:
        root = Path(temp).resolve()
        sources = root / "source"
        selected = create_sources(agent, sources, count, turns, width, dsh_compressed)
        before = hashes(sources)
        index = Index(root / "index", [ADAPTERS[agent]([sources])])
        try:
            started = time.perf_counter()
            cold = index.refresh()
            cold_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            warm = index.refresh()
            warm_ms = (time.perf_counter() - started) * 1000
            rows = index.sessions()
            row = next(r for r in rows if r["sourcePath"] == selected)
            started = time.perf_counter()
            menu = Server(index, agent=agent).mention_items({"query": ""})
            menu_ms = (time.perf_counter() - started) * 1000
            tracemalloc.start()
            started = time.perf_counter()
            try:
                session = index.read(row)
                context = build_context(session)
                context_ms = (time.perf_counter() - started) * 1000
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            assert len(rows) == count
            assert LATEST in context and RECENT in context and session.originalGoal in context
            assert len(context) <= CONTEXT_LIMIT
            assert "PRIVATE_REASONING_SENTINEL" not in context
            assert before == hashes(sources)
            assert not cold["errors"] and not warm["errors"]
            return {"agent": agent, "synthetic": True, "sessions": count, "longMessages": turns,
                    **({"sourceFormat": "jsonl.zstd" if dsh_compressed else "jsonl"} if agent == "dsh" else {}),
                    "messageWidth": width, "coldMs": round(cold_ms, 1), "warmMs": round(warm_ms, 1),
                    "menuMs": round(menu_ms, 1), "contextWithTracingMs": round(context_ms, 1),
                    "contextChars": len(context), "peakPythonMiB": round(peak / 1048576, 2),
                    "sourceBytes": sum(p.stat().st_size for p in sources.rglob("*") if p.is_file()),
                    "warmBytesReadCounter": warm["bytesRead"], "snapshotRescan": agent not in ("claude", "codex"),
                    "latestEvidencePreserved": True, "sourcesUnchanged": True, "modelCalled": False}
        finally:
            index.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=300)
    parser.add_argument("--turns", type=int, default=600)
    parser.add_argument("--width", type=int, default=2048)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.sessions <= 2000 or not 1 <= args.turns <= 5000 or not 1 <= args.width <= 8192:
        parser.error("bounded inputs required: sessions 1..2000, turns 1..5000, width 1..8192")
    results = []
    for agent in ADAPTERS:
        for compressed in ((False, True) if agent == "dsh" else (False,)):
            result = check(agent, args.sessions, args.turns, args.width, compressed)
            results.append(result)
            print(json.dumps(result), flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
