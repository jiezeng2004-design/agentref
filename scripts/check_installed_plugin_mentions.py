"""Read fresh Desktop app-server plugin linkage; never read session resources."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading


def main():
    executable = sys.argv[1]
    proc = subprocess.Popen([executable, "app-server"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8")
    inbox = queue.Queue()

    def reader():
        for line in proc.stdout:
            try:
                inbox.put(json.loads(line))
            except ValueError:
                pass
    threading.Thread(target=reader, daemon=True).start()
    counter = 0

    def rpc(method, params):
        nonlocal counter
        counter += 1
        proc.stdin.write(json.dumps(dict(id=counter, method=method, params=params)) + "\n")
        proc.stdin.flush()
        while True:
            result = inbox.get(timeout=50)
            if result.get("id") == counter:
                if "error" in result:
                    raise RuntimeError(str(result["error"]))
                return result["result"]
    try:
        rpc("initialize", {"clientInfo": {"name": "agentref-installed-menu-check", "version": "1"},
                           "capabilities": {"experimentalApi": True}})
        proc.stdin.write('{"method":"initialized"}\n'); proc.stdin.flush()
        started = rpc("thread/start", {"ephemeral": True, "cwd": str(Path.cwd()),
                      "permissions": ":read-only", "threadSource": "mcp_extension_host"})
        tid = started["thread"]["id"]
        status = rpc("mcpServerStatus/list", {"threadId": tid})
        reports = []
        for server in status["data"]:
            if not any(n in server["name"] for n in ("dsh", "claude")):
                continue
            searches = [t for t in server.get("tools", {}).values()
                        if t.get("_meta", {}).get("openai/extensions", {}).get("mentions/search") is not None]
            reports.append(dict(server=server["name"], pluginId=server.get("pluginId"),
                                pluginIdPresent="pluginId" in server,
                                authStatus=server.get("authStatus"), searches=[t["name"] for t in searches]))
        print(json.dumps({"desktopBinary": executable, "pluginMentionProviders": reports,
                          "privateContextRead": False}, ensure_ascii=False))
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.terminate(); proc.wait(timeout=10)


if __name__ == "__main__":
    main()
