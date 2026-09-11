"""Isolated installed Codex app-server acceptance; no model or private history."""
import json
import argparse
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
from contextlib import nullcontext


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=["claude", "grok", "opencode", "antigravity", "dsh"], default="claude")
    parser.add_argument("--source-error", action="store_true", help="Add one corrupt synthetic source and verify diagnostics survive the host")
    options = parser.parse_args()
    agent = options.agent
    repo = Path(__file__).resolve().parents[1]
    artifacts = repo / "demo-artifacts"
    artifacts.mkdir(exist_ok=True)
    with nullcontext(tempfile.mkdtemp(prefix="native-mentions-", dir=artifacts)) as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        exe = repo / ".venv/Scripts/agentref.exe"
        source = root / "source"
        source.mkdir()
        if agent == "claude":
            shutil.copyfile(repo / "tests/fixtures/claude-normal.jsonl", source / "claude-normal.jsonl")
        else:
            import sys
            sys.path.insert(0, str(repo / "tests"))
            from extra_fixtures import BUILDERS
            if agent == "dsh":
                from dsh_fixtures import dsh
                dsh(source)
            else:
                BUILDERS[agent](source)
        if options.source_error:
            if agent == "claude":
                (source / "broken.jsonl").write_bytes(b'{"broken":')
            elif agent == "grok":
                broken = source / "broken" / "broken"
                broken.mkdir(parents=True)
                (broken / "summary.json").write_bytes(b'{"broken":')
            elif agent == "antigravity":
                (source / "broken.db").write_bytes(b'corrupt synthetic database')
            else:
                raise ValueError("use claude, grok or antigravity for an isolated extra corrupt source")
        args = ["--data-dir", str(root / "index"), "--" + agent + "-root", str(source), "mcp", "--agent", agent]
        config = "[features]\nplugins = false\n[mcp_servers." + agent + "]\ncommand = " + json.dumps(str(exe)) + "\nargs = " + json.dumps(args) + "\n"
        (home / "config.toml").write_text(config, encoding="utf-8")
        env = dict(os.environ, CODEX_HOME=str(home))
        with (root / "stderr.log").open("w", encoding="utf-8") as errors:
            process = subprocess.Popen([shutil.which("codex"), "app-server"], env=env, cwd=root,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                       text=True, encoding="utf-8")
            inbox = queue.Queue()

            def reader():
                for line in process.stdout:
                    try:
                        inbox.put(json.loads(line))
                    except ValueError:
                        continue

            threading.Thread(target=reader, daemon=True).start()
            counter = 0

            def rpc(method, params):
                nonlocal counter
                counter += 1
                process.stdin.write(json.dumps({"id": counter, "method": method, "params": params}) + "\n")
                process.stdin.flush()
                while True:
                    message = inbox.get(timeout=45)
                    if message.get("id") == counter:
                        if "error" in message:
                            raise RuntimeError(json.dumps(message["error"]))
                        return message["result"]

            try:
                rpc("initialize", {"clientInfo": {"name": "agentref-mention-check", "version": "1"},
                                   "capabilities": {"experimentalApi": True}})
                process.stdin.write('{"method":"initialized"}\n')
                process.stdin.flush()
                thread = rpc("thread/start", {"ephemeral": True, "cwd": str(root),
                                              "permissions": ":read-only", "threadSource": "mcp_extension_host"})
                tid = thread["thread"]["id"]
                inventory = rpc("mcpServerStatus/list", {"threadId": tid})
                server = next(s for s in inventory["data"] if s["name"] == agent)
                tool = next(t for t in server["tools"].values() if t["name"] == "search_mentions")
                assert tool["_meta"]["openai/extensions"]["mentions/search"] == {}
                result = rpc("mcpServer/tool/call", {"threadId": tid, "server": agent,
                             "tool": "search_mentions", "arguments": {"query": "", "path": []}})
                items = result["structuredContent"]["items"]
                assert set(result["structuredContent"]) == {"items"}, "Desktop rejects unknown keys"
                assert items and all(i["type"] == "resource" for i in items)
                if options.source_error:
                    assert result["_meta"]["indexIncomplete"]
                    assert result["_meta"]["warnings"]
                chosen = next(item for item in items if item["title"] != "broken")
                selected = rpc("mcpServer/resource/read", {"threadId": tid, "server": agent,
                                                            "uri": chosen["resourceUri"]})
                assert "Original Goal" in selected["contents"][0]["text"]
                if options.source_error:
                    assert "index refresh incomplete" in selected["contents"][0]["text"]
                print(json.dumps({"agent": agent, "installedHost": "codex app-server", "nativeMetadataPreserved": True,
                                  "candidateCount": len(items), "selectedResourceRead": True,
                                  "privateHistoryUsed": False, "modelCalled": False,
                                  "sourceErrorDiagnosticsVerified": options.source_error}))
            finally:
                process.stdin.close()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
