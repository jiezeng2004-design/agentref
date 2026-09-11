"""AgentRef entry picker: plugin metadata only, never opens a session index."""
import json
import shutil
import subprocess

from .mcp import Server, PROTOCOLS, validate_arguments
from . import __version__


AGENTS = {
    "claude": "Claude Code",
    "grok": "Grok",
    "opencode": "OpenCode",
    "antigravity": "Antigravity",
    "dsh": "DSH · DeepSeek Harness",
}


def installed_agents():
    executable = shutil.which("codex")
    if not executable:
        raise ValueError("Codex CLI is unavailable")
    result = subprocess.run(
        [executable, "plugin", "list", "--json", "--marketplace", "personal"],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    if result.returncode:
        raise ValueError("Plugin inventory unavailable")
    inventory = json.loads(result.stdout)
    return [name for name in AGENTS if any(
        item.get("name") == name and item.get("pluginId") == name + "@personal"
        and item.get("installed") is True and item.get("enabled") is True
        for item in inventory.get("installed", [])
    )]


class AgentMenuServer(Server):
    def __init__(self, catalog=installed_agents):
        # Reuse the JSON-RPC transport only. No Index, adapters or transcript access.
        self.catalog = catalog

    def dispatch(self, method, p):
        if not isinstance(p, dict):
            raise ValueError("invalid params")
        if method == "initialize":
            version = p.get("protocolVersion")
            return {"protocolVersion": version if version in PROTOCOLS else PROTOCOLS[0],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "ganetref", "version": __version__},
                    "instructions": "Choose an agent, then use its @ mention and Tab to select a session. Never select a session automatically."}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [{
                "name": "search_mentions", "title": "选择 AgentRef agent",
                "description": "List installed and enabled AgentRef agent entries. Choosing an entry inserts @agent; use its Tab menu to select a session. No session content is read.",
                "inputSchema": {"type": "object", "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "array", "items": {"type": "string"}},
                }, "additionalProperties": False},
                "annotations": {"readOnlyHint": True, "openWorldHint": False},
                "_meta": {"openai/extensions": {"mentions/search": {}},
                          "connector_name": "ganetref"},
            }]}
        if method == "tools/call":
            try:
                tool = self.dispatch("tools/list", {})["tools"][0]
                if p.get("name") != tool["name"]:
                    raise ValueError("unknown tool")
                args = p.get("arguments", {})
                validate_arguments(args, tool["inputSchema"])
                query = args.get("query", "").strip().lstrip("@").casefold()
                # This provider has one level; reject fabricated nested navigation.
                if args.get("path"):
                    raise ValueError("unsupported path")
                names = self.catalog()
                items = [{"type": "completion", "title": AGENTS[name],
                          "detail": "选择 @" + name + "，再按 Tab 展开会话",
                          "insertText": "@" + name}
                         for name in AGENTS if name in names
                         and (not query or query in (name + " " + AGENTS[name]).casefold())]
                content = {"items": items}
                return {"structuredContent": content,
                        "content": [{"type": "text", "text": json.dumps(content, ensure_ascii=False)}]}
            except (ValueError, TypeError, AttributeError, OSError, subprocess.SubprocessError):
                return {"isError": True, "content": [{"type": "text", "text":
                    "无法读取 agent 入口，或查询无效。请检查 Codex 插件是否已安装并启用，然后重试。未读取会话正文。"}]}
        raise LookupError("method not found")
