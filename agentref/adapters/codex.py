import hashlib
import json
from pathlib import Path

from .base import BaseAdapter, text_content


def request_title(text):
    """Ignore host-injected user messages when deriving a fallback title."""
    if "## My request:" in text:
        text = text.rsplit("## My request:", 1)[1]
    text = text.strip()
    if not text or text.startswith(("<", "# AGENTS.md", "# Files", "## Referenced chats", "You are ", "This is an authorized interrupted")):
        return ""
    return text.splitlines()[0][:120]


class CodexAdapter(BaseAdapter):
    agent = "codex"

    def _patch_event_index(self, session):
        index = getattr(session, "_codexPatchEventsByKey", None)
        if index is None:
            index = {}
            for call in session.toolCalls:
                event = call.get("codexPatchEvent")
                if event:
                    index[(event["callId"], event["turnId"])] = call
            session._codexPatchEventsByKey = index
        return index

    def patch_event(self, s, payload):
        """Only the observed add-file shape is established; other shapes warn."""
        call_id, turn_id = payload.get("call_id"), payload.get("turn_id", "")
        success, status, changes = payload.get("success"), payload.get("status"), payload.get("changes")
        if (not isinstance(call_id, str) or not call_id or not isinstance(turn_id, str)
                or type(success) is not bool or status != ("completed" if success else "failed")
                or not isinstance(changes, dict)):
            self.unknown(s, "event_msg:patch_apply_end:unsupported-shape")
            return
        operations = []
        for path, change in changes.items():
            if (not isinstance(path, str) or not path or "\x00" in path
                    or not isinstance(change, dict) or change.get("type") != "add"
                    or not isinstance(change.get("content"), str)):
                self.unknown(s, "event_msg:patch_apply_end:unsupported-change")
                continue
            operation = {"path": path, "changeType": "add"}
            if success:
                operation["expectedSha256"] = hashlib.sha256(change["content"].encode("utf-8")).hexdigest()
            operations.append(operation)
        evidence = {"callId": call_id, "turnId": turn_id, "success": success, "operations": operations}
        index = self._patch_event_index(s)
        prior_call = index.get((call_id, turn_id))
        if prior_call is not None:
            if prior_call["codexPatchEvent"] != evidence:
                prior_call["status"] = "UNCERTAIN"
                prior_call["output"] = "Conflicting historical patch events; completion not established"
                prior_call["patchEventConflict"] = True
                self.unknown(s, "event_msg:patch_apply_end:conflicting-duplicate")
            return
        previous_state = s.latestAgentState
        identity = "patch-event:" + json.dumps([turn_id, call_id], ensure_ascii=False)
        self.call(s, identity, "codex.patch_apply_end", {"call_id": call_id, "turn_id": turn_id})
        call = s.toolCalls[-1]
        call["codexPatchEvent"] = evidence
        index[(call_id, turn_id)] = call
        call["status"] = "COMPLETED" if success else "FAILED"
        call["output"] = "Historical patch_apply_end reported " + status + "; not current feature acceptance"
        # This sideband event is not a new task or a standalone resumed tool call.
        s.latestAgentState = previous_state

    def event_file_operations(self, call):
        event = call.get("codexPatchEvent")
        if not event:
            return []
        result = []
        for change in event["operations"]:
            operation = {"path": change["path"], "cwd": call.get("cwd", ""),
                         "task": "Codex patch add " + change["path"], "status": call["status"],
                         "evidence": [*call["evidence"], "structured patch_apply_end add-file event"],
                         "sourceEvent": "patch_apply_end", "sourceCallId": event["callId"]}
            if call["status"] == "COMPLETED" and not call.get("patchEventConflict"):
                operation["expectedSha256"] = change["expectedSha256"]
            result.append(operation)
        return result

    def finish(self, s):
        super().finish(s)
        # A direct apply_patch response and its sideband event may describe the
        # same operation. Collapse only matching call/path/cwd evidence; a
        # contradictory status/hash stays uncertain instead of inventing success.
        remove = set()
        patch_calls = {call["id"] for call in s.toolCalls
                       if "apply_patch" in call["name"] and not call.get("codexPatchEvent")}
        direct_operations = {}
        for index, operation in enumerate(s.fileOperations):
            if operation.get("sourceEvent"):
                continue
            identity = (repr(operation.get("path")), repr(operation.get("cwd")))
            indexed_call_ids = set()
            for evidence in operation.get("evidence", []):
                if not isinstance(evidence, str) or not evidence.startswith("tool call "):
                    continue
                call_id = evidence[len("tool call "):]
                if call_id in patch_calls and call_id not in indexed_call_ids:
                    direct_operations.setdefault((call_id, *identity), []).append((index, operation))
                    indexed_call_ids.add(call_id)
        for event_index, event in enumerate(s.fileOperations):
            if event.get("sourceEvent") != "patch_apply_end" or event["sourceCallId"] not in patch_calls:
                continue
            key = (event["sourceCallId"], repr(event["path"]), repr(event.get("cwd")))
            for index, original in direct_operations.get(key, ()):
                if (original.get("sourceEvent") or original.get("path") != event["path"]
                        or original.get("cwd") != event.get("cwd")
                        or "tool call " + event["sourceCallId"] not in original["evidence"]):
                    continue
                compatible = (original["status"] == event["status"]
                              and (not original.get("expectedSha256")
                                   or original.get("expectedSha256") == event.get("expectedSha256")))
                if compatible:
                    original["evidence"].extend(event["evidence"])
                    if event.get("expectedSha256"):
                        original["expectedSha256"] = event["expectedSha256"]
                    remove.add(event_index)
                else:
                    self.unknown(s, "event_msg:patch_apply_end:conflicting-tool-result")
                    s.parseWarnings.append("patch event conflicts with tool evidence; completion not established")
                    for item in (original, event):
                        item["status"] = "UNCERTAIN"
                        item.pop("expectedSha256", None)
        s.fileOperations = [item for index, item in enumerate(s.fileOperations) if index not in remove]
        if hasattr(s, "_codexPatchEventsByKey"):
            del s._codexPatchEventsByKey

    def metadata_needs_refresh(self, row):
        return not request_title(row["title"])

    def metadata_overlay(self):
        return self.saved_titles()

    def metadata_overlay_signature(self):
        signatures = []
        homes = {root.parent for root in self.roots if root.name in ("sessions", "archived_sessions")}
        for home in sorted(homes):
            path = home / "session_index.jsonl"
            if path.is_symlink():
                signatures.append((str(path), "linked"))
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                signatures.append((str(path), None))
            except OSError as exc:
                signatures.append((str(path), "unavailable", exc.errno))
            else:
                signatures.append((str(path), stat.st_dev, stat.st_ino,
                                   stat.st_mtime_ns, stat.st_size))
        return tuple(signatures)

    def overlay_title(self, row, title_overlay=None):
        titles = self.saved_titles() if title_overlay is None else title_overlay
        title = titles.get(row["sessionId"], row["title"])
        return "未命名会话" if title == row["sessionId"] else title

    def overlay_metadata(self, rows, title_overlay=None):
        titles = self.saved_titles() if title_overlay is None else title_overlay
        for row in rows:
            row["title"] = self.overlay_title(row, titles)

    def saved_titles(self):
        titles = {}
        for home in {r.parent for r in self.roots if r.name in ("sessions", "archived_sessions")}:
            path = home / "session_index.jsonl"
            if path.is_symlink():
                continue
            try:
                with path.open(encoding="utf-8") as stream:
                    for line in stream:
                        try:
                            item = json.loads(line)
                            if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("thread_name"), str):
                                name = item["thread_name"].strip()
                                if name:
                                    titles[item["id"]] = name
                        except (ValueError, TypeError):
                            continue
            except (OSError, UnicodeError):
                continue
        return titles

    def message(self, s, role, text):
        old_title = s.title
        super().message(s, role, text)
        if role == "user":
            s.title = old_title if old_title and old_title != s.sessionId else request_title(text)

    def consume(self, s, r):
        kind = r.get("type")
        p = r.get("payload") or {}
        timestamp = r.get("timestamp", "")
        s.createdAt = s.createdAt or timestamp
        s.updatedAt = timestamp or s.updatedAt
        if kind == "session_meta":
            if not getattr(s, "_metadata_seen", False):
                s.sessionId = p.get("id") or p.get("session_id") or s.sessionId
                s.cwd = p.get("cwd") or s.cwd
                s._metadata_seen = True
            if p.get("cli_version"):
                s.versions.append(p["cli_version"])
        elif kind == "turn_context":
            s.cwd = p.get("cwd") or s.cwd
        elif kind == "response_item":
            t = p.get("type")
            if t == "message":
                if p.get("role") in ("user", "assistant"):
                    self.message(s, p["role"], text_content(p.get("content")))
            elif t in ("function_call", "custom_tool_call"):
                self.call(s, p.get("call_id"), p.get("name"), p.get("arguments", p.get("input", {})))
            elif t in ("function_call_output", "custom_tool_call_output"):
                self.result(s, p.get("call_id"), p.get("output", ""))
            elif t != "reasoning":
                self.unknown(s, "response_item:" + str(t))
        elif kind == "event_msg":
            t = p.get("type")
            if t == "patch_apply_end":
                self.patch_event(s, p)
            elif t in ("task_started", "turn_started"):
                s.latestAgentState = "incomplete"
            elif t in ("task_complete", "turn_complete"):
                s.latestAgentState = "turn-ended"
            elif t in ("turn_aborted", "error", "stream_error"):
                s.latestAgentState = "interrupted"
                s.errors.append(str(p.get("message", p.get("reason", t))))
            elif t not in ("token_count", "agent_message", "user_message", "agent_reasoning", "item_completed", "item_started"):
                self.unknown(s, "event_msg:" + str(t))
        elif kind not in ("compacted", "world_state", "token_usage_record"):
            self.unknown(s, kind)
