"""Antigravity SQLite/Step protobuf, field numbers verified from installed schema.

Only public user/assistant text and structured tool metadata are interpreted.
Thinking, signatures, model configuration and arbitrary binary strings are ignored.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from urllib.parse import unquote, urlsplit
from ..core import SessionIR
from .snapshot import SnapshotAdapter, timestamp
from .protobuf import fields, first, string

_METADATA_SCAN_ERROR = object()


def proto_time(data):
    return timestamp(first(fields(data), 1, 0)) if data else ""


def user_text(step):
    payload = fields(first(step, 19))
    items = "".join(string(fields(item), 1) for item in payload.get(3, []))
    return items or string(payload, 1) or string(payload, 2)


def local_path(uri):
    parsed = urlsplit(uri)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return ""
    path = unquote(parsed.path)
    return path[1:] if len(path) > 2 and path[0] == "/" and path[2] == ":" else path


class AntigravityAdapter(SnapshotAdapter):
    agent = "antigravity"
    metadata_parallel_threshold = 32
    metadata_workers = 8

    def metadata(self, db, path):
        row = db.execute("""SELECT meta.trajectory_id, blob.data AS metadata_blob,
                                  first_user.step_payload AS first_user_payload,
                                  first_user.step_format AS first_user_format,
                                  last_step.metadata AS last_metadata,
                                  last_step.status AS last_status
                           FROM (SELECT trajectory_id FROM trajectory_meta LIMIT 1) AS meta
                           LEFT JOIN (SELECT data FROM trajectory_metadata_blob LIMIT 1) AS blob ON 1=1
                           LEFT JOIN (SELECT step_payload,step_format FROM steps
                                      WHERE step_type=14 ORDER BY idx LIMIT 1) AS first_user ON 1=1
                           LEFT JOIN (SELECT metadata,status FROM steps
                                      ORDER BY idx DESC LIMIT 1) AS last_step ON 1=1""").fetchone()
        if row is None or row["trajectory_id"] is None:
            raise ValueError("missing Antigravity trajectory identity")
        s = SessionIR(agent=self.agent, sessionId=row["trajectory_id"], sourcePath=str(path))
        if row["metadata_blob"] is not None:
            m = fields(row["metadata_blob"])
            # Subagents must not be listed as unrelated main conversations.
            if first(m, 8):
                return None
            s.createdAt = proto_time(first(m, 2))
            uris = [v.decode("utf-8") for v in m.get(7, [])]
            for workspace in m.get(1, []):
                uris.append(string(fields(workspace), 1))
            for uri in uris:
                s.cwd = local_path(uri)
                if s.cwd:
                    break
        if row["first_user_payload"] is not None and row["first_user_format"] == 0:
            s.title = user_text(fields(row["first_user_payload"])).split("\n", 1)[0][:120]
        if row["last_metadata"] is not None or row["last_status"] is not None:
            m = fields(row["last_metadata"] or b"")
            s.updatedAt = proto_time(first(m, 8) or first(m, 22) or first(m, 1))
            s.latestAgentState = "incomplete" if row["last_status"] in (1, 2, 6, 7, 8, 9, 11, 12) else "unknown"
        s.updatedAt = s.updatedAt or timestamp(path.stat().st_mtime)
        return s

    def scan_metadata(self):
        paths = [p for root in self.roots for p in sorted(root.glob("*.db"))]
        if len(paths) < self.metadata_parallel_threshold:
            def read(path):
                with self.database(path) as db:
                    return self.metadata(db, path)
            yield from self.scan_files(paths, read)
            return

        self.scan_errors = []

        def read(path):
            try:
                with self.database(path) as db:
                    return self.metadata(db, path)
            except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
                return _METADATA_SCAN_ERROR

        batch_size = max(1, min(8, len(paths) // (self.metadata_workers * 4)))
        batches = (paths[start:start + batch_size]
                   for start in range(0, len(paths), batch_size))

        def read_batch(batch):
            return [read(path) for path in batch]

        with ThreadPoolExecutor(max_workers=self.metadata_workers, thread_name_prefix="agentref-ag-metadata") as pool:
            for batch_results in pool.map(read_batch, batches):
                for result in batch_results:
                    if result is _METADATA_SCAN_ERROR:
                        self.scan_errors.append(self.agent + ": source metadata unavailable or unsupported")
                    elif result is not None:
                        yield result

    def readSession(self, path):
        path = self.checked(path)
        with self.database(path) as db:
            s = self.metadata(db, path)
            if s is None:
                raise ValueError("subagent trajectory excluded")
            for row in db.execute("SELECT idx,step_type,status,step_payload,step_format FROM steps ORDER BY idx"):
                try:
                    if row["step_format"] != 0:
                        raise ValueError("unsupported step format")
                    step = fields(row["step_payload"])
                    if first(step, 1, 0) != row["step_type"]:
                        raise ValueError("inconsistent step type")
                    if 19 in step:
                        self.message(s, "user", user_text(step))
                    elif 20 in step:
                        response = fields(first(step, 20))
                        self.message(s, "assistant", string(response, 8) or string(response, 1))
                        # Do not pre-add planner calls; their execution steps carry evidence.
                    else:
                        metadata = fields(first(step, 5))
                        call = fields(first(metadata, 29) or first(metadata, 4))
                        cid = string(call, 1) or "step-" + str(row["idx"])
                        name = string(call, 2) or "antigravity_step_" + str(row["step_type"])
                        args = string(call, 3) or {}
                        if 28 in step:
                            command = fields(first(step, 28))
                            args = {"cmd": string(command, 23) or string(command, 1), "cwd": string(command, 2)}
                            name = "run_command"
                            self.call(s, cid, name, args)
                            output = fields(first(command, 21) or first(command, 26))
                            text = string(output, 1) or string(output, 2) or string(command, 4)
                            if 6 in command:
                                code = first(command, 6, 0)
                                if code >= 2**63:
                                    code -= 2**64
                                text += "\nHistorical exit code: " + str(code)
                            if row["status"] in (3, 7):
                                self.result(s, cid, text or "Historical step ended; command completion unverified", row["status"] == 7)
                        elif 37 in step:
                            status = fields(first(step, 37))
                            self.call(s, cid, "command_status", {"command_id": string(status, 1)})
                            if row["status"] in (3, 7):
                                output = string(status, 9) or string(status, 3)
                                if 5 in status:
                                    code = first(status, 5, 0)
                                    output += "\nHistorical exit code: " + str(code if code < 2**63 else code - 2**64)
                                self.result(s, cid, output, row["status"] == 7)
                        elif call:
                            self.call(s, cid, name, args)
                            if row["status"] in (3, 7):
                                self.result(s, cid, "Historical step status " + str(row["status"]) + "; tool output not decoded", row["status"] == 7)
                            self.unknown(s, "tool payload " + str(row["step_type"]))
                        else:
                            self.unknown(s, "step " + str(row["step_type"]))
                except (TypeError, ValueError, UnicodeError):
                    s.parseWarnings.append("unsupported Antigravity step " + str(row["idx"]) + "; partially skipped")
        s.parseWarnings.append("Antigravity experimental: non-command tool payloads and attachments are not decoded; reconcile current files before continuing")
        self.finish(s)
        return s
