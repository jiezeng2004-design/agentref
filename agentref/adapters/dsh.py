"""Read-only DSH version-0 JSONL/Zstandard history and title projections."""
import json
from bisect import bisect_left
from contextlib import contextmanager
import os
from operator import itemgetter
from pathlib import Path
import stat

from ..core import SessionIR
from .base import text_content
from .snapshot import SnapshotAdapter, timestamp

MAX_LINE = 16 * 1024 * 1024
MAX_HISTORY = 128 * 1024 * 1024
_PACKED_EVENT_TYPES = frozenset(("text-chunks", "reasoning-chunks", "tool-call-chunks"))
_SURFACE_EVENT_TYPES = frozenset(("user/message", "assistant/message", "tool/result"))
_PASSIVE_EVENT_TYPES = frozenset(("turn/start", "turn/end", "step/start", "step/end", "tool/call",
                                 "assistant/chunk", "request/header", "request/context", "session/end-seed"))
_JSON_DECODER = json.JSONDecoder()
_SURFACE_SEQUENCE = itemgetter(0)


def _loads_jsonl_record(line):
    """Fast-path compact UTF-8 object lines; retain json.loads fallback semantics."""
    if line.startswith(b"{") and line.endswith(b"\n") and line[-2] != 13:
        try:
            text = line.decode("utf-8")
            value, end = _JSON_DECODER.raw_decode(text)
        except (UnicodeError, ValueError):
            pass
        else:
            if end == len(text) - 1:
                return value
    return json.loads(line)


