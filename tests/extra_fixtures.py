"""Synthetic stores only; never copies local user transcripts."""
import json
import sqlite3
from pathlib import Path


def varint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out) + bytes([value])


def proto(*items):
    out = b""
    for number, value in items:
        if isinstance(value, str):
            value = value.encode()
        out += varint(number * 8 + (2 if isinstance(value, bytes) else 0))
        out += varint(len(value)) + value if isinstance(value, bytes) else varint(value)
    return out


def grok(root):
    folder = root / "encoded-project" / "grok-fixture"
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps({"info": {"id": "grok-fixture", "cwd": str(root)}, "generated_title": "Grok 合成会话", "created_at": "2026-09-05T00:00:00Z", "updated_at": "2026-09-05T00:01:00Z"}), encoding="utf-8")
    updates = [
        {"sessionUpdate": "user_message_chunk", "content": {"text": "Build a "}},
        {"sessionUpdate": "user_message_chunk", "content": {"text": "sample"}},
        {"sessionUpdate": "agent_thought_chunk", "content": {"text": "PRIVATE_REASONING_SENTINEL"}},
        {"sessionUpdate": "tool_call", "toolCallId": "g1", "rawInput": {"command": "python -m unittest"}, "_meta": {"x.ai/tool": {"name": "shell"}}},
        {"sessionUpdate": "tool_call_update", "toolCallId": "g1", "status": "failed", "rawOutput": "Process exited with code 1"},
        {"sessionUpdate": "agent_message_chunk", "content": {"text": "Tests failed; "}},
        {"sessionUpdate": "agent_message_chunk", "content": {"text": "fix pending."}},
        {"sessionUpdate": "turn_completed"},
    ]
    (folder / "updates.jsonl").write_text("".join(json.dumps({"params": {"update": u}}) + "\n" for u in updates), encoding="utf-8")
    return folder


def opencode(root):
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "opencode.db")
    db.executescript("""
    CREATE TABLE session(id TEXT PRIMARY KEY, parent_id TEXT, title TEXT, directory TEXT, time_created INTEGER, time_updated INTEGER, revert TEXT);
    CREATE TABLE message(id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
    CREATE TABLE part(id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
    CREATE TABLE session_message(id TEXT, session_id TEXT);
    """)
    db.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?)", ("oc-fixture", None, "OpenCode 合成会话", str(root), 1788566400000, 1788566460000, None))
    db.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?)", ("oc-child", "oc-fixture", "child", str(root), 1, 2, None))
    for n, role in enumerate(("user", "assistant", "user"), 1):
        mid = "m" + str(n)
        db.execute("INSERT INTO message VALUES (?,?,?,?)", (mid, "oc-fixture", n, json.dumps({"role": role, "finish": "stop" if role == "assistant" else None})))
        db.execute("INSERT INTO part VALUES (?,?,?,?,?)", ("p" + str(n), mid, "oc-fixture", n, json.dumps({"type": "text", "text": ("Build sample", "Sample written", "Reverted request")[n-1]})))
    for pid, payload in [("p4", {"type": "reasoning", "text": "PRIVATE_REASONING_SENTINEL"}), ("p5", {"type": "tool", "callID": "oc-tool", "tool": "bash", "state": {"status": "completed", "input": {"command": "python -m unittest"}, "output": "Process exited with code 0"}})]:
        db.execute("INSERT INTO part VALUES (?,?,?,?,?)", (pid, "m2", "oc-fixture", 2, json.dumps(payload)))
    db.commit()
    db.close()


def antigravity(root):
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "ag-fixture.db")
    db.executescript("""
    CREATE TABLE trajectory_meta(trajectory_id TEXT);
    CREATE TABLE trajectory_metadata_blob(id TEXT,data BLOB);
    CREATE TABLE steps(idx INTEGER,step_type INTEGER,status INTEGER,metadata BLOB,step_payload BLOB,step_format INTEGER);
    """)
    db.execute("INSERT INTO trajectory_meta VALUES ('ag-fixture')")
    stamp = proto((1, 1788566400))
    meta = proto((2, stamp), (7, root.as_uri()))
    db.execute("INSERT INTO trajectory_metadata_blob VALUES ('meta',?)", (meta,))
    stepmeta = proto((1, stamp), (8, stamp))
    steps = [
        (14, proto((19, proto((3, proto((1, "Build an Antigravity sample"))))))),
        (15, proto((20, proto((1, "I will run the tests."), (3, "PRIVATE_REASONING_SENTINEL"), (16, "RAW_REASONING_SENTINEL"))))),
        (21, proto((28, proto((23, "python -m unittest"), (2, str(root)), (6, 0), (21, proto((1, "Tests passed"))))))),
    ]
    for idx, (kind, payload) in enumerate(steps):
        full = proto((1, kind), (4, 3), (5, stepmeta)) + payload
        db.execute("INSERT INTO steps VALUES (?,?,?,?,?,0)", (idx, kind, 3, stepmeta, full))
    db.commit()
    db.close()


BUILDERS = {"grok": grok, "opencode": opencode, "antigravity": antigravity}
