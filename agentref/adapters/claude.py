from .base import BaseAdapter, text_content


class ClaudeAdapter(BaseAdapter):
    agent = "claude"

    def consume(self, s, r):
        if r.get("isSidechain"):
            return
        s.sessionId = r.get("sessionId") or s.sessionId
        s.cwd = r.get("cwd") or s.cwd
        timestamp = r.get("timestamp", "")
        s.createdAt = s.createdAt or timestamp
        s.updatedAt = timestamp or s.updatedAt
        if r.get("version") and r["version"] not in s.versions:
            s.versions.append(r["version"])
        kind = r.get("type")
        if kind == "ai-title":
            s.title = r.get("aiTitle") or s.title
        elif kind in ("user", "assistant"):
            m = r.get("message") or {}
            content = m.get("content", [])
            if not r.get("isMeta"):
                self.message(s, kind, text_content(content))
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        self.call(s, block.get("id"), block.get("name"), block.get("input", {}))
                    elif block.get("type") == "tool_result":
                        self.result(s, block.get("tool_use_id"), text_content(block.get("content")), block.get("is_error", False))
            if m.get("stop_reason") == "end_turn":
                s.latestAgentState = "turn-ended"
            if r.get("isApiErrorMessage"):
                s.errors.append(str(r.get("error", "API error")))
                s.latestAgentState = "interrupted"
        elif kind == "system":
            if r.get("subtype") in ("api_error", "error", "interrupt"):
                s.latestAgentState = "interrupted"
                s.errors.append(str(r.get("content", r.get("subtype"))))
        elif kind not in ("summary", "mode", "file-history-snapshot", "file-history-delta", "last-prompt", "cost-state", "attachment", "atis-latch", "queue-operation", "progress"):
            self.unknown(s, kind)
