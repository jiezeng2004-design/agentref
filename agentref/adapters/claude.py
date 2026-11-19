from .base import BaseAdapter, text_content


_HOST_WRAPPERS = ("system-reminder", "command-name", "command-message",
                  "command-args", "local-command-stdout", "local-command-stderr",
                  "local-command-caveat")


def request_text(content):
    """Drop complete, known host blocks; unknown or mixed markup stays intent."""
    blocks = content if isinstance(content, list) else [content]
    texts = []
    for block in blocks:
        text = text_content(block)
        stripped = text.strip()
        if not stripped:
            continue
        # Only whole blocks qualify. Do not strip tags out of a real request.
        if any(stripped.startswith("<" + tag + ">")
               and stripped.endswith("</" + tag + ">") for tag in _HOST_WRAPPERS):
            continue
        texts.append(text)
    return "\n".join(texts)


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
        if kind == "custom-title":
            title = r.get("customTitle")
            if isinstance(title, str) and title.strip():
                s.title = title
                s._claudeTitleSource = "custom"
        elif kind == "ai-title":
            title = r.get("aiTitle")
            if getattr(s, "_claudeTitleSource", None) != "custom" and isinstance(title, str) and title.strip():
                s.title = title
                s._claudeTitleSource = "ai"
        elif kind in ("user", "assistant"):
            m = r.get("message") or {}
            content = m.get("content", [])
            if not r.get("isMeta"):
                raw = text_content(content)
                if kind == "user":
                    request = request_text(content)
                    derive_title = request and not getattr(s, "_claudeTitleSource", None)
                    if derive_title:
                        # A cached session-id placeholder is not a user title.
                        s.title = ""
                    self.message(s, "user" if request else "context", request or raw)
                    if request:
                        s.messages[-1]["text"] = raw
                    if derive_title:
                        s._claudeTitleSource = "derived"
                else:
                    self.message(s, kind, raw)
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
        elif kind not in ("summary", "mode", "file-history-snapshot", "file-history-delta", "last-prompt", "cost-state", "attachment", "atis-latch", "queue-operation", "progress", "agent-name", "api-request", "api-request-shape", "api-request-blob", "tools-used", "pr-link", "relocated", "bridge-session"):
            self.unknown(s, kind)
