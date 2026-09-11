import json
from pathlib import Path
from ..core import SessionIR
from ..parser import read_jsonl
from .base import text_content
from .snapshot import SnapshotAdapter, timestamp


class GrokAdapter(SnapshotAdapter):
    agent = "grok"

    def metadata(self, path):
        path = self.checked(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        info = data.get("info") or {}
        return SessionIR(agent=self.agent, sessionId=str(info.get("id") or path.parent.name),
                         title=data.get("generated_title") or data.get("session_summary", "")[:120],
                         cwd=info.get("cwd", ""), createdAt=timestamp(data.get("created_at")),
                         updatedAt=timestamp(data.get("updated_at")), sourcePath=str(path))

    def scan_metadata(self):
        # Main sessions only: encoded workspace / session / summary.json.
        paths = (p for root in self.roots for p in sorted(root.glob("*/*/summary.json")))
        yield from self.scan_files(paths, self.metadata)

    def readSession(self, path):
        s = self.metadata(path)
        updates = Path(path).parent / "updates.jsonl"
        if updates.is_file():
            records, _, warnings = read_jsonl(self.checked(updates))
            pending_role, chunks = None, []

            def flush():
                nonlocal pending_role, chunks
                if chunks:
                    self.message(s, pending_role, "".join(chunks))
                pending_role, chunks = None, []

            for record in records:
                try:
                    u = record.get("params", {}).get("update", {})
                    kind = u.get("sessionUpdate")
                    if kind in ("user_message_chunk", "agent_message_chunk"):
                        role = "user" if kind == "user_message_chunk" else "assistant"
                        if role != pending_role:
                            flush()
                        pending_role = role
                        chunks.append(text_content(u.get("content")))
                    elif kind in ("tool_call", "tool_call_update"):
                        flush()
                        cid = str(u["toolCallId"])
                        meta = u.get("_meta", {}).get("x.ai/tool", {})
                        call = next((c for c in reversed(s.toolCalls) if c["id"] == cid), None)
                        if call is None:
                            self.call(s, cid, meta.get("name") or u.get("title", "unknown"), u.get("rawInput", {}))
                            call = s.toolCalls[-1]
                        elif isinstance(u.get("rawInput"), dict):
                            call["arguments"].update(u["rawInput"])
                        if meta.get("name"):
                            call["name"] = meta["name"]
                        if u.get("status") in ("completed", "failed"):
                            output = u.get("rawOutput")
                            if output is None:
                                output = "\n".join(text_content(c.get("content", c)) for c in u.get("content", []) if isinstance(c, dict))
                            self.result(s, cid, output or "Historical tool status: " + u["status"], u["status"] == "failed")
                    elif kind == "turn_completed":
                        flush()
                        s.latestAgentState = "turn_ended"
                    elif kind == "plan":
                        for item in u.get("entries", []):
                            s.possibleTodos.append({"task": item.get("content", ""), "status": "NOT_STARTED" if item.get("status") == "pending" else "UNCERTAIN", "evidence": ["historical Grok plan; requires reconciliation"]})
                    elif kind not in ("agent_thought_chunk", "session_recap", "task_backgrounded", "task_completed", "available_commands_update", "current_mode_update", "config_option_update", "usage_update"):
                        self.unknown(s, kind)
                except (KeyError, TypeError, AttributeError, ValueError):
                    s.parseWarnings.append("unsupported Grok update; partially skipped")
            flush()
        else:
            records, _, warnings = read_jsonl(self.checked(Path(path).parent / "chat_history.jsonl"))
            s.parseWarnings.append("Grok updates unavailable; raw chat fallback may omit restore/compaction semantics")
            for r in records:
                kind = r.get("type")
                if kind in ("user", "assistant"):
                    self.message(s, kind, text_content(r.get("content")))
                    for c in r.get("tool_calls") or []:
                        f = c.get("function", c)
                        self.call(s, c.get("id", ""), f.get("name", "unknown"), f.get("arguments", {}))
                elif kind == "tool":
                    self.result(s, r.get("tool_call_id", ""), text_content(r.get("content")))
        s.parseWarnings.extend(warnings)
        self.finish(s)
        return s
