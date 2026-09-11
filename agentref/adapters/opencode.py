import json
from pathlib import Path
from ..core import SessionIR
from .snapshot import SnapshotAdapter, timestamp


class OpenCodeAdapter(SnapshotAdapter):
    agent = "opencode"

    def metadata(self, row, path):
        return SessionIR(agent=self.agent, sessionId=row["id"], title=row["title"],
                         cwd=row["directory"], createdAt=timestamp(row["time_created"]),
                         updatedAt=timestamp(row["time_updated"]),
                         sourcePath=str(path) + "::" + row["id"])

    def scan_metadata(self):
        def read(path):
            with self.database(path) as db:
                return [self.metadata(row, path) for row in db.execute("SELECT id,title,directory,time_created,time_updated FROM session WHERE parent_id IS NULL")]
        yield from self.scan_files((root / "opencode.db" for root in self.roots if (root / "opencode.db").is_file()), read)

    def read_indexed(self, row):
        path, sid = row["sourcePath"].rsplit("::", 1)
        if sid != row["sessionId"]:
            raise ValueError("inconsistent session locator")
        return self.read_session(path, sid)

    def read_session(self, path, sid):
        with self.database(path) as db:
            row = db.execute("SELECT * FROM session WHERE id=? AND parent_id IS NULL", (sid,)).fetchone()
            if row is None:
                raise ValueError("session unavailable")
            s = self.metadata(row, Path(path))
            revert = json.loads(row["revert"]) if "revert" in row.keys() and row["revert"] else {}
            cutoff = revert.get("messageID")
            if cutoff:
                s.parseWarnings.append("OpenCode reverted suffix excluded from active context")
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "session_message" in tables and db.execute("SELECT 1 FROM session_message WHERE session_id=? LIMIT 1", (sid,)).fetchone():
                raise ValueError("OpenCode event projection format not yet supported")
            for message in db.execute("SELECT id,data FROM message WHERE session_id=? ORDER BY time_created,id", (sid,)):
                if message["id"] == cutoff:
                    break
                try:
                    data = json.loads(message["data"])
                    role = data.get("role")
                    texts = []
                    for part in db.execute("SELECT data FROM part WHERE message_id=? AND session_id=? ORDER BY time_created,id", (message["id"], sid)):
                        p = json.loads(part[0])
                        kind = p.get("type")
                        if kind == "text" and not p.get("ignored"):
                            texts.append(p.get("text", ""))
                        elif kind == "tool":
                            state = p.get("state", {})
                            name = p.get("tool", "unknown")
                            name = {"write": "Write", "edit": "Edit"}.get(name, name)
                            args = dict(state.get("input") or {})
                            if "filePath" in args:
                                args["file_path"] = args["filePath"]
                            self.call(s, p.get("callID", ""), name, args)
                            if state.get("status") in ("completed", "error"):
                                output = state.get("output", state.get("error", ""))
                                self.result(s, p.get("callID", ""), output, state["status"] == "error")
                        elif kind not in ("reasoning", "step-start", "step-finish", "snapshot", "patch", "file", "agent", "compaction", "subtask", "retry"):
                            self.unknown(s, kind)
                    if role in ("user", "assistant"):
                        self.message(s, role, "\n".join(texts))
                    if data.get("error"):
                        s.errors.append(json.dumps(data["error"], ensure_ascii=False))
                    if role == "assistant" and data.get("finish") == "stop":
                        s.latestAgentState = "turn_ended"
                except (TypeError, ValueError, AttributeError):
                    s.parseWarnings.append("unsupported OpenCode message; partially skipped")
        self.finish(s)
        return s
