import json


def dsh(root):
    folder = root / "sessions/project/session-synthetic"
    folder.mkdir(parents=True, exist_ok=True)
    header = dict(type="session", version=0, id="session-synthetic", createdAt=1700000000000,
                  cwd=str(root), delegationDepth=0)
    records = [header,
        dict(seq=0, time=1700000000001, type="user/message", surfaceOp="append",
             data=dict(role="user", source=dict(kind="user"), content=[dict(type="text", text="Build a DSH sample")])),
        dict(seq=1, time=1700000000002, type="assistant/message", surfaceOp="append",
             data=dict(turn=0, step=0, message=dict(role="assistant", content=[dict(type="text", text="I will verify it.")]))),
        dict(seq=2, time=1700000000003, type="turn/end", data=dict(turn=0, reason=dict(kind="completed")))]
    path = folder / "session.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path
