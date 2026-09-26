import json
import os
from pathlib import Path
import stat
from ..core import SessionIR
from ..parser import scan_jsonl
from .base import text_content
from .snapshot import SnapshotAdapter, timestamp


class GrokAdapter(SnapshotAdapter):
    agent = "grok"
    metadata_cache_enabled = True

    def metadata(self, path):
        return self._metadata_checked(self.checked(path))

    def _metadata_checked(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        info = data.get("info") or {}
        return SessionIR(agent=self.agent, sessionId=str(info.get("id") or path.parent.name),
                         title=data.get("generated_title") or data.get("session_summary", "")[:120],
                         cwd=info.get("cwd", ""), createdAt=timestamp(data.get("created_at")),
                         updatedAt=timestamp(data.get("updated_at")), sourcePath=str(path))

    def scan_metadata(self):
        # Main sessions only: encoded workspace / session / summary.json.
        paths = []
        path_roots = {}
        trusted_paths = set()

        def add(path, root, trusted=False):
            paths.append(path)
            path_roots.setdefault(path, root)
            if trusted:
                trusted_paths.add(path)

        def scan_error_path(path, root):
            add(path / "__agentref_scan_error__" / "summary.json", root)

        for root in self.roots:
            try:
                with os.scandir(root) as entries:
                    projects = sorted(entries, key=lambda entry: entry.name)
            except FileNotFoundError:
                continue
            except OSError:
                scan_error_path(root, root)
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
                        sessions = sorted(entries, key=lambda entry: entry.name)
                except OSError:
                    scan_error_path(project_path, root)
                    continue

                for session in sessions:
                    session_path = Path(session.path)
                    try:
                        session_info = session.stat(follow_symlinks=False)
                    except OSError:
                        scan_error_path(session_path, root)
                        continue
                    if SnapshotAdapter._stat_is_symlink_or_junction(session_info):
                        scan_error_path(session_path, root)
                        continue
                    if not stat.S_ISDIR(session_info.st_mode):
                        continue
                    try:
                        with os.scandir(session.path) as files:
                            summary_entry = next((entry for entry in files
                                                  if entry.name == "summary.json"), None)
                    except OSError:
                        scan_error_path(session_path, root)
                        continue
                    if summary_entry is None:
                        continue
                    summary = Path(summary_entry.path)
                    try:
                        summary_info = summary_entry.stat(follow_symlinks=False)
                    except OSError:
                        add(summary, root)
                        continue
                    trusted = (stat.S_ISREG(summary_info.st_mode)
                               and not SnapshotAdapter._stat_is_symlink_or_junction(summary_info))
                    add(summary, root, trusted=trusted)

        def read(path):
            if path in trusted_paths:
                return self._metadata_checked(path)
            return self.metadata(path)

        yield from self.scan_files(paths, read, path_roots=path_roots)

    def readSession(self, path):
        s = self.metadata(path)
        updates = Path(path).parent / "updates.jsonl"
        if updates.is_file():
            pending_role, chunks = None, []

            def flush():
                nonlocal pending_role, chunks
                if chunks:
                    self.message(s, pending_role, "".join(chunks))
                pending_role, chunks = None, []

            def consume_update(record):
                nonlocal pending_role, chunks
                try:
                    u = record.get("params", {}).get("update", {})
                    kind = u.get("sessionUpdate")
                    if kind in ("user_message_chunk", "agent_message_chunk"):
                        role = "user" if kind == "user_message_chunk" else "assistant"
                        if role != pending_role:
                            flush()
                        pending_role = role
                        chunks.append(text_content(u.get("content")))
                    elif kind in ("tool_call", "tool_call_update"):
                        flush()
                        cid = str(u["toolCallId"])
                        meta = u.get("_meta", {}).get("x.ai/tool", {})
                        call = self.find_tool_call(s, cid)
                        if call is None:
                            self.call(s, cid, meta.get("name") or u.get("title", "unknown"), u.get("rawInput", {}))
                            call = s.toolCalls[-1]
                        elif isinstance(u.get("rawInput"), dict):
                            call["arguments"].update(u["rawInput"])
                        if meta.get("name"):
                            call["name"] = meta["name"]
                        if u.get("status") in ("completed", "failed"):
                            output = u.get("rawOutput")
                            if output is None:
                                output = "\n".join(text_content(c.get("content", c)) for c in u.get("content", []) if isinstance(c, dict))
                            self.result(s, cid, output or "Historical tool status: " + u["status"], u["status"] == "failed")
                    elif kind == "turn_completed":
                        flush()
                        s.latestAgentState = "turn_ended"
                    elif kind == "plan":
                        for item in u.get("entries", []):
                            s.possibleTodos.append({"task": item.get("content", ""), "status": "NOT_STARTED" if item.get("status") == "pending" else "UNCERTAIN", "evidence": ["historical Grok plan; requires reconciliation"]})
                    elif kind not in ("agent_thought_chunk", "session_recap", "task_backgrounded", "task_completed", "available_commands_update", "current_mode_update", "config_option_update", "usage_update"):
                        self.unknown(s, kind)
                except (KeyError, TypeError, AttributeError, ValueError):
                    s.parseWarnings.append("unsupported Grok update; partially skipped")
            _, warnings = scan_jsonl(self.checked(updates), consume=consume_update)
            flush()
        else:
            s.parseWarnings.append("Grok updates unavailable; raw chat fallback may omit restore/compaction semantics")

            def consume_history(r):
                kind = r.get("type")
                if kind in ("user", "assistant"):
                    self.message(s, kind, text_content(r.get("content")))
                    for c in r.get("tool_calls") or []:
                        f = c.get("function", c)
                        self.call(s, c.get("id", ""), f.get("name", "unknown"), f.get("arguments", {}))
                elif kind == "tool":
                    self.result(s, r.get("tool_call_id", ""), text_content(r.get("content")))
            _, warnings = scan_jsonl(self.checked(Path(path).parent / "chat_history.jsonl"),
                                     consume=consume_history)
        s.parseWarnings.extend(warnings)
        self.finish(s)
        return s
