"""Metadata-only native mention labels shared by both desktop integrations."""
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import unquote, urlsplit
import unicodedata


def session_time(row):
    for key in ("updatedAt", "createdAt"):
        try:
            raw = row.get(key)
            if not isinstance(raw, str):
                continue
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        except (TypeError, ValueError):
            pass
    try:
        return datetime.fromtimestamp(row.get("mtime", 0) / 1_000_000_000, timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return datetime.fromtimestamp(0, timezone.utc)


def short_text(value, limit=36):
    text = " ".join("".join(c for c in str(value) if not unicodedata.category(c).startswith("C")).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def agent_display_name(row):
    agent = row.get("agent") or "agentref"
    return {"claude": "Claude", "codex": "Codex", "grok": "Grok",
                  "opencode": "OpenCode", "antigravity": "Antigravity", "dsh": "DSH"}.get(agent, "AgentRef")


def is_unnamed(row):
    title = row.get("title") or ""
    return short_text(title) in ("", "未命名会话", f"未命名 {agent_display_name(row)} 会话") or title == row.get("sessionId")


def label(row, rank=None):
    agent = row.get("agent") or "agentref"
    agent_name = agent_display_name(row)
    if is_unnamed(row):
        # Use metadata only; preserve the identity suffix even for long projects.
        project = str(row.get("cwd") or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        project = short_text(project, 16) or agent_name
        when = session_time(row)
        stamp = when.astimezone().strftime("%m-%d %H:%M") if when.timestamp() else "时间未知"
        identity = row.get("ref") or agent + ":" + str(row.get("sessionId") or "")
        suffix = sha256(identity.encode("utf-8")).hexdigest()[:8]
        return f"{project} · {stamp} · {suffix}"
    title = short_text(row["title"])
    when = session_time(row)
    stamp = when.astimezone().strftime("%m-%d %H:%M") if when.timestamp() else "时间未知"
    return f"{title} · {stamp}" if when.timestamp() else title


def resource_uri(row, rank=None):
    # Claude ranks/displays the URI rather than the MCP resource name. Keep URI
    # lengths uniform and rank first. The exact ref survives later reordering.
    prefix = f"{rank:04d}/" if rank is not None else ""
    return "agentref://session/" + prefix + row["ref"]


def resource_ref(uri):
    parsed = urlsplit(uri)
    if parsed.scheme != "agentref" or parsed.netloc != "session" or not parsed.path.startswith("/"):
        raise ValueError("unknown resource URI")
    path = unquote(parsed.path[1:])
    parts = path.split("/")
    if len(parts) == 2 and len(parts[0]) >= 4 and parts[0].isdigit():
        ref = parts[1]
    else:
        ref = path
    if "/" in ref or not ref:
        raise ValueError("invalid resource reference")
    return ref
