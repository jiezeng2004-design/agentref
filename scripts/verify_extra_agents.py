"""Check installed MCP entrypoints using metadata only; never selects private text."""
import json
import subprocess
import time
from pathlib import Path


def main():
    results = []
    for name in ("claude", "grok", "opencode", "antigravity"):
        plugin = Path.home() / "plugins" / name
        entry = json.loads((plugin / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"][name]
        requests = [
            {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}}},
            {"id": 2, "method": "tools/list", "params": {}},
            {"id": 3, "method": "tools/call", "params": {"name": "search_mentions", "arguments": {"query": "", "path": []}}},
            {"id": 4, "method": "completion/complete", "params": {"ref": {"type": "ref/resource", "uri": "agentref://session/{session}"}, "argument": {"name": "session", "value": ""}}},
        ]
        text = "".join(json.dumps({"jsonrpc": "2.0", **r}) + "\n" for r in requests)
        started = time.monotonic()
        result = subprocess.run([entry["command"], *entry["args"]], input=text, capture_output=True,
                                text=True, encoding="utf-8", timeout=30)
        assert result.returncode == 0, name + " MCP failed"
        replies = {r["id"]: r for r in map(json.loads, result.stdout.splitlines())}
        assert all("error" not in r for r in replies.values())
        tools = replies[2]["result"]["tools"]
        mention = next(t for t in tools if t["name"] == "search_mentions")
        assert mention["_meta"]["openai/extensions"]["mentions/search"] == {}
        inventory = replies[3]["result"]["structuredContent"]
        assert set(inventory) == {"items"}, "Desktop rejects unknown keys"
        metadata = replies[3]["result"]["_meta"]
        items = inventory["items"]
        assert all(i["resourceUri"].startswith("agentref://session/" + name + ":") for i in items)
        completion = replies[4]["result"]["completion"]
        assert completion["total"] == metadata["total"]
        results.append({"agent": name, "candidateCount": len(items), "totalSessions": completion["total"],
                        "indexIncomplete": metadata.get("indexIncomplete", False), "nativeMentionDeclaration": True,
                        "claudeCompletion": True, "seconds": round(time.monotonic() - started, 3),
                        "privateContextSelected": False, "modelCalled": False})
    print(json.dumps(results, ensure_ascii=False))
    path = Path(__file__).resolve().parents[1] / "demo-artifacts/extra-agents-installed-check.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
