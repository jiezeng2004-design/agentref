import json
import hashlib
import re
from pathlib import Path
from ..core import SessionIR
from ..parser import read_jsonl


def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text_content(x) for x in value if isinstance(x, (str, dict)))
    if isinstance(value, dict):
        return str(value.get("text", ""))
    return ""


class BaseAdapter:
    index_mode = "incremental"

    def __init__(self, roots):
        self.roots = [Path(p).expanduser().resolve() for p in roots]

    def metadata_needs_refresh(self, row):
        return False

    def overlay_metadata(self, rows):
        """Optional metadata-only display policy; never read session bodies."""

    def read_indexed(self, row):
        path = Path(row["sourcePath"])
        if path.is_symlink() or not any(path.resolve().is_relative_to(r) for r in self.roots):
            raise ValueError("source escaped configured session root")
        return self.readSession(path)

    def discoverSessions(self):
        files = set()
        for root in self.roots:
            if not root.is_dir():
                continue
            for p in root.rglob("*.jsonl"):
                if "subagents" in p.parts or p.name.startswith("agent-"):
                    continue
                try:
                    resolved = p.resolve()
                    if resolved.is_relative_to(root) and not p.is_symlink():
                        files.add(resolved)
                except OSError:
                    continue
        return sorted(files)

    def readSessionIncrementally(self, path, offset=0):
        return read_jsonl(Path(path), offset)

    def readSession(self, path):
        records, _, warnings = self.readSessionIncrementally(path)
        session = SessionIR(agent=self.agent, sessionId=Path(path).stem, sourcePath=str(path))
        for record in records:
            try:
                self.consume(session, record)
            except (TypeError, ValueError, KeyError, AttributeError):
                session.parseWarnings.append("unsupported record shape; partially skipped")
        session.parseWarnings.extend(warnings)
        self.finish(session)
        return session

    def getSessionMetadata(self, path):
        s = self.readSession(path)
        return {k: getattr(s, k) for k in ("agent", "sessionId", "title", "cwd", "createdAt", "updatedAt", "sourcePath", "latestAgentState")}

    def extractWorkspace(self, session):
        return session.cwd

    def getSessionStatus(self, session):
        return session.latestAgentState

    def message(self, s, role, text):
        if not text:
            return
        s.messages.append({"role": role, "text": text})
        if role == "user":
            s.originalGoal = s.originalGoal or text
            s.latestUserRequest = text
            s.title = s.title or text.splitlines()[0][:120]
            s.latestAgentState = "incomplete"
        elif role == "assistant":
            for line in text.splitlines():
                if re.search(r"(?i)(next I will|I will |plan to |TODO|接下来|下一步|计划|将实现)", line):
                    s.possibleTodos.append({"task": line[:500], "status": "UNCERTAIN", "evidence": ["natural-language plan; execution not established"]})

    def call(self, s, call_id, name, args):
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"raw": args}
        if not isinstance(args, dict):
            args = {"raw": str(args)}
        s.toolCalls.append({"id": str(call_id), "name": str(name), "arguments": args, "cwd": s.cwd, "output": None, "status": "UNCERTAIN"})
        s.latestAgentState = "incomplete"

    def result(self, s, call_id, output, failed=False):
        if isinstance(output, list):
            output = text_content(output)
        for call in reversed(s.toolCalls):
            if call["id"] == str(call_id):
                call["output"] = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
                call["status"] = "FAILED" if failed else "UNCERTAIN"
                return
        s.parseWarnings.append("orphan tool result: " + str(call_id))

    def finish(self, s):
        for call in s.toolCalls:
            name, args, out = call["name"], call["arguments"], call["output"]
            evidence = ["tool call " + call["id"]]
            if out is None:
                evidence.append("no completion result")
                s.latestAgentState = "incomplete"
            else:
                code = re.search(r"(?i)(?:exit(?:ed with)? code|Process exited with code)[:\s]+(-?\d+)", out)
                try:
                    structured = json.loads(out)
                except ValueError:
                    structured = None
                if isinstance(structured, list):
                    out = text_content(structured)
                    call["output"] = out
                if out.startswith(("Script failed", "Script error:", "Error:", "Error executing tool")):
                    call["status"] = "FAILED"
                exit_code = structured.get("exit_code") if isinstance(structured, dict) else None
                if exit_code is None and code:
                    exit_code = int(code[1])
                if exit_code is not None:
                    call["status"] = "COMPLETED" if exit_code == 0 and call["status"] != "FAILED" else "FAILED"
                    evidence.append(f"historical exit code {exit_code}")
                elif call["status"] != "FAILED" and name in ("Write", "Edit", "MultiEdit", "apply_patch", "functions.apply_patch"):
                    if re.search(r"(?i)(success|updated|created|applied)", out):
                        call["status"] = "COMPLETED"
                        evidence.append("historical file tool success")
                if call["status"] == "FAILED":
                    s.errors.append(out[:2000])
            call["evidence"] = evidence
            command = args.get("command", args.get("cmd"))
            if command:
                item = {"task": str(command), "cwd": args.get("workdir", args.get("cwd", call.get("cwd", ""))), "status": call["status"], "evidence": evidence, "output": out}
                s.commands.append(item)
                if re.search(r"(?i)(\b(pytest|unittest|vitest|jest)\b|\b(npm|pnpm|yarn|cargo|go)\s+test\b|\bnode\s+--test\b)", str(command)):
                    s.testRuns.append(item.copy())
            path = args.get("file_path", args.get("path"))
            paths = [path] if isinstance(path, str) and name in ("Write", "Edit", "MultiEdit") else []
            if "apply_patch" in name:
                paths += re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", str(args.get("raw", args.get("patch", ""))), re.M)
            for path in paths:
                operation = {"path": path, "cwd": call.get("cwd", ""), "task": name + " " + path, "status": call["status"], "evidence": evidence}
                if name == "Write" and isinstance(args.get("content"), str):
                    operation["expectedSha256"] = hashlib.sha256(args["content"].encode()).hexdigest()
                if "apply_patch" in name:
                    patch = str(args.get("raw", args.get("patch", "")))
                    marker = "*** Add File: " + path + "\n"
                    if marker in patch:
                        body = patch.split(marker, 1)[1].split("*** ", 1)[0]
                        lines = body.splitlines()
                        if lines and all(line.startswith("+") for line in lines):
                            operation["expectedSha256"] = hashlib.sha256(("\n".join(line[1:] for line in lines) + "\n").encode()).hexdigest()
                s.fileOperations.append(operation)
            if name.endswith("update_plan") or name == "TodoWrite":
                for todo in args.get("plan", args.get("todos", [])):
                    if isinstance(todo, dict):
                        status = todo.get("status")
                        s.possibleTodos.append({"task": str(todo.get("step", todo.get("content", "unknown"))), "status": "NOT_STARTED" if status == "pending" else "UNCERTAIN", "planStatus": status if call["status"] != "FAILED" and out is not None else "unconfirmed", "evidence": ["agent plan status: " + str(status) + "; requires reconciliation"]})
        if not s.title:
            s.title = s.sessionId
        # Later structured plan updates supersede older snapshots of the same task.
        latest_todos = {}
        for todo in s.possibleTodos:
            latest_todos[todo["task"]] = todo
        s.possibleTodos = list(latest_todos.values())
        if s.unknownTypes:
            s.parseWarnings.append("unknown record types: " + ", ".join(s.unknownTypes[:20]))
        if any("incomplete trailing" in w for w in s.parseWarnings):
            s.latestAgentState = "incomplete"

    def unknown(self, s, kind):
        if str(kind) not in s.unknownTypes:
            s.unknownTypes.append(str(kind))