class DshAdapter(SnapshotAdapter):
    agent = "dsh"

    def metadata_dependencies(self, path):
        path = Path(path)
        root = next((root for root in self.roots if path.is_relative_to(root)), None)
        if root is None:
            return super().metadata_dependencies(path)
        projection = root / "storages/session_projcache/sessions" / (path.parent.name + ".json")
        return (path, projection)

    @contextmanager
    def stream(self, path):
        with self._stream_checked(self.checked(path)) as stream:
            yield stream

    @contextmanager
    def _stream_checked(self, path):
        """Open a path already validated by this adapter's public boundary."""
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
        data = _loads_jsonl_record(line)
        if not isinstance(data, dict) or data.get("type") != "session" or data.get("version") != 0 or not isinstance(data.get("id"), str) or not data["id"]:
            raise ValueError("unsupported DSH session format")
        return data

    def metadata(self, path):
        return self._metadata_checked(self.checked(path))

    def _metadata_checked(self, path, cache_dir_present=None, root=None):
        with self._stream_checked(path) as stream:
            header = self.header(stream)
        if header.get("origin") == "subagent" or header.get("delegationDepth", 0) > 0:
            return None
        s = SessionIR(agent=self.agent, sessionId=header["id"], title="未命名 DSH 会话",
                      cwd=header.get("cwd", ""), createdAt=timestamp(header.get("createdAt")),
                      updatedAt=timestamp(path.stat().st_mtime), sourcePath=str(path))
        if cache_dir_present is False:
            return s
        # Cache identity must match the log. Never use cache paths or body projections.
        root = root or next(r for r in self.roots if path.is_relative_to(r))
        cache = root / "storages/session_projcache/sessions" / (path.parent.name + ".json")
        if cache_dir_present is not False and cache.is_file():
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
        path_roots = {}
        trusted_paths = set()
        cache_dirs = {root: (root / "storages/session_projcache/sessions").is_dir() for root in self.roots}

        def add(path, root, trusted=False):
            paths.append(path)
            path_roots.setdefault(path, root)
            if trusted:
                trusted_paths.add(path)

        def scan_error_path(path, root):
            add(path / "__agentref_scan_error__" / "session.jsonl", root)

        for root in self.roots:
            # Explicit live-session directory only; never scan recovery backups.
            sessions_root = root / "sessions"
            try:
                sessions_info = os.lstat(sessions_root)
            except FileNotFoundError:
                continue
            except OSError:
                scan_error_path(sessions_root, root)
                continue
            if (SnapshotAdapter._stat_is_symlink_or_junction(sessions_info)
                    or not stat.S_ISDIR(sessions_info.st_mode)):
                scan_error_path(sessions_root, root)
                continue
            try:
                with os.scandir(sessions_root) as entries:
                    projects = sorted(entries, key=lambda entry: entry.name)
            except OSError:
                scan_error_path(sessions_root, root)
                continue

            for project in projects:
                project_path = Path(project.path)
                try:
                    project_info = project.stat(follow_symlinks=False)
                except OSError:
                    scan_error_path(project_path, root)
                    continue
                if SnapshotAdapter._stat_is_symlink_or_junction(project_info):
                    scan_error_path(project_path, root)
                    continue
                if not stat.S_ISDIR(project_info.st_mode):
                    continue
                try:
                    with os.scandir(project.path) as entries:
                        folders = sorted(entries, key=lambda entry: entry.name)
                except OSError:
                    scan_error_path(project_path, root)
                    continue

                for folder in folders:
                    folder_path = Path(folder.path)
                    try:
                        folder_info = folder.stat(follow_symlinks=False)
                    except OSError:
                        scan_error_path(folder_path, root)
                        continue
                    if SnapshotAdapter._stat_is_symlink_or_junction(folder_info):
                        scan_error_path(folder_path, root)
                        continue
                    if not stat.S_ISDIR(folder_info.st_mode):
                        continue
                    try:
                        with os.scandir(folder.path) as entries:
                            session_entries = {entry.name: entry for entry in entries
                                               if entry.name in ("session.jsonl", "session.jsonl.zstd")}
                    except OSError:
                        scan_error_path(folder_path, root)
                        continue
                    candidates = []
                    for name in ("session.jsonl", "session.jsonl.zstd"):
                        entry = session_entries.get(name)
                        if entry is None:
                            continue
                        path = Path(entry.path)
                        try:
                            info = entry.stat(follow_symlinks=False)
                        except OSError:
                            candidates.append((path, False))
                            continue
                        if SnapshotAdapter._stat_is_symlink_or_junction(info):
                            candidates.append((path, False))
                        elif stat.S_ISREG(info.st_mode):
                            candidates.append((path, True))
                    if len(candidates) == 1:
                        add(candidates[0][0], root, trusted=candidates[0][1])
                    elif len(candidates) > 1:
                        # Do not guess which competing representation is authoritative.
                        add(folder_path / "ambiguous-session-format", root)

        def read(path):
            # The configured root is retained during discovery; avoid a full
            # root-membership scan for every session file.
            root = path_roots[path]
            checked = path if path in trusted_paths else self.checked(path, root=root)
            return self._metadata_checked(checked, cache_dir_present=cache_dirs[root], root=root)

        yield from self.scan_files(paths, read)

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
        s = self._metadata_checked(path)
        if s is None:
            raise ValueError("DSH subagent session is not exposed")
        calls, surface, expected, size = {}, [], 0, 0
        surface_ordered = True
        replaced_until = -1
        final_state = None
        event_errors = []
        with self._stream_checked(path) as stream:
            self.header(stream)
            while line := stream.readline(MAX_LINE + 1):
                size += len(line)
                if len(line) > MAX_LINE or size > MAX_HISTORY:
                    raise ValueError("DSH history exceeds read limit")
                if not line.endswith(b"\n"):
                    s.parseWarnings.append("incomplete trailing DSH record excluded")
                    break
                event = _loads_jsonl_record(line)
                if not isinstance(event, dict):
                    raise ValueError("invalid DSH event envelope")
                data = event.get("data")
                if not isinstance(data, dict):
                    raise ValueError("invalid DSH event envelope")
                kind = event.get("type")
                if kind in _PACKED_EVENT_TYPES:
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
                if kind == "tool/call":
                    calls[data["callId"]] = (event["seq"], data["name"], data["arguments"])
                if kind in ("turn/start", "tool/call", "user/message"):
                    final_state = "incomplete"
                elif kind == "turn/end":
                    reason = data.get("reason", {})
                    final_state = "turn_ended" if reason.get("kind") == "completed" else "incomplete"
                    if reason.get("kind") == "error":
                        event_errors.append(json.dumps(reason.get("error"), ensure_ascii=False))
                op = event.get("surfaceOp")
                if op is not None and kind not in _SURFACE_EVENT_TYPES:
                    raise ValueError("unsupported DSH surface event")
                if op == "append":
                    surface.append((event["seq"], kind, data))
                    if len(surface) > 1 and surface_ordered and surface[-2][0] >= surface[-1][0]:
                        surface_ordered = False
                elif isinstance(op, dict) and op.get("op") == "replace":
                    start_value, end_value = op["start"], op["end"]
                    if surface_ordered and type(start_value) is int and type(end_value) is int:
                        start = bisect_left(surface, start_value, key=_SURFACE_SEQUENCE)
                        end = bisect_left(surface, end_value, key=_SURFACE_SEQUENCE)
                        if (start == len(surface) or surface[start][0] != start_value
                                or end == len(surface) or surface[end][0] != end_value):
                            raise ValueError("invalid DSH surface replacement")
                    else:
                        seqs = [entry[0] for entry in surface]
                        start, end = seqs.index(start_value), seqs.index(end_value)
                    if start > end:
                        raise ValueError("invalid DSH surface replacement")
                    ends_at_tail = end == len(surface) - 1
                    surface[start:end + 1] = [(event["seq"], kind, data)]
                    if not ends_at_tail:
                        surface_ordered = False
                    replaced_until = max(replaced_until, op["end"])
                    s.parseWarnings.append("DSH compacted surface used; replaced messages excluded")
                elif op is not None:
                    raise ValueError("unsupported DSH surface operation")
                elif kind in _SURFACE_EVENT_TYPES:
                    raise ValueError("DSH message lacks supported surface metadata")
                elif kind not in _PASSIVE_EVENT_TYPES:
                    self.unknown(s, kind)
        added_calls = set()
        for _, kind, d in surface:
            if kind == "user/message":
                if d.get("source", {}).get("kind") == "user":
                    self.message(s, "user", text_content(d.get("content")))
                else:
                    self.message(s, "assistant", "[Historical injected context]\n" + text_content(d.get("content")))
            elif kind == "assistant/message":
                blocks = d.get("message", {}).get("content", [])
                self.message(s, "assistant", text_content([b for b in blocks if b.get("type") == "text"]))
                for b in blocks:
                    if b.get("type") == "tool-call":
                        self.call(s, b["id"], b["name"], b["arguments"])
                        added_calls.add(b["id"])
            elif kind == "tool/result":
                for block in d.get("message", {}).get("content", []):
                    cid = block.get("callId", block.get("toolCallId", block.get("id")))
                    call_data = calls.get(cid)
                    if call_data is not None:
                        if cid not in added_calls:
                            self.call(s, cid, call_data[1], call_data[2])
                            added_calls.add(cid)
                        self.result(s, cid, block.get("content", block.get("result", "")), bool(d.get("error") or block.get("isError")))
                    else:
                        s.parseWarnings.append("DSH result has no matching historical tool call")
        # A crash may persist tool/call before its assembled assistant message.
        # Keep such pending calls, except evidence shadowed by compaction.
        for cid, (call_seq, call_name, call_arguments) in calls.items():
            if cid not in added_calls and call_seq > replaced_until:
                self.call(s, cid, call_name, call_arguments)
        if final_state is not None:
            s.latestAgentState = final_state
        s.errors.extend(event_errors)
        self.finish(s)
        return s
