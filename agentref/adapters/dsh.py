"""Read-only DSH version-0 JSONL/Zstandard history and title projections."""
import json
from contextlib import contextmanager
from pathlib import Path

from ..core import SessionIR
from .base import text_content
from .snapshot import SnapshotAdapter, timestamp

MAX_LINE = 16 * 1024 * 1024
MAX_HISTORY = 128 * 1024 * 1024


class DshAdapter(SnapshotAdapter):
    agent = "dsh"

    @contextmanager
    def stream(self, path):
        path = self.checked(path)
        try:
            if path.suffix == ".zstd":
                try:
                    from compression import zstd
                    with zstd.open(path, "rb") as stream:
                        yield stream
                except ImportError:
                    import zstandard
                    with path.open("rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as reader:
                        import io
                        with io.BufferedReader(reader) as stream:
                            yield stream
            else:
                with path.open("rb") as stream:
                    yield stream
        except (EOFError, ImportError) as exc:
            raise ValueError("DSH compressed history unavailable or incomplete") from exc
        except Exception as exc:
            if type(exc).__name__ == "ZstdError":
                raise ValueError("DSH compressed history is corrupt") from exc
            raise

    def header(self, stream):
        line = stream.readline(65537)
        if len(line) > 65536 or not line.endswith(b"\n"):
            raise ValueError("invalid DSH header")
        data = json.loads(line)
        if not isinstance(data, dict) or data.get("type") != "session" or data.get("version") != 0 or not isinstance(data.get("id"), str) or not data["id"]:
            raise ValueError("unsupported DSH session format")
        return data

    def metadata(self, path):
        path = self.checked(path)
        with self.stream(path) as stream:
            header = self.header(stream)
        if header.get("origin") == "subagent" or header.get("delegationDepth", 0) > 0:
            return None
        s = SessionIR(agent=self.agent, sessionId=header["id"], title="未命名 DSH 会话",
                      cwd=header.get("cwd", ""), createdAt=timestamp(header.get("createdAt")),
                      updatedAt=timestamp(path.stat().st_mtime), sourcePath=str(path))
        # Cache identity must match the log. Never use cache paths or body projections.
        root = next(r for r in self.roots if path.resolve().is_relative_to(r))
        cache = root / "storages/session_projcache/sessions" / (path.parent.name + ".json")
        if cache.is_file():
            try:
                record = json.loads(self.checked(cache).read_text(encoding="utf-8"))["record"]
                identity = record["identity"]
                if identity.get("createdAt") == header.get("createdAt") and identity.get("cwd", "") == s.cwd:
                    title = record.get("rows", {}).get("title", {}).get("val")
                    if isinstance(title, str) and title.strip():
                        s.title = title
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                s.parseWarnings.append("DSH title cache unavailable; header metadata used")
        return s

    def scan_metadata(self):
        paths = []
        for root in self.roots:
            # Explicit live-session directory only; never scan recovery backups.
            for folder in sorted((root / "sessions").glob("*/*")):
                candidates = [p for p in (folder / "session.jsonl", folder / "session.jsonl.zstd") if p.is_file()]
                if len(candidates) == 1:
                    paths.append(candidates[0])
                elif len(candidates) > 1:
                    # Do not guess which competing representation is authoritative.
                    paths.append(folder / "ambiguous-session-format")
        yield from self.scan_files(paths, self.metadata)

    def read_indexed(self, row):
        session = self.readSession(row["sourcePath"])
        if session.sessionId != row["sessionId"]:
            raise ValueError("DSH source identity changed; select the refreshed candidate")
        return session

    def readSession(self, path):
        try:
            return self._read_session(path)
        except (AttributeError, KeyError, TypeError, IndexError) as exc:
            # Malformed nested records fail this resource, not the MCP process.
            raise ValueError("unsupported DSH record shape") from exc

    def _read_session(self, path):
        path = self.checked(path)
        s = self.metadata(path)
        if s is None:
            raise ValueError("DSH subagent session is not exposed")
        events, surface, expected, size = [], [], 0, 0
        with self.stream(path) as stream:
            self.header(stream)
            while line := stream.readline(MAX_LINE + 1):
                size += len(line)
                if len(line) > MAX_LINE or size > MAX_HISTORY:
                    raise ValueError("DSH history exceeds read limit")
                if not line.endswith(b"\n"):
                    s.parseWarnings.append("incomplete trailing DSH record excluded")
                    break
                event = json.loads(line)
                if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
                    raise ValueError("invalid DSH event envelope")
                kind, data = event.get("type"), event.get("data", {})
                if kind in ("text-chunks", "reasoning-chunks", "tool-call-chunks"):
                    chunks = data.get("args" if kind == "tool-call-chunks" else "texts")
                    if event.get("seq0") != expected or not isinstance(chunks, list) or not chunks or not all(isinstance(c, str) for c in chunks):
                        raise ValueError("invalid DSH packed sequence")
                    gaps = data.get("dt")
                    if not isinstance(gaps, list) or len(gaps) != len(chunks) - 1 or not all(type(g) is int for g in gaps):
                        raise ValueError("invalid DSH packed timestamps")
                    expected += len(chunks)
                    continue  # Assembled assistant/message owns visible content.
                if event.get("seq") != expected:
                    raise ValueError("DSH event sequence gap")
                expected += 1
                events.append(event)
                op = event.get("surfaceOp")
                if op is not None and kind not in ("user/message", "assistant/message", "tool/result"):
                    raise ValueError("unsupported DSH surface event")
                if op == "append":
                    surface.append(event)
                elif isinstance(op, dict) and op.get("op") == "replace":
                    seqs = [e["seq"] for e in surface]
                    start, end = seqs.index(op["start"]), seqs.index(op["end"])
                    if start > end:
                        raise ValueError("invalid DSH surface replacement")
                    surface[start:end + 1] = [event]
                    s.parseWarnings.append("DSH compacted surface used; replaced messages excluded")
                elif op is not None:
                    raise ValueError("unsupported DSH surface operation")
                elif kind in ("user/message", "assistant/message", "tool/result"):
                    raise ValueError("DSH message lacks supported surface metadata")
                elif kind not in ("turn/start", "turn/end", "step/start", "step/end", "tool/call",
                                  "assistant/chunk", "request/header", "request/context", "session/end-seed"):
                    self.unknown(s, kind)
        calls = {e["data"]["callId"]: e for e in events if e["type"] == "tool/call"}
        added_calls = set()
        for e in surface:
            d = e["data"]
            if e["type"] == "user/message":
                if d.get("source", {}).get("kind") == "user":
                    self.message(s, "user", text_content(d.get("content")))
                else:
                    self.message(s, "assistant", "[Historical injected context]\n" + text_content(d.get("content")))
            elif e["type"] == "assistant/message":
                blocks = d.get("message", {}).get("content", [])
                self.message(s, "assistant", text_content([b for b in blocks if b.get("type") == "text"]))
                for b in blocks:
                    if b.get("type") == "tool-call":
                        self.call(s, b["id"], b["name"], b["arguments"])
                        added_calls.add(b["id"])
            elif e["type"] == "tool/result":
                for block in d.get("message", {}).get("content", []):
                    cid = block.get("callId", block.get("toolCallId", block.get("id")))
                    call = calls.get(cid)
                    if call:
                        if cid not in added_calls:
                            self.call(s, cid, call["data"]["name"], call["data"]["arguments"])
                            added_calls.add(cid)
                        self.result(s, cid, block.get("content", block.get("result", "")), bool(d.get("error") or block.get("isError")))
                    else:
                        s.parseWarnings.append("DSH result has no matching historical tool call")
        # A crash may persist tool/call before its assembled assistant message.
        # Keep such pending calls, except evidence shadowed by compaction.
        replaced_until = max((e["surfaceOp"]["end"] for e in events
                              if isinstance(e.get("surfaceOp"), dict)), default=-1)
        for cid, event in calls.items():
            if cid not in added_calls and event["seq"] > replaced_until:
                data = event["data"]
                self.call(s, cid, data["name"], data["arguments"])
        for e in events:
            if e["type"] in ("turn/start", "tool/call", "user/message"):
                s.latestAgentState = "incomplete"
            elif e["type"] == "turn/end":
                reason = e["data"].get("reason", {})
                s.latestAgentState = "turn_ended" if reason.get("kind") == "completed" else "incomplete"
                if reason.get("kind") == "error":
                    s.errors.append(json.dumps(reason.get("error"), ensure_ascii=False))
        self.finish(s)
        return s
