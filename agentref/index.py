import hashlib
import os
import sqlite3
from pathlib import Path
from .core import SessionIR
from .mentions import session_time
from .adapters.registry import default_adapters


def fingerprint(path, end):
    with path.open("rb") as f:
        head = f.read(min(end, 4096))
        f.seek(max(0, end - 4096))
        tail = f.read(min(end, 4096))
    return hashlib.sha256(head + tail).hexdigest()


class Index:
    def __init__(self, data_dir=None, adapters=None):
        self.adapters = {a.agent: a for a in (adapters if adapters is not None else default_adapters())}
        self.home = Path(data_dir or os.environ.get("AGENTREF_HOME", Path.home() / ".agentref")).expanduser().resolve()
        for adapter in self.adapters.values():
            if adapter.index_mode not in ("incremental", "snapshot"):
                raise ValueError("unsupported adapter index mode")
            if any(self.home.is_relative_to(r) for r in adapter.roots):
                raise ValueError("AgentRef index must not be inside foreign session roots")
        self.home.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.home / "index.sqlite3", timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            ref TEXT PRIMARY KEY, agent TEXT, sessionId TEXT, title TEXT, cwd TEXT,
            createdAt TEXT, updatedAt TEXT, sourcePath TEXT UNIQUE,
            latestAgentState TEXT, mtime INTEGER, size INTEGER, offset INTEGER,
            fingerprint TEXT, warnings INTEGER)""")
        self.db.execute("CREATE INDEX IF NOT EXISTS sessions_agent ON sessions(agent)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS mention_aliases (
            agent TEXT, alias TEXT, ref TEXT, PRIMARY KEY(agent, alias))""")
        if self.db.execute("PRAGMA user_version").fetchone()[0] < 1:
            # Recheck old cached JSONL diagnostics once, without touching sources.
            with self.db:
                self.db.execute("UPDATE sessions SET mtime=-1 WHERE agent IN ('claude','codex')")
                self.db.execute("PRAGMA user_version=1")

    def close(self):
        self.db.close()

    def mention_aliases(self, rows):
        # Never reuse an emitted name for another session, even after deletion or
        # rename. References already inserted in prompts must retain their target.
        from .mentions import short_text
        result = {}
        with self.db:
            for row in rows:
                base = "".join(c if c.isalnum() else "_" for c in short_text(row["title"], 200)).strip("_")[:36] or "未命名会话"
                alias, number = base, 1
                while True:
                    self.db.execute("INSERT OR IGNORE INTO mention_aliases VALUES (?,?,?)", (row["agent"], alias, row["ref"]))
                    target = self.db.execute("SELECT ref FROM mention_aliases WHERE agent=? AND alias=?", (row["agent"], alias)).fetchone()[0]
                    if target == row["ref"]:
                        break
                    number += 1
                    alias = f"{base}_{number}"
                result[row["ref"]] = alias
        return result

    def refresh(self):
        stats = {"files": 0, "changed": 0, "bytesRead": 0, "errors": []}
        seen = set()
        for agent, adapter in self.adapters.items():
            if adapter.index_mode == "snapshot":
                try:
                    for s in adapter.scan_metadata():
                        seen.add(s.sourcePath)
                        ref = agent + ":" + hashlib.sha256(s.sourcePath.encode()).hexdigest()[:16]
                        self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                            ref, agent, s.sessionId, s.title or "未命名会话", s.cwd, s.createdAt, s.updatedAt,
                            s.sourcePath, s.latestAgentState, 0, 0, 0, "snapshot", len(s.parseWarnings)))
                        stats["files"] += 1
                    if adapter.scan_errors:
                        stats["errors"].extend(adapter.scan_errors)
                        seen.update(r[0] for r in self.db.execute("SELECT sourcePath FROM sessions WHERE agent=?", (agent,)))
                except (OSError, ValueError, TypeError, sqlite3.Error):
                    stats["errors"].append(agent + ": metadata unavailable or unsupported")
                    # A transient source failure must not delete previously indexed sessions.
                    seen.update(r[0] for r in self.db.execute("SELECT sourcePath FROM sessions WHERE agent=?", (agent,)))
                continue
            try:
                paths = list(adapter.discoverSessions())
            except OSError:
                stats["errors"].append(agent + ": source discovery unavailable")
                seen.update(r[0] for r in self.db.execute("SELECT sourcePath FROM sessions WHERE agent=?", (agent,)))
                continue
            for path in paths:
                seen.add(str(path))
                stats["files"] += 1
                try:
                    stat = path.stat()
                    old = self.db.execute("SELECT * FROM sessions WHERE sourcePath=?", (str(path),)).fetchone()
                    repair_title = old and adapter.metadata_needs_refresh(old)
                    if old and not repair_title and old["mtime"] == stat.st_mtime_ns and old["size"] == stat.st_size:
                        if old["warnings"]:
                            stats["errors"].append(agent + ": cached source metadata has parse warnings")
                        continue
                    offset = 0
                    if old and old["mtime"] != -1 and not old["warnings"] and not repair_title and stat.st_size > old["size"] and fingerprint(path, old["offset"]) == old["fingerprint"]:
                        offset = old["offset"]
                    s = SessionIR(agent=agent, sessionId=path.stem, sourcePath=str(path))
                    if offset:
                        for key in ("sessionId", "title", "cwd", "createdAt", "updatedAt", "latestAgentState"):
                            setattr(s, key, old[key])
                        s._metadata_seen = True
                    records, end, warnings = adapter.readSessionIncrementally(path, offset)
                    for record in records:
                        try:
                            adapter.consume(s, record)
                        except (TypeError, ValueError, KeyError, AttributeError):
                            warnings.append("unsupported record")
                        # Unknown record kinds are adapter diagnostics, not JSON errors.
                        # Tool-result orphan warnings are not used here: metadata scanning
                        # deliberately discards calls between records.
                        if s.unknownTypes:
                            warnings.append("unknown record types: " + ", ".join(s.unknownTypes[:20]))
                            s.unknownTypes.clear()
                        s.parseWarnings.clear()
                        # Discard IR content between metadata records.
                        s.messages.clear()
                        s.toolCalls.clear()
                        s.possibleTodos.clear()
                        s.errors.clear()
                    ref = agent + ":" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
                    if any("incomplete trailing" in w for w in warnings):
                        s.latestAgentState = "incomplete"
                    if warnings:
                        stats["errors"].append(agent + ": source metadata has parse warnings")
                    self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                        ref, agent, s.sessionId, s.title or s.sessionId, s.cwd, s.createdAt, s.updatedAt,
                        str(path), s.latestAgentState, stat.st_mtime_ns, stat.st_size, end,
                        fingerprint(path, end), len(warnings)))
                    stats["changed"] += 1
                    stats["bytesRead"] += end - offset
                except OSError as exc:
                    stats["errors"].append(type(exc).__name__ + ": source unavailable")
        for row in self.db.execute("SELECT sourcePath,agent FROM sessions").fetchall():
            if row[1] in self.adapters and row[0] not in seen:
                self.db.execute("DELETE FROM sessions WHERE sourcePath=?", (row[0],))
        self.db.commit()
        return stats

    def sessions(self, agent=None):
        enabled = list(self.adapters) if agent is None else [agent] if agent in self.adapters else []
        if not enabled:
            return []
        placeholders = ",".join("?" for _ in enabled)
        rows = self.db.execute(f"SELECT * FROM sessions WHERE agent IN ({placeholders})", enabled).fetchall()
        result = [dict(row) for row in rows]
        for name, adapter in self.adapters.items():
            if agent is None or name == agent:
                adapter.overlay_metadata([row for row in result if row["agent"] == name])
        # Browsing only overlays local titles; body extraction is an explicit command.
        from .titles import apply_cached_titles
        apply_cached_titles(self.home, result)
        return sorted(result,
                      key=lambda r: (session_time(r), r["ref"]), reverse=True)

    def matches(self, query, agent=None):
        query = query.lstrip("@")
        if query in self.adapters:
            return self.sessions(query)
        if ":" in query and query.split(":", 1)[0] in self.adapters:
            agent = query.split(":", 1)[0]
        rows = self.sessions(agent)
        exact = [r for r in rows if query in (r["ref"], r["sessionId"], r["agent"] + ":" + r["sessionId"])]
        if exact:
            return exact
        alias = query.split(":", 1)[-1].casefold()
        return [r for r in rows if alias in r["title"].casefold() or alias in Path(r["cwd"]).name.casefold() or r["sessionId"].casefold().startswith(alias)]

    def read(self, row):
        if row["agent"] not in self.adapters:
            raise ValueError("source agent is not enabled")
        adapter = self.adapters[row["agent"]]
        return adapter.read_indexed(row)
