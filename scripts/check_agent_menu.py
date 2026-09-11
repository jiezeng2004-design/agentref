"""Check the installed unified provider through Codex app-server, metadata only."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading


def main():
    process = subprocess.Popen([sys.argv[1], "app-server"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding="utf-8")
    inbox = queue.Queue()

    def reader():
        for line in process.stdout:
            try:
                inbox.put(json.loads(line))
            except ValueError:
                pass

    threading.Thread(target=reader, daemon=True).start()
    counter = 0

    def rpc(method, params):
        nonlocal counter
        counter += 1
        process.stdin.write(json.dumps(dict(id=counter, method=method, params=params)) + "\n")
        process.stdin.flush()
        while True:
            response = inbox.get(timeout=50)
            if response.get("id") == counter:
                if "error" in response:
                    raise RuntimeError(str(response["error"]))
                return response["result"]

    try:
        rpc("initialize", {"clientInfo": {"name": "ganetref-check", "version": "1"},
                           "capabilities": {"experimentalApi": True}})
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        thread = rpc("thread/start", {"ephemeral": True, "cwd": str(Path.cwd()),
                     "permissions": ":read-only", "threadSource": "mcp_extension_host"})
        tid = thread["thread"]["id"]
        status = rpc("mcpServerStatus/list", {"threadId": tid})
        server = next(s for s in status["data"] if "ganetref" in s["name"])
        tool = next(t for t in server["tools"].values() if t["name"] == "search_mentions")
        assert tool["_meta"]["openai/extensions"]["mentions/search"] == {}
        # Older CLI builds omit pluginId; Desktop also supports server-name linkage.
        assert (server.get("pluginId") == "ganetref@personal" or
                (server.get("pluginId") is None and server["name"] == "ganetref")), server["name"]
        result = rpc("mcpServer/tool/call", {"threadId": tid, "server": server["name"],
                     "tool": "search_mentions", "arguments": {"query": "", "path": []}})
        assert set(result["structuredContent"]) == {"items"}
        items = result["structuredContent"]["items"]
        assert items and all(i["type"] == "completion" for i in items)
        assert all(set(i) == {"type", "title", "detail", "insertText"} for i in items)
        assert all(i["insertText"].startswith("@") for i in items)
        print(json.dumps({"pluginId": server.get("pluginId"), "server": server["name"],
                          "completionEntries": [i["insertText"] for i in items],
                          "privateContextRead": False, "modelCalled": False,
                          "desktopUIVerified": False}, ensure_ascii=False))
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
