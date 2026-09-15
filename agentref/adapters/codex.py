import json

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

    def metadata_needs_refresh(self, row):
        return not request_title(row["title"])

    def overlay_metadata(self, rows):
        titles = self.saved_titles()
        for row in rows:
            row["title"] = titles.get(row["sessionId"], row["title"])
            if row["title"] == row["sessionId"]:
                row["title"] = "未命名会话"

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
            if t in ("task_started", "turn_started"):
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
