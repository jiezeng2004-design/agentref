import json
import hashlib
import os
import re
import stat
from pathlib import Path
from ..core import SessionIR
from ..parser import read_jsonl, scan_jsonl

PLAN_PATTERN = re.compile(r"(?i)(next I will|I will |plan to |TODO|接下来|下一步|计划|将实现)")
_ASCII_PLAN_PATTERN = re.compile(r"(next i will|i will |plan to |todo)")
_ASCII_LINE_BREAK_PATTERN = re.compile(r"[\n\r\v\f\x1c-\x1e]")
_LONG_PLAN_TEXT_LIMIT = 256 * 1024
_FILE_OPERATION_TOOLS = frozenset(("Write", "Edit", "MultiEdit"))
_TEST_RUN_PATTERN = re.compile(
    r"(\b(pytest|unittest|vitest|jest)\b|\b(npm|pnpm|yarn|cargo|go)\s+test\b|\bnode\s+--test\b)", re.I)
_EXIT_CODE_PATTERN = re.compile(r"(?:exit(?:ed with)? code|Process exited with code)[:\s]+(-?\d+)", re.I)
_FILE_TOOL_SUCCESS_PATTERN = re.compile(r"(success|updated|created|applied)", re.I)


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
        self._discovered_stats = {}

    def metadata_needs_refresh(self, row):
        return False

    def metadata_overlay(self):
        """Return a stable title overlay map for one metadata query, if any."""
        return None

    def metadata_overlay_signature(self):
        """Return a cheap change signature for any external metadata overlay."""
        return None

    def overlay_title(self, row, overlay=None):
        return row["title"]

    def overlay_metadata(self, rows, overlay=None):
        """Optional metadata-only display policy; never read session bodies."""

    def read_indexed(self, row):
        path = Path(row["sourcePath"])
        if path.is_symlink() or not any(path.resolve().is_relative_to(r) for r in self.roots):
            raise ValueError("source escaped configured session root")
        return self.readSession(path)

    def discoverSessions(self):
        file_stats = {}
        for root in self.roots:
            if not root.is_dir():
                continue
            pending = [root]
            while pending:
                directory = pending.pop()
                try:
                    resolved = directory.resolve()
                    if (not resolved.is_relative_to(root) or directory.is_symlink()
                            or (hasattr(directory, "is_junction") and directory.is_junction())):
                        continue
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            try:
                                if entry.is_symlink():
                                    continue
                                if entry.is_dir(follow_symlinks=False):
                                    path = Path(entry.path)
                                    is_junction = getattr(path, "is_junction", None)
                                    if is_junction is not None and is_junction():
                                        continue
                                    if entry.name != "subagents":
                                        pending.append(path)
                                elif (entry.name.casefold().endswith(".jsonl")
                                      and not entry.name.startswith("agent-")):
                                    source_stat = entry.stat(follow_symlinks=False)
                                    if stat.S_ISREG(source_stat.st_mode):
                                        file_stats[entry.path] = (source_stat.st_mtime_ns, source_stat.st_size)
                            except OSError:
                                continue
                except OSError:
                    continue
        ordered_paths = sorted(file_stats, key=os.path.normcase)
        self._discovered_stats = file_stats
        return [Path(path) for path in ordered_paths]

    def discovered_metadata(self, path):
        cached = self._discovered_stats.get(os.fspath(path))
        if cached is not None:
            return cached
        source_stat = Path(path).stat()
        return source_stat.st_mtime_ns, source_stat.st_size

    def release_discovered_metadata(self):
        self._discovered_stats.clear()

    def readSessionIncrementally(self, path, offset=0):
        return read_jsonl(Path(path), offset)

    def scanSessionIncrementally(self, path, offset, consume, on_warning=None, collect_warnings=True):
        # Preserve older custom adapters that replace the list parser. Built-in
        # Claude/Codex adapters use the streaming parser to avoid a session-sized
        # intermediate record list during indexing and selected-session reads.
        if type(self).readSessionIncrementally is not BaseAdapter.readSessionIncrementally:
            records, end, warnings = self.readSessionIncrementally(path, offset)
            for record in records:
                consume(record)
            if on_warning is not None:
                for warning in warnings:
                    on_warning(warning)
            return end, warnings if collect_warnings else []
        return scan_jsonl(Path(path), offset, consume, on_warning, collect_warnings)

    def readSession(self, path):
        session = SessionIR(agent=self.agent, sessionId=Path(path).stem, sourcePath=str(path))

        def consume(record):
            try:
                self.consume(session, record)
            except (TypeError, ValueError, KeyError, AttributeError):
                session.parseWarnings.append("unsupported record shape; partially skipped")

        _, warnings = self.scanSessionIncrementally(path, 0, consume)
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
            if (len(text) >= _LONG_PLAN_TEXT_LIMIT and text.isascii()
                    and not _ASCII_LINE_BREAK_PATTERN.search(text)):
                if _ASCII_PLAN_PATTERN.search(text.lower()):
                    s.possibleTodos.append({"task": text[:500], "status": "UNCERTAIN",
                                            "evidence": ["natural-language plan; execution not established"]})
                return
            for line in text.splitlines():
                if PLAN_PATTERN.search(line):
                    s.possibleTodos.append({"task": line[:500], "status": "UNCERTAIN", "evidence": ["natural-language plan; execution not established"]})

    def call(self, s, call_id, name, args):
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"raw": args}
        if not isinstance(args, dict):
            args = {"raw": str(args)}
        call = {"id": str(call_id), "name": str(name), "arguments": args, "cwd": s.cwd,
                "output": None, "status": "UNCERTAIN"}
        s.toolCalls.append(call)
        index = getattr(s, "_toolCallById", None)
        if index is not None:
            index[call["id"]] = call
        s.latestAgentState = "incomplete"

    def find_tool_call(self, s, call_id):
        """Return the newest matching call, maintaining the old reverse-search rule."""
        index = getattr(s, "_toolCallById", None)
        if index is None:
            index = {}
            for call in s.toolCalls:
                index[call["id"]] = call
            s._toolCallById = index
        return index.get(str(call_id))

    def result(self, s, call_id, output, failed=False):
        if isinstance(output, list):
            output = text_content(output)
        call = self.find_tool_call(s, call_id)
        if call is not None:
            call["output"] = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
            call["status"] = "FAILED" if failed else "UNCERTAIN"
            return
        s.parseWarnings.append("orphan tool result: " + str(call_id))

    def event_file_operations(self, call):
        """Adapter-owned structured event evidence; never execute source text."""
        return []

    def finish(self, s):
        collect_event_operations = (
            type(self).event_file_operations is not BaseAdapter.event_file_operations
            or "event_file_operations" in self.__dict__
        )
        for call in s.toolCalls:
            name, args, out = call["name"], call["arguments"], call["output"]
            evidence = ["tool call " + call["id"]]
            if out is None:
                evidence.append("no completion result")
                s.latestAgentState = "incomplete"
            else:
                original_out = out
                structured = None
                if out.lstrip().startswith(("{", "[")):
                    try:
                        structured = json.loads(out)
                    except ValueError:
                        pass
                if isinstance(structured, list):
                    out = text_content(structured)
                    call["output"] = out
                if out.startswith(("Script failed", "Script error:", "Error:", "Error executing tool")):
                    call["status"] = "FAILED"
                exit_code = structured.get("exit_code") if isinstance(structured, dict) else None
                if exit_code is None:
                    code = _EXIT_CODE_PATTERN.search(original_out)
                    if code:
                        exit_code = int(code[1])
                if exit_code is not None:
                    call["status"] = "COMPLETED" if exit_code == 0 and call["status"] != "FAILED" else "FAILED"
                    evidence.append(f"historical exit code {exit_code}")
                elif call["status"] != "FAILED" and name in ("Write", "Edit", "MultiEdit", "apply_patch", "functions.apply_patch"):
                    if _FILE_TOOL_SUCCESS_PATTERN.search(out):
                        call["status"] = "COMPLETED"
                        evidence.append("historical file tool success")
                if call["status"] == "FAILED":
                    s.errors.append(out[:2000])
            call["evidence"] = evidence
            command = args.get("command", args.get("cmd"))
            if command:
                command_text = str(command)
                item = {"task": command_text, "cwd": args.get("workdir", args.get("cwd", call.get("cwd", ""))), "status": call["status"], "evidence": evidence, "output": out}
                s.commands.append(item)
                if _TEST_RUN_PATTERN.search(command_text):
                    s.testRuns.append(item.copy())
            if name in _FILE_OPERATION_TOOLS or "apply_patch" in name:
                path = args.get("file_path", args.get("path"))
                paths = [path] if isinstance(path, str) and name in _FILE_OPERATION_TOOLS else []
                is_patch_tool = "apply_patch" in name
                if is_patch_tool:
                    paths += re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", str(args.get("raw", args.get("patch", ""))), re.M)
                for path in paths:
                    operation = {"path": path, "cwd": call.get("cwd", ""), "task": name + " " + path, "status": call["status"], "evidence": evidence}
                    if name == "Write" and isinstance(args.get("content"), str):
                        operation["expectedSha256"] = hashlib.sha256(args["content"].encode()).hexdigest()
                    if is_patch_tool:
                        patch = str(args.get("raw", args.get("patch", "")))
                        marker = "*** Add File: " + path + "\n"
                        if marker in patch:
                            body = patch.split(marker, 1)[1].split("*** ", 1)[0]
                            lines = body.splitlines()
                            if lines and all(line.startswith("+") for line in lines):
                                operation["expectedSha256"] = hashlib.sha256(("\n".join(line[1:] for line in lines) + "\n").encode()).hexdigest()
                    s.fileOperations.append(operation)
            if collect_event_operations:
                s.fileOperations.extend(self.event_file_operations(call))
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
        if hasattr(s, "_toolCallById"):
            del s._toolCallById

    def unknown(self, s, kind):
        if str(kind) not in s.unknownTypes:
            s.unknownTypes.append(str(kind))
