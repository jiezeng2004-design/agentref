import hashlib
import os
import sqlite3
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from .core import SessionIR
from .adapters.base import BaseAdapter
from .adapters.registry import default_adapters

_ISO_ORDER_CACHE_LIMIT = 4096
ALIAS_INVENTORY_STREAM_THRESHOLD = 20000
ALIAS_INVENTORY_BATCH_SIZE = 4096
_ISO_ORDER_CACHE_SEEN = object()
_ISO_ORDER_CACHE_MISS = object()
_ISO_ORDER_CACHE = {}
_ALIAS_ASCII_TRANSLATION = str.maketrans({
    chr(codepoint): "_" for codepoint in range(128) if not chr(codepoint).isalnum()
})
_ISO_ORDER_CACHE_LOCK = Lock()
_SEARCH_FTS_MIN_ROWS = 20_000
_SEARCH_FTS_QUERY_THRESHOLD = 8
_SEARCH_FTS_MIN_CANDIDATES = 128
_SEARCH_FTS_MAX_CANDIDATES = 1024
_SEARCH_FTS_CANDIDATE_DIVISOR = 64
SESSION_COLUMNS = ("ref", "agent", "sessionId", "title", "cwd", "createdAt", "updatedAt",
                   "sourcePath", "latestAgentState", "mtime", "size", "offset", "fingerprint", "warnings")
SEARCH_DOCUMENT_POSITIONS = tuple(SESSION_COLUMNS.index(name)
                                  for name in ("ref", "agent", "sessionId", "title", "cwd"))


def _session_order_key(updated_at, created_at, mtime):
    for raw in (updated_at, created_at):
        if not isinstance(raw, str):
            continue
        value = _iso_session_order_key(raw)
        if value is not None:
            return value
    try:
        value = datetime.fromtimestamp(mtime / 1_000_000_000, timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        value = datetime.fromtimestamp(0, timezone.utc)
    return _datetime_order_key(value)


def _iso_session_order_key(raw):
    if len(raw) > 128:
        return _parse_iso_session_order_key(raw)
    value = _ISO_ORDER_CACHE.get(raw, _ISO_ORDER_CACHE_MISS)
    if value is not _ISO_ORDER_CACHE_MISS and value is not _ISO_ORDER_CACHE_SEEN:
        return value
    with _ISO_ORDER_CACHE_LOCK:
        value = _ISO_ORDER_CACHE.get(raw, _ISO_ORDER_CACHE_MISS)
        if value is not _ISO_ORDER_CACHE_MISS:
            if value is _ISO_ORDER_CACHE_SEEN:
                value = _parse_iso_session_order_key(raw)
                _ISO_ORDER_CACHE[raw] = value
            return value
        value = _parse_iso_session_order_key(raw)
        if len(_ISO_ORDER_CACHE) >= _ISO_ORDER_CACHE_LIMIT:
            _ISO_ORDER_CACHE.clear()
        _ISO_ORDER_CACHE[raw] = _ISO_ORDER_CACHE_SEEN
        return value


def _parse_iso_session_order_key(raw):
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return _datetime_order_key(value)


def _datetime_order_key(value):
    offset = value.utcoffset() or timedelta(0)
    # Convert to an integer UTC timeline without datetime.astimezone(), which
    # can overflow for valid ISO dates near year 1 or 9999.
    local_us = (((value.toordinal() - 1) * 24 + value.hour) * 60 + value.minute) * 60_000_000
    local_us += value.second * 1_000_000 + value.microsecond
    offset_us = ((offset.days * 24 + offset.seconds // 3600) * 60 + (offset.seconds % 3600) // 60) * 60_000_000
    offset_us += (offset.seconds % 60) * 1_000_000 + offset.microseconds
    return local_us - offset_us


def _search_casefold(value):
    return value.casefold() if isinstance(value, str) else ""


def _search_document_changed(old, values):
    if old is None:
        return True
    if isinstance(old, tuple):
        return any(old[position] != values[position] for position in SEARCH_DOCUMENT_POSITIONS)
    return any(old[name] != values[position]
               for position, name in zip(SEARCH_DOCUMENT_POSITIONS,
                                         ("ref", "agent", "sessionId", "title", "cwd")))


def _path_name(value):
    if not isinstance(value, str):
        return Path(value).name
    separators = os.sep + (os.altsep or "")
    drive, tail = os.path.splitdrive(value)
    if not tail or not tail.strip(separators):
        return ""
    return os.path.basename(value.rstrip(separators))


def _mention_alias_base(value):
    text = str(value)
    if text.isprintable():
        text = " ".join(text.split())
        if len(text) > 200:
            text = text[:199] + "…"
    else:
        from .mentions import short_text
        text = short_text(text, 200)
    alias = (text.translate(_ALIAS_ASCII_TRANSLATION) if text.isascii()
             else "".join(char if char.isalnum() else "_" for char in text))
    return alias.strip("_")[:36] or "未命名会话"


def _alias_identity_changed(old, values):
    if old is None:
        return True
    for key, value in values.items():
        previous = old[SESSION_COLUMNS.index(key)] if isinstance(old, tuple) else old[key]
        if previous != value:
            return True
    return False


def fingerprint(path, end):
    with path.open("rb") as f:
        head = f.read(min(end, 4096))
        f.seek(max(0, end - 4096))
        tail = f.read(min(end, 4096))
    return hashlib.sha256(head + tail).hexdigest()


class Index:
    def __init__(self, data_dir=None, adapters=None):
        self.adapters = {a.agent: a for a in (adapters if adapters is not None else default_adapters())}
        self._snapshot_metadata_cache = {}
        self._title_cache_signature = object()
        self._title_cache = {}
        self._mention_alias_inventory_cache = {}
        self._search_page_queries = 0
        self._search_sparse_queries = 0
        self._search_sparse_query_counts = {}
        self._search_fts_build_pending = False
        self._search_fts_pending_query = None
        self._search_dense_queries = {}
        self._search_fts_ready = False
        self._search_fts_dirty = False
        self._search_fts_disabled = False
        self._search_fts_data_version = None
        self._search_fts_below_signature = None
        self.home = Path(data_dir or os.environ.get("AGENTREF_HOME", Path.home() / ".agentref")).expanduser().resolve()
        for adapter in self.adapters.values():
            if adapter.index_mode not in ("incremental", "snapshot"):
                raise ValueError("unsupported adapter index mode")
            if any(self.home.is_relative_to(r) for r in adapter.roots):
                raise ValueError("AgentRef index must not be inside foreign session roots")
        self.home.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.home / "index.sqlite3", timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.create_function("agentref_session_order", 3, _session_order_key, deterministic=True)
        self.db.create_function("agentref_search_casefold", 1, _search_casefold, deterministic=True)
        self._session_match_state = [None]

        def session_match_dispatch(*values):
            callback = self._session_match_state[0]
            return int(callback(*values)) if callback is not None else 0

        self.db.create_function("agentref_session_matches", 8, session_match_dispatch)
        self.db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            ref TEXT PRIMARY KEY, agent TEXT, sessionId TEXT, title TEXT, cwd TEXT,
            createdAt TEXT, updatedAt TEXT, sourcePath TEXT UNIQUE,
            latestAgentState TEXT, mtime INTEGER, size INTEGER, offset INTEGER,
            fingerprint TEXT, warnings INTEGER)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS mention_aliases (
            agent TEXT, alias TEXT, ref TEXT, PRIMARY KEY(agent, alias))""")
        self.db.execute("CREATE INDEX IF NOT EXISTS mention_aliases_alias_ref ON mention_aliases(alias,agent,ref)")
        if self.db.execute("PRAGMA user_version").fetchone()[0] < 1:
            # Recheck old cached JSONL diagnostics once, without touching sources.
            with self.db:
                self.db.execute("UPDATE sessions SET mtime=-1 WHERE agent IN ('claude','codex')")
                self.db.execute("PRAGMA user_version=1")
        if self.db.execute("PRAGMA user_version").fetchone()[0] < 2:
            # Re-evaluate prior Codex parser warnings once after patch-event
            # support. Healthy rows and other sources keep their metadata cache.
            with self.db:
                self.db.execute("UPDATE sessions SET mtime=-1 WHERE agent='codex' AND warnings>0")
                self.db.execute("PRAGMA user_version=2")
        if self.db.execute("PRAGMA user_version").fetchone()[0] < 3:
            # Keep source filtering and recent-order paging in one index. This
            # also migrates existing databases atomically from the old agent-only
            # index without touching indexed session metadata or foreign sources.
            with self.db:
                self.db.execute("DROP INDEX IF EXISTS sessions_agent")
                self.db.execute("""CREATE INDEX sessions_agent ON sessions(
                    agent, agentref_session_order(updatedAt,createdAt,mtime) DESC, ref DESC)""")
                self.db.execute("PRAGMA user_version=3")
        else:
            self.db.execute("""CREATE INDEX IF NOT EXISTS sessions_agent ON sessions(
                agent, agentref_session_order(updatedAt,createdAt,mtime) DESC, ref DESC)""")
        if self.db.execute("PRAGMA user_version").fetchone()[0] < 4:
            with self.db:
                self.db.execute("CREATE INDEX IF NOT EXISTS sessions_sessionid ON sessions(sessionId)")
                self.db.execute("PRAGMA user_version=4")
        else:
            self.db.execute("CREATE INDEX IF NOT EXISTS sessions_sessionid ON sessions(sessionId)")

    def close(self):
        self.db.close()

    def _invalidate_search_fts(self):
        self.db.execute("DROP TABLE IF EXISTS temp.agentref_search")
        if self.db.in_transaction:
            self.db.commit()
        self._search_fts_ready = False
        self._search_fts_dirty = False
        self._search_fts_data_version = None
        self._search_fts_build_pending = False
        self._search_fts_pending_query = None
        self._search_sparse_queries = 0
        self._search_sparse_query_counts.clear()
        self._search_dense_queries.clear()
        self._search_fts_below_signature = None

    def _mark_search_fts_dirty(self):
        if (self._search_page_queries or self._search_sparse_queries
                or self._search_sparse_query_counts or self._search_fts_build_pending):
            self._search_page_queries = 0
            self._search_sparse_queries = 0
            self._search_sparse_query_counts.clear()
            self._search_fts_build_pending = False
            self._search_fts_pending_query = None
        if self._search_fts_ready:
            self._search_fts_dirty = True

    def _ensure_search_fts(self):
        """Build a process-local trigram candidate index for large histories."""
        if self._search_fts_disabled:
            return False
        try:
            data_version = self.db.execute("PRAGMA data_version").fetchone()[0]
            was_ready = self._search_fts_ready
            if (was_ready and not self._search_fts_dirty
                    and data_version == self._search_fts_data_version):
                self._search_fts_build_pending = False
                self._search_fts_pending_query = None
                return True
            if was_ready:
                self._invalidate_search_fts()
                return False
            current_signature = (data_version, self.db.total_changes)
            if current_signature == self._search_fts_below_signature:
                return False
            rows = self.db.execute("SELECT count(*) FROM sessions").fetchone()[0]
            if rows < _SEARCH_FTS_MIN_ROWS:
                self._search_fts_below_signature = current_signature
                return False
            self.db.execute("""CREATE VIRTUAL TABLE temp.agentref_search USING fts5(
                ref UNINDEXED, title, session_id, cwd,
                tokenize='trigram case_sensitive 1', detail=none)""")

            cursor = self.db.execute("SELECT rowid,ref,title,sessionId,cwd FROM sessions")
            insert_sql = "INSERT INTO temp.agentref_search(rowid,ref,title,session_id,cwd) VALUES (?,?,?,?,?)"
            while batch := cursor.fetchmany(512):
                self.db.executemany(insert_sql, (
                    (row[0], row[1], _search_casefold(row[2]),
                     _search_casefold(row[3]), _search_casefold(row[4]))
                    for row in batch))
            cursor.close()
            after_version = self.db.execute("PRAGMA data_version").fetchone()[0]
            if after_version != data_version:
                self._invalidate_search_fts()
                return False
            self._search_fts_data_version = after_version
            self._search_fts_ready = True
            self._search_fts_dirty = False
            self._search_fts_build_pending = False
            self._search_fts_pending_query = None
            if self.db.in_transaction:
                self.db.commit()
            return True
        except sqlite3.OperationalError:
            if not self._search_fts_ready:
                self._search_fts_disabled = True
            return False

    def _title_cache_file_signature(self):
        from .titles import CACHE
        try:
            stat = (self.home / CACHE).stat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            return ("unavailable", exc.errno)
        return (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size)

    def _load_title_cache(self):
        from .titles import load_cache
        for _ in range(2):
            before = self._title_cache_file_signature()
            if before == self._title_cache_signature:
                return self._title_cache
            cache = load_cache(self.home)
            after = self._title_cache_file_signature()
            self._title_cache = cache
            if before == after:
                self._title_cache_signature = after
                return cache
            # Do not trust a cache read that overlapped an atomic replacement.
            self._title_cache_signature = object()
        return self._title_cache

    def _mention_alias_inventory_signature(self, agents):
        self._load_title_cache()
        data_version = self.db.execute("PRAGMA data_version").fetchone()[0]
        overlays = tuple((name, self.adapters[name].metadata_overlay_signature()) for name in agents)
        return self.db.total_changes, data_version, self._title_cache_signature, overlays

    def ensure_mention_alias_inventory(self, agent=None, force=False):
        """Persist stable aliases for the current ordered metadata inventory."""
        agents = tuple(self.adapters) if agent is None else (agent,) if agent in self.adapters else ()
        if not agents:
            return
        signature = self._mention_alias_inventory_signature(agents)
        cached = self._mention_alias_inventory_cache.get(agents)
        if not force and cached is not None and cached[0] == signature:
            if cached[1] is not None:
                self._mention_alias_inventory_cache[agents] = (signature, None)
            return
        placeholders = ",".join("?" for _ in agents)
        count = self.db.execute(
            f"SELECT count(*) FROM sessions WHERE agent IN ({placeholders})", agents).fetchone()[0]
        if count <= ALIAS_INVENTORY_STREAM_THRESHOLD:
            self.mention_aliases(self.sessions(agent), return_map=False)
        else:
            seeded_empty = False
            with self.db:
                if not self.db.in_transaction:
                    self.db.execute("BEGIN IMMEDIATE")
                existing_alias = self.db.execute(
                    f"SELECT 1 FROM mention_aliases WHERE agent IN ({placeholders}) LIMIT 1",
                    agents).fetchone()
                if existing_alias is None:
                    occupied = set()
                    next_number = {}
                    base_cache = {}
                    missing = object()
                    for rows in self.iter_session_batches(
                            agent, batch_size=ALIAS_INVENTORY_BATCH_SIZE):
                        inserts = []
                        for row in rows:
                            title = row["title"]
                            try:
                                cache_key = (type(title), title)
                                base = base_cache.get(cache_key, missing)
                            except TypeError:
                                cache_key = None
                                base = missing
                            if base is missing:
                                base = _mention_alias_base(title)
                                if cache_key is not None and len(base_cache) < 4096:
                                    base_cache[cache_key] = base
                            key = (row["agent"], base)
                            number = next_number.get(key, 1)
                            alias = base if number == 1 else f"{base}_{number}"
                            while (row["agent"], alias) in occupied:
                                number += 1
                                alias = f"{base}_{number}"
                            occupied.add((row["agent"], alias))
                            if number > 1:
                                next_number[key] = number + 1
                            inserts.append((row["agent"], alias, row["ref"]))
                        if inserts:
                            inserts.sort(key=lambda item: (item[0], item[1]))
                            self.db.executemany(
                                "INSERT OR IGNORE INTO mention_aliases VALUES (?,?,?)", inserts)
                    seeded_empty = True
            if not seeded_empty:
                allocation_state = {}
                for rows in self.iter_session_batches(agent, batch_size=ALIAS_INVENTORY_BATCH_SIZE):
                    self.mention_aliases(rows, return_map=False, allocation_state=allocation_state)
        signature = self._mention_alias_inventory_signature(agents)
        self._mention_alias_inventory_cache[agents] = (signature, None)

    def mention_alias_inventory(self, agent=None, force=False):
        """Reserve stable aliases once per unchanged metadata inventory."""
        agents = tuple(self.adapters) if agent is None else (agent,) if agent in self.adapters else ()
        if not agents:
            return {}
        signature = self._mention_alias_inventory_signature(agents)
        cached = self._mention_alias_inventory_cache.get(agents)
        if not force and cached is not None and cached[0] == signature and cached[1] is not None:
            return cached[1]
        rows = self.sessions(agent)
        aliases = self.mention_aliases(rows)
        signature = self._mention_alias_inventory_signature(agents)
        self._mention_alias_inventory_cache[agents] = (signature, aliases)
        return aliases

    def mention_alias_inventory_is_current(self, agent=None):
        agents = tuple(self.adapters) if agent is None else (agent,) if agent in self.adapters else ()
        if not agents:
            return False
        cached = self._mention_alias_inventory_cache.get(agents)
        return cached is not None and cached[0] == self._mention_alias_inventory_signature(agents)

    def _rows_for_refs(self, refs):
        result = []
        values = list(dict.fromkeys(refs))
        for start in range(0, len(values), 500):
            page = values[start:start + 500]
            placeholders = ",".join("?" for _ in page)
            result.extend(dict(row) for row in self.db.execute(
                f"SELECT * FROM sessions WHERE ref IN ({placeholders})", page))
        if not result:
            return result
        enabled = tuple(dict.fromkeys(row["agent"] for row in result))
        overlays, _ = self._metadata_overlays(enabled)
        self._overlay_metadata(result, overlays=overlays, title_cache=self._load_title_cache())
        return sorted(result, key=lambda row: (
            _session_order_key(row["updatedAt"], row["createdAt"], row["mtime"]), row["ref"]),
            reverse=True)

    def _metadata_overlays(self, enabled):
        overlays = {}
        sql_supported = True
        for name in enabled:
            adapter = self.adapters[name]
            adapter_type = type(adapter)
            metadata_overlay = getattr(adapter_type, "metadata_overlay", BaseAdapter.metadata_overlay)
            overlay_metadata = getattr(adapter_type, "overlay_metadata", None)
            overlay_title = getattr(adapter_type, "overlay_title", BaseAdapter.overlay_title)
            custom_overlay = overlay_metadata is not BaseAdapter.overlay_metadata
            custom_map = metadata_overlay is not BaseAdapter.metadata_overlay
            custom_title = overlay_title is not BaseAdapter.overlay_title
            if custom_overlay or custom_map or custom_title:
                if not (custom_overlay and custom_map and custom_title):
                    sql_supported = False
                    continue
                overlays[name] = adapter.metadata_overlay()
        return overlays, sql_supported

    def _overlay_metadata(self, result, overlays=None, title_cache=None):
        grouped = {name: [] for name in self.adapters}
        for row in result:
            rows = grouped.get(row["agent"])
            if rows is not None:
                rows.append(row)
        for name, adapter in self.adapters.items():
            rows = grouped[name]
            if rows:
                if overlays is not None and name in overlays:
                    adapter.overlay_metadata(rows, overlays[name])
                else:
                    adapter.overlay_metadata(rows)
        # Browsing only overlays local titles; body extraction is an explicit command.
        from .titles import apply_cached_titles
        apply_cached_titles(self.home, result,
                            cache=title_cache if title_cache is not None else self._load_title_cache())
        return result

    def _all_query_page(self, enabled, limit, offset, include_total=False):
        """Page the unfiltered session list without invoking the keyword matcher."""
        if limit == 0 and not include_total:
            return []
        placeholders = ",".join("?" for _ in enabled)
        total = None
        read_transaction = include_total and not self.db.in_transaction
        try:
            if read_transaction:
                self.db.execute("BEGIN")
            if include_total:
                total = self.db.execute(
                    f"SELECT count(*) FROM sessions WHERE agent IN ({placeholders})", enabled
                ).fetchone()[0]

            if limit == 0:
                rows = []
            else:
                rows = self.sessions(enabled[0] if len(enabled) == 1 else None,
                                     limit=limit, offset=offset)
            return (rows, total) if include_total else rows
        finally:
            if read_transaction and self.db.in_transaction:
                self.db.execute("ROLLBACK")

    def _query_page(self, enabled, query, limit, offset, include_total=False):
        if limit == 0 and not include_total:
            return []
        if not query:
            return self._all_query_page(enabled, limit, offset, include_total)
        overlays, sql_supported = self._metadata_overlays(enabled)
        if not sql_supported:
            return None
        from .titles import identity, is_unnamed
        title_cache = self._load_title_cache()
        adapters = self.adapters
        cwd_names = {}
        missing_cwd = object()

        def row_matches(agent, session_id, ref, title, cwd, created_at, source_path, needle):
            title_overlay = overlays.get(agent)
            if agent in overlays and (title_overlay or title == session_id):
                row = {"agent": agent, "sessionId": session_id, "ref": ref, "title": title,
                       "cwd": cwd, "createdAt": created_at, "sourcePath": source_path}
                title = adapters[agent].overlay_title(row, title_overlay)
            cached = title_cache.get(ref)
            if isinstance(cached, dict) and isinstance(cached.get("title"), str) and cached["title"]:
                row = {"agent": agent, "sessionId": session_id, "ref": ref, "title": title,
                       "cwd": cwd, "createdAt": created_at, "sourcePath": source_path}
                if is_unnamed(row) and cached.get("identity") == identity(row):
                    title = cached["title"]
            if needle in title.casefold():
                return 1
            if session_id.casefold().startswith(needle):
                return 1
            cwd_name = cwd_names.get(cwd, missing_cwd)
            if cwd_name is missing_cwd:
                cwd_name = _path_name(cwd).casefold()
                if len(cwd_names) < 1024:
                    cwd_names[cwd] = cwd_name
            return int(needle in cwd_name)

        fts_agents = []
        grams = dict.fromkeys(query[position:position + 3] for position in range(len(query) - 2))
        fts_expression = " AND ".join('"' + gram.replace('"', '""') + '"' for gram in grams)
        page_capacity_fits = (limit is not None
                              and offset + limit <= 9_223_372_036_854_775_807)
        eligible_fts_agents = []
        dense_query_key = (tuple(enabled), query)
        if not title_cache and dense_query_key not in self._search_dense_queries:
            for name in enabled:
                if name not in overlays:
                    eligible_fts_agents.append(name)
                elif (name == "codex" and not overlays[name]
                      and query not in "未命名会话".casefold()):
                    # The only empty-map Codex title rewrite is the unnamed label;
                    # session-ID prefix matching remains covered by the indexed ID field.
                    eligible_fts_agents.append(name)
        sparse_query_key = (tuple(eligible_fts_agents), query)
        if (page_capacity_fits and not self.db.in_transaction and len(query) >= 3
                and "\x00" not in query and eligible_fts_agents):
            self._search_page_queries += 1
            pending_query_matches = (self._search_fts_pending_query is None
                                     or self._search_fts_pending_query == sparse_query_key)
            if self._search_fts_ready or (self._search_fts_build_pending and pending_query_matches):
                if self._ensure_search_fts():
                    history_size = self.db.execute("SELECT count(*) FROM sessions").fetchone()[0]
                    candidate_cap = min(_SEARCH_FTS_MAX_CANDIDATES,
                                        max(_SEARCH_FTS_MIN_CANDIDATES,
                                            history_size // _SEARCH_FTS_CANDIDATE_DIVISOR))
                    candidate_placeholders = ",".join("?" for _ in eligible_fts_agents)
                    candidates = self.db.execute(f"""SELECT s.rowid FROM temp.agentref_search AS f
                        CROSS JOIN sessions AS s ON s.ref=f.ref
                        WHERE s.agent IN ({candidate_placeholders}) AND agentref_search MATCH ?
                        LIMIT ?""", [*eligible_fts_agents, fts_expression, candidate_cap + 1]).fetchmany(candidate_cap + 1)
                    if len(candidates) <= candidate_cap:
                        fts_agents = eligible_fts_agents
                    else:
                        if len(self._search_dense_queries) >= 128:
                            self._search_dense_queries.pop(next(iter(self._search_dense_queries)))
                        self._search_dense_queries[dense_query_key] = True

        self._session_match_state[0] = row_matches
        placeholders = ",".join("?" for _ in enabled)
        order = "agentref_session_order(updatedAt,createdAt,mtime) DESC, ref DESC"
        total = None
        read_transaction = ((limit is not None and include_total) or bool(fts_agents)) and not self.db.in_transaction
        try:
            if read_transaction:
                data_version = self.db.execute("PRAGMA data_version").fetchone()[0]
                self.db.execute("BEGIN")
                self.db.execute("SELECT rowid FROM sessions LIMIT 1").fetchone()
                version_after_snapshot = self.db.execute("PRAGMA data_version").fetchone()[0]
                if (fts_agents and (version_after_snapshot != data_version
                                    or version_after_snapshot != self._search_fts_data_version)):
                    fts_agents = []
            if limit is not None and offset + limit <= 9_223_372_036_854_775_807:
                if include_total:
                    if fts_agents:
                        fallback_agents = [name for name in enabled if name not in fts_agents]
                        total = 0
                        fts_placeholders = ",".join("?" for _ in fts_agents)
                        count_sql = f"""SELECT count(*) FROM temp.agentref_search AS f
                                      CROSS JOIN sessions AS s ON s.ref=f.ref
                                      WHERE s.agent IN ({fts_placeholders}) AND agentref_search MATCH ?
                                        AND agentref_session_matches(s.agent,s.sessionId,s.ref,s.title,s.cwd,
                                                                     s.createdAt,s.sourcePath,?)"""
                        total += self.db.execute(count_sql, [*fts_agents, fts_expression, query]).fetchone()[0]
                        if fallback_agents:
                            fallback_placeholders = ",".join("?" for _ in fallback_agents)
                            fallback_sql = f"""SELECT count(*) FROM sessions WHERE agent IN ({fallback_placeholders})
                                              AND agentref_session_matches(agent,sessionId,ref,title,cwd,createdAt,sourcePath,?)"""
                            total += self.db.execute(fallback_sql, [*fallback_agents, query]).fetchone()[0]
                    else:
                        count_sql = f"""SELECT count(*) FROM sessions WHERE agent IN ({placeholders})
                                          AND agentref_session_matches(agent,sessionId,ref,title,cwd,createdAt,sourcePath,?)"""
                        total = self.db.execute(count_sql, list(enabled) + [query]).fetchone()[0]
                page_capacity = offset + limit
                if not include_total or (limit > 0 and total):
                    if len(enabled) == 1:
                        if enabled[0] in fts_agents:
                            sql = f"""SELECT s.* FROM temp.agentref_search AS f
                                      CROSS JOIN sessions AS s ON s.ref=f.ref
                                      WHERE s.agent=? AND agentref_search MATCH ?
                                        AND agentref_session_matches(s.agent,s.sessionId,s.ref,s.title,s.cwd,
                                                                     s.createdAt,s.sourcePath,?)
                                      ORDER BY {order} LIMIT ? OFFSET ?"""
                            params = [enabled[0], fts_expression, query, limit, offset]
                        else:
                            sql = f"""SELECT * FROM sessions WHERE agent=?
                                      AND agentref_session_matches(agent,sessionId,ref,title,cwd,createdAt,sourcePath,?)
                                      ORDER BY {order} LIMIT ? OFFSET ?"""
                            params = [enabled[0], query, limit, offset]
                        rows = [dict(row) for row in self.db.execute(sql, params).fetchall()]
                    else:
                        # Each source contributes at most K rows to a global top-K,
                        # so local ordered LIMITs can bound the outer merge sort.
                        arms = []
                        params = []
                        for name in enabled:
                            if name in fts_agents:
                                arms.append(f"""SELECT * FROM (SELECT s.* FROM temp.agentref_search AS f
                                              CROSS JOIN sessions AS s ON s.ref=f.ref
                                              WHERE s.agent=? AND agentref_search MATCH ?
                                                AND agentref_session_matches(s.agent,s.sessionId,s.ref,s.title,s.cwd,
                                                                             s.createdAt,s.sourcePath,?)
                                              ORDER BY {order} LIMIT ?)""")
                                params.extend((name, fts_expression, query, page_capacity))
                            else:
                                arms.append(f"""SELECT * FROM (SELECT * FROM sessions WHERE agent=?
                                              AND agentref_session_matches(agent,sessionId,ref,title,cwd,createdAt,sourcePath,?)
                                              ORDER BY {order} LIMIT ?)""")
                                params.extend((name, query, page_capacity))
                        sql = f"SELECT * FROM ({' UNION ALL '.join(arms)}) ORDER BY {order} LIMIT ? OFFSET ?"
                        params.extend((limit, offset))
                        rows = [dict(row) for row in self.db.execute(sql, params).fetchall()]
                else:
                    rows = []
            else:
                selected = "*" if not include_total else "*, COUNT(*) OVER() AS _agentrefTotal"
                sql = f"""SELECT {selected} FROM sessions
                          WHERE agent IN ({placeholders})
                            AND agentref_session_matches(agent,sessionId,ref,title,cwd,createdAt,sourcePath,?)
                          ORDER BY {order}"""
                params = list(enabled) + [query]
                if limit is None:
                    sql += " LIMIT -1 OFFSET ?"
                    params.append(offset)
                else:
                    sql += " LIMIT ? OFFSET ?"
                    params.extend((limit, offset))
                rows = [dict(row) for row in self.db.execute(sql, params).fetchall()]
                total = rows[0]["_agentrefTotal"] if include_total and rows else None
                if include_total:
                    for row in rows:
                        row.pop("_agentrefTotal", None)
            if include_total and total is None:
                count_sql = f"SELECT count(*) FROM sessions WHERE agent IN ({placeholders}) AND agentref_session_matches(agent,sessionId,ref,title,cwd,createdAt,sourcePath,?)"
                total = self.db.execute(count_sql, list(enabled) + [query]).fetchone()[0]
        finally:
            if read_transaction and self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self._session_match_state[0] = None
        result = self._overlay_metadata(rows, overlays=overlays, title_cache=title_cache)
        if (not self._search_fts_ready and not self._search_fts_disabled
                and eligible_fts_agents):
            observed_matches = total if include_total else len(result) if offset == 0 else None
            if observed_matches is not None and observed_matches <= 512:
                previous = self._search_sparse_query_counts.get(sparse_query_key, 0)
                if previous == 0 and len(self._search_sparse_query_counts) >= 128:
                    self._search_sparse_query_counts.pop(next(iter(self._search_sparse_query_counts)))
                self._search_sparse_query_counts[sparse_query_key] = previous + 1
                if previous + 1 >= 2:
                    self._search_fts_build_pending = True
                    self._search_fts_pending_query = sparse_query_key
                if self._search_page_queries >= _SEARCH_FTS_QUERY_THRESHOLD:
                    self._search_sparse_queries += 1
                    if self._search_sparse_queries >= 2:
                        self._search_fts_build_pending = True
                        self._search_fts_pending_query = None
        return (result, total) if include_total else result

    def mention_aliases(self, rows, return_map=True, allocation_state=None):
        # Never reuse an emitted name for another session, even after deletion or
        # rename. References already inserted in prompts must retain their target.
        if not rows:
            return {}
        result = {} if return_map else None
        with self.db:
            # Reserve alias space before reading ownership so concurrent callers
            # cannot independently claim the same first alias.
            if not self.db.in_transaction:
                self.db.execute("BEGIN IMMEDIATE")
            alias_base_cache = {}
            missing_base = object()

            def alias_base(title):
                try:
                    key = (type(title), title)
                    base = alias_base_cache.get(key, missing_base)
                except TypeError:
                    return _mention_alias_base(title)
                if base is missing_base:
                    base = _mention_alias_base(title)
                    if len(alias_base_cache) < 4096:
                        alias_base_cache[key] = base
                return base

            agents = tuple(dict.fromkeys(row["agent"] for row in rows))
            agent_placeholders = ",".join("?" for _ in agents)
            existing_alias = self.db.execute(
                f"SELECT 1 FROM mention_aliases WHERE agent IN ({agent_placeholders}) LIMIT 1",
                agents).fetchone()
            if existing_alias is None:
                occupied_by_agent = {}
                next_number = {}
                inserts = []
                for row in rows:
                    base = alias_base(row["title"])
                    key = (row["agent"], base)
                    number = next_number.get(key, 1)
                    alias = base if number == 1 else f"{base}_{number}"
                    aliases_for_agent = occupied_by_agent.setdefault(row["agent"], set())
                    while alias in aliases_for_agent:
                        number += 1
                        alias = f"{base}_{number}"
                    aliases_for_agent.add(alias)
                    next_number[key] = number + 1
                    if result is not None:
                        result[row["ref"]] = alias
                    inserts.append((row["agent"], alias, row["ref"]))
                if inserts:
                    inserts.sort(key=lambda item: (item[0], item[1]))
                    self.db.executemany("INSERT OR IGNORE INTO mention_aliases VALUES (?,?,?)", inserts)
                return result
            bases = {}
            for row in rows:
                bases[row["ref"]] = alias_base(row["title"])
            candidates = {}
            refs_by_base = {}
            for row in rows:
                base = bases[row["ref"]]
                candidates.setdefault(row["agent"], set()).add(base)
                refs_by_base.setdefault((row["agent"], base), []).append(row["ref"])
            owners = {}
            # Read only aliases that this inventory can use as its first choice.
            # Existing base ownership is read in bounded chunks; numbered suffix
            # ownership is prefetched only for bases that can collide.
            for agent, aliases in candidates.items():
                values = sorted(aliases)
                for start in range(0, len(values), 500):
                    page = values[start:start + 500]
                    placeholders = ",".join("?" for _ in page)
                    owners.update({(agent, row["alias"]): row["ref"] for row in self.db.execute(
                        f"SELECT alias,ref FROM mention_aliases WHERE agent=? AND alias IN ({placeholders})",
                        [agent, *page])})
            missing = object()
            numbered_candidates = {}
            candidate_roles = {}
            numbered_loaded_until = {}
            for (agent, base), refs in refs_by_base.items():
                base_owner = owners.get((agent, base))
                if len(refs) > 1 or (base_owner is not None and base_owner not in refs):
                    numbered_loaded_until[(agent, base)] = len(refs) + 1
                    for number in range(2, len(refs) + 2):
                        alias = f"{base}_{number}"
                        numbered_candidates.setdefault(agent, set()).add(alias)
                        candidate_roles.setdefault((agent, alias), []).append((base, number))
            for agent, aliases in numbered_candidates.items():
                values = sorted(aliases)
                for start in range(0, len(values), 500):
                    page = values[start:start + 500]
                    placeholders = ",".join("?" for _ in page)
                    owners.update({(agent, row["alias"]): row["ref"] for row in self.db.execute(
                        f"SELECT alias,ref FROM mention_aliases WHERE agent=? AND alias IN ({placeholders})",
                        [agent, *page])})
            existing_numbers = {}
            # Preserve each ref's already-reserved numbered alias even when
            # inventory order changes; otherwise a reversed duplicate group
            # would scan every earlier suffix for every row.
            for (agent, alias), roles in candidate_roles.items():
                owner = owners.get((agent, alias))
                if owner is not None:
                    for base, number in roles:
                        owner_key = (agent, base, owner)
                        prior = existing_numbers.get(owner_key)
                        if prior is None or number < prior:
                            existing_numbers[owner_key] = number
            next_number = allocation_state if allocation_state is not None else {}
            inserts = []
            for row in rows:
                base = bases[row["ref"]]
                key = (row["agent"], base)
                target = owners.get(key, missing)
                if target is missing:
                    alias = base
                    owners[key] = row["ref"]
                    inserts.append((row["agent"], alias, row["ref"]))
                elif target == row["ref"]:
                    alias = base
                else:
                    assigned_number = existing_numbers.get((row["agent"], base, row["ref"]))
                    if assigned_number is not None:
                        alias = f"{base}_{assigned_number}"
                        number = next_number.get(key, 2)
                        while number <= assigned_number:
                            numbered_alias = owners.get((row["agent"], f"{base}_{number}"), missing)
                            if numbered_alias is missing:
                                break
                            number += 1
                        next_number[key] = number
                        if result is not None:
                            result[row["ref"]] = alias
                        continue
                    number = next_number.get(key, 2)
                    while True:
                        alias = f"{base}_{number}"
                        numbered_key = (row["agent"], alias)
                        target = owners.get(numbered_key, missing)
                        loaded_until = numbered_loaded_until.get(key, 1)
                        if target is missing and number > loaded_until:
                            start = max(loaded_until + 1, number)
                            end = max(number, start + 499)
                            page = [f"{base}_{candidate}" for candidate in range(start, end + 1)]
                            placeholders = ",".join("?" for _ in page)
                            owners.update({(row["agent"], item["alias"]): item["ref"]
                                           for item in self.db.execute(
                                               f"SELECT alias,ref FROM mention_aliases "
                                               f"WHERE agent=? AND alias IN ({placeholders})",
                                               [row["agent"], *page])})
                            numbered_loaded_until[key] = end
                            target = owners.get(numbered_key, missing)
                        if target is missing:
                            owners[numbered_key] = row["ref"]
                            inserts.append((row["agent"], alias, row["ref"]))
                            next_number[key] = number + 1
                            break
                        if target == row["ref"]:
                            next_number[key] = number + 1
                            break
                        number += 1
                if result is not None:
                    result[row["ref"]] = alias
            if inserts:
                inserts.sort(key=lambda item: (item[0], item[1]))
                self.db.executemany("INSERT OR IGNORE INTO mention_aliases VALUES (?,?,?)", inserts)
        return result

    def refresh(self):
        stats = {"files": 0, "changed": 0, "bytesRead": 0, "errors": []}
        search_document_changed = False
        seen = set()
        alias_changed_refs = {}
        alias_deleted_refs = {}
        alias_cache_baseline = {
            agents: self._mention_alias_inventory_signature(agents)
            for agents in self._mention_alias_inventory_cache
        }
        for agent, adapter in self.adapters.items():
            if adapter.index_mode == "snapshot":
                snapshot_paths = set()
                existing_snapshot_rows = [None]
                existing_source_paths = [None]
                snapshot_updates = []

                def flush_snapshot_updates():
                    if snapshot_updates:
                        self.db.executemany(
                            "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            snapshot_updates)
                        snapshot_updates.clear()

                def old_snapshot_row(source_path):
                    if existing_snapshot_rows[0] is None:
                        existing_snapshot_rows[0] = {
                            row["sourcePath"]: row for row in self.db.execute(
                                "SELECT * FROM sessions WHERE agent=?", (agent,))
                        }
                        if existing_source_paths[0] is None:
                            existing_source_paths[0] = tuple(sorted(existing_snapshot_rows[0]))
                    return existing_snapshot_rows[0].get(source_path)

                def current_source_paths(path_text):
                    if existing_source_paths[0] is None:
                        existing_source_paths[0] = tuple(row[0] for row in self.db.execute(
                            "SELECT sourcePath FROM sessions WHERE agent=? ORDER BY sourcePath", (agent,)))
                    paths = existing_source_paths[0]
                    current = []
                    exact = bisect_left(paths, path_text)
                    if exact < len(paths) and paths[exact] == path_text:
                        current.append(path_text)
                    prefix = path_text + "::"
                    position = bisect_left(paths, prefix)
                    while position < len(paths) and paths[position].startswith(prefix):
                        current.append(paths[position])
                        position += 1
                    return tuple(current)

                def reuse_metadata(path, signature, scanned, source_paths=()):
                    path_text = str(path)
                    key = (agent, path_text)
                    snapshot_paths.add(key)
                    if scanned:
                        self._snapshot_metadata_cache[key] = (signature, tuple(sorted(source_paths)))
                        return False
                    cached = self._snapshot_metadata_cache.get(key)
                    if cached is None or cached[0] != signature:
                        return False
                    current_paths = current_source_paths(path_text)
                    if current_paths != cached[1]:
                        self._snapshot_metadata_cache.pop(key, None)
                        return False
                    seen.update(current_paths)
                    stats["files"] += len(cached[1])
                    return True

                try:
                    previous_reuse = getattr(adapter, "metadata_reuse", None)
                    if (hasattr(adapter, "metadata_reuse")
                            and getattr(adapter, "metadata_cache_enabled", False)):
                        adapter.metadata_reuse = reuse_metadata
                    try:
                        for s in adapter.scan_metadata():
                            seen.add(s.sourcePath)
                            ref = agent + ":" + hashlib.sha256(s.sourcePath.encode()).hexdigest()[:16]
                            values = (ref, agent, s.sessionId, s.title or "未命名会话", s.cwd, s.createdAt,
                                      s.updatedAt, s.sourcePath, s.latestAgentState, 0, 0, 0, "snapshot",
                                      len(s.parseWarnings))
                            old = old_snapshot_row(s.sourcePath)
                            if _alias_identity_changed(old, {
                                    "ref": ref, "agent": agent, "sessionId": s.sessionId,
                                    "title": s.title or "未命名会话", "cwd": s.cwd,
                                    "createdAt": s.createdAt, "sourcePath": s.sourcePath}):
                                alias_changed_refs.setdefault(agent, set()).add(ref)
                                if old is not None and old["ref"] != ref:
                                    alias_deleted_refs.setdefault(agent, set()).add(old["ref"])
                            if old is None or tuple(old) != values:
                                if _search_document_changed(old, values):
                                    search_document_changed = True
                                    self._mark_search_fts_dirty()
                                snapshot_updates.append(values)
                                existing_snapshot_rows[0][s.sourcePath] = values
                                stats["changed"] += 1
                                if len(snapshot_updates) >= 512:
                                    flush_snapshot_updates()
                            stats["files"] += 1
                    finally:
                        try:
                            flush_snapshot_updates()
                        finally:
                            if (hasattr(adapter, "metadata_reuse")
                                    and getattr(adapter, "metadata_cache_enabled", False)):
                                adapter.metadata_reuse = previous_reuse
                    if adapter.scan_errors:
                        stats["errors"].extend(adapter.scan_errors)
                        seen.update(r[0] for r in self.db.execute("SELECT sourcePath FROM sessions WHERE agent=?", (agent,)))
                    if not adapter.scan_errors:
                        for key in [key for key in self._snapshot_metadata_cache
                                    if key[0] == agent and key not in snapshot_paths]:
                            self._snapshot_metadata_cache.pop(key, None)
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
            existing = {row["sourcePath"]: row for row in self.db.execute(
                "SELECT * FROM sessions WHERE agent=?", (agent,))}
            for path in paths:
                seen.add(str(path))
                stats["files"] += 1
                try:
                    mtime_ns, size = adapter.discovered_metadata(path)
                    old = existing.get(str(path))
                    repair_title = old and adapter.metadata_needs_refresh(old)
                    if old and not repair_title and old["mtime"] == mtime_ns and old["size"] == size:
                        if old["warnings"]:
                            stats["errors"].append(agent + ": cached source metadata has parse warnings")
                        continue
                    offset = 0
                    if old and old["mtime"] != -1 and not old["warnings"] and not repair_title and size > old["size"] and fingerprint(path, old["offset"]) == old["fingerprint"]:
                        offset = old["offset"]
                    s = SessionIR(agent=agent, sessionId=path.stem, sourcePath=str(path))
                    if offset:
                        for key in ("sessionId", "title", "cwd", "createdAt", "updatedAt", "latestAgentState"):
                            setattr(s, key, old[key])
                        s._metadata_seen = True
                    warning_count = 0
                    incomplete_tail = False

                    def note_warning(warning):
                        nonlocal warning_count, incomplete_tail
                        warning_count += 1
                        if "incomplete trailing" in warning:
                            incomplete_tail = True

                    def consume_record(record):
                        try:
                            adapter.consume(s, record)
                        except (TypeError, ValueError, KeyError, AttributeError):
                            note_warning("unsupported record")
                        # Unknown record kinds are adapter diagnostics, not JSON errors.
                        # Tool-result orphan warnings are not used here: metadata scanning
                        # deliberately discards calls between records.
                        if s.unknownTypes:
                            note_warning("unknown record types: " + ", ".join(s.unknownTypes[:20]))
                            s.unknownTypes.clear()
                        # Metadata indexing intentionally discards tool calls between
                        # records, so an unmatched result is not a useful diagnostic
                        # here. Preserve every other adapter warning before clearing
                        # per-record IR state; otherwise parser conflicts and partial
                        # records silently disappear from the index health signal.
                        for warning in s.parseWarnings:
                            if not warning.startswith("orphan tool result:"):
                                note_warning(warning)
                        s.parseWarnings.clear()
                        # Discard IR content between metadata records.
                        s.messages.clear()
                        s.toolCalls.clear()
                        tool_call_index = getattr(s, "_toolCallById", None)
                        if tool_call_index is not None:
                            tool_call_index.clear()
                        patch_event_index = getattr(s, "_codexPatchEventsByKey", None)
                        if patch_event_index is not None:
                            patch_event_index.clear()
                        s.possibleTodos.clear()
                        s.errors.clear()
                    end, _ = adapter.scanSessionIncrementally(path, offset, consume_record,
                                                              on_warning=note_warning, collect_warnings=False)
                    ref = agent + ":" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
                    if incomplete_tail:
                        s.latestAgentState = "incomplete"
                    if warning_count:
                        stats["errors"].append(agent + ": source metadata has parse warnings")
                    if _alias_identity_changed(old, {
                            "ref": ref, "agent": agent, "sessionId": s.sessionId,
                            "title": s.title or s.sessionId, "cwd": s.cwd,
                            "createdAt": s.createdAt, "sourcePath": str(path)}):
                        alias_changed_refs.setdefault(agent, set()).add(ref)
                        if old is not None and old["ref"] != ref:
                            alias_deleted_refs.setdefault(agent, set()).add(old["ref"])
                    values = (
                        ref, agent, s.sessionId, s.title or s.sessionId, s.cwd, s.createdAt, s.updatedAt,
                        str(path), s.latestAgentState, mtime_ns, size, end,
                        fingerprint(path, end), warning_count)
                    if _search_document_changed(old, values):
                        search_document_changed = True
                        self._mark_search_fts_dirty()
                    self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
                    stats["changed"] += 1
                    stats["bytesRead"] += end - offset
                except OSError as exc:
                    stats["errors"].append(type(exc).__name__ + ": source unavailable")
            adapter.release_discovered_metadata()
        enabled = list(self.adapters)
        if enabled:
            placeholders = ",".join("?" for _ in enabled)
            stale = []
            for row in self.db.execute(
                    f"SELECT sourcePath,agent,ref FROM sessions WHERE agent IN ({placeholders})", enabled):
                if row[0] not in seen:
                    stale.append((row[0],))
                    alias_deleted_refs.setdefault(row[1], set()).add(row[2])
            if stale:
                search_document_changed = True
                self._mark_search_fts_dirty()
                self.db.executemany("DELETE FROM sessions WHERE sourcePath=?", stale)
        else:
            stale = []
        self.db.commit()
        if search_document_changed:
            self._mark_search_fts_dirty()
        for agents, before in alias_cache_baseline.items():
            cached = self._mention_alias_inventory_cache.get(agents)
            if cached is None or cached[0] != before:
                continue
            after = self._mention_alias_inventory_signature(agents)
            if after[1:] != before[1:]:
                self._mention_alias_inventory_cache.pop(agents, None)
                continue
            changed = set().union(*(alias_changed_refs.get(agent, set()) for agent in agents))
            deleted = set().union(*(alias_deleted_refs.get(agent, set()) for agent in agents))
            if not changed and not deleted:
                self._mention_alias_inventory_cache[agents] = (after, cached[1])
                continue
            rows = self._rows_for_refs(changed)
            aliases = self.mention_aliases(rows, return_map=cached[1] is not None) if rows else {}
            if cached[1] is not None:
                inventory = cached[1]
                for ref in deleted:
                    inventory.pop(ref, None)
                inventory.update(aliases)
            after = self._mention_alias_inventory_signature(agents)
            self._mention_alias_inventory_cache[agents] = (after, cached[1])
        return stats

    def iter_session_batches(self, agent=None, batch_size=512):
        """Yield chronologically ordered, overlaid rows without a full-list copy."""
        if type(batch_size) is not int or not 1 <= batch_size <= 10000:
            raise ValueError("session batch size must be an integer from 1 to 10000")
        enabled = list(self.adapters) if agent is None else [agent] if agent in self.adapters else []
        if not enabled:
            return
        overlays, _ = self._metadata_overlays(enabled)
        title_cache = self._load_title_cache()
        placeholders = ",".join("?" for _ in enabled)
        cursor = self.db.execute(
            f"SELECT * FROM sessions WHERE agent IN ({placeholders}) "
            "ORDER BY agentref_session_order(updatedAt,createdAt,mtime) DESC, ref DESC",
            enabled)
        try:
            while rows := cursor.fetchmany(batch_size):
                result = [dict(row) for row in rows]
                self._overlay_metadata(result, overlays=overlays, title_cache=title_cache)
                yield result
        finally:
            cursor.close()

    def sessions(self, agent=None, limit=None, offset=0):
        if type(offset) is not int or offset < 0:
            raise ValueError("session offset must be a nonnegative integer")
        if limit is not None and (type(limit) is not int or limit < 0):
            raise ValueError("session limit must be a nonnegative integer")
        enabled = list(self.adapters) if agent is None else [agent] if agent in self.adapters else []
        if not enabled:
            return []
        placeholders = ",".join("?" for _ in enabled)
        sql = f"SELECT * FROM sessions WHERE agent IN ({placeholders})"
        params = list(enabled)
        if limit is None and offset == 0:
            rows = self.db.execute(sql, params).fetchall()
        else:
            sql += " ORDER BY agentref_session_order(updatedAt,createdAt,mtime) DESC, ref DESC"
            if limit is None:
                sql += " LIMIT -1 OFFSET ?"
                params.append(offset)
            else:
                sql += " LIMIT ? OFFSET ?"
                params.extend((limit, offset))
            rows = self.db.execute(sql, params).fetchall()
        result = [dict(row) for row in rows]
        self._overlay_metadata(result)
        if limit is None and offset == 0:
            return sorted(result, key=lambda row: (
                _session_order_key(row["updatedAt"], row["createdAt"], row["mtime"]), row["ref"]),
                reverse=True)
        return result

    def filter_rows(self, rows, query, agent=None):
        """Apply Index.matches semantics to an already overlaid ordered row set."""
        query = query.lstrip("@")
        if query in self.adapters:
            return [row for row in rows if row["agent"] == query]
        if ":" in query and query.split(":", 1)[0] in self.adapters:
            agent = query.split(":", 1)[0]
        if agent is not None:
            if agent not in self.adapters:
                return []
            rows = [row for row in rows if row["agent"] == agent]
        exact = [row for row in rows if query in (row["ref"], row["sessionId"],
                                                   row["agent"] + ":" + row["sessionId"])]
        if exact:
            return exact
        alias = query.split(":", 1)[-1].casefold()
        return [row for row in rows if alias in row["title"].casefold()
                or row["sessionId"].casefold().startswith(alias)
                or alias in Path(row["cwd"]).name.casefold()]

    def refs_with_prefix(self, token, agent=None, limit=2):
        """Resolve short public ref tokens without materializing the session list."""
        if (not isinstance(token, str) or not 1 <= len(token) <= 16
                or any(char not in "0123456789abcdef" for char in token)):
            return []
        if type(limit) is not int or not 1 <= limit <= 2:
            raise ValueError("reference prefix limit must be 1 or 2")
        enabled = list(self.adapters) if agent is None else [agent] if agent in self.adapters else []
        if not enabled:
            return []
        placeholders = ",".join("?" for _ in enabled)
        patterns = [f"{name}:{token}*" for name in enabled]
        pattern_where = " OR ".join("ref GLOB ?" for _ in patterns)
        sql = f"SELECT ref,agent FROM sessions WHERE agent IN ({placeholders}) AND ({pattern_where}) ORDER BY ref LIMIT ?"
        rows = self.db.execute(sql, [*enabled, *patterns, limit]).fetchall()
        return [dict(row) for row in rows]

    def matches(self, query, agent=None, limit=None, offset=0, include_total=False):
        if type(offset) is not int or offset < 0:
            raise ValueError("session offset must be a nonnegative integer")
        if limit is not None and (type(limit) is not int or limit < 0):
            raise ValueError("session limit must be a nonnegative integer")
        query = query.lstrip("@")
        if query in self.adapters:
            rows = self.sessions(query, limit=limit, offset=offset)
            if include_total:
                total = self.db.execute("SELECT count(*) FROM sessions WHERE agent=?", (query,)).fetchone()[0]
                return rows, total
            return rows
        if ":" in query and query.split(":", 1)[0] in self.adapters:
            agent = query.split(":", 1)[0]
            row = self.db.execute("SELECT * FROM sessions WHERE agent=? AND ref=?", (agent, query)).fetchone()
            if row is not None:
                if offset or limit == 0:
                    return ([], 1) if include_total else []
                result = self._overlay_metadata([dict(row)])
                return (result, 1) if include_total else result
        enabled = list(self.adapters) if agent is None else [agent] if agent in self.adapters else []
        if not enabled:
            return ([], 0) if include_total else []
        placeholders = ",".join("?" for _ in enabled)
        exact_arms = [
            f"SELECT * FROM sessions WHERE agent IN ({placeholders}) AND ref=?",
            f"SELECT * FROM sessions WHERE agent IN ({placeholders}) AND sessionId=?",
        ]
        exact_params = [*enabled, query, *enabled, query]
        prefix, separator, suffix = query.partition(":")
        if separator and prefix in self.adapters:
            exact_arms.append("SELECT * FROM sessions WHERE agent=? AND sessionId=?")
            exact_params.extend((prefix, suffix))
        exact_refs = [arm.replace("SELECT *", "SELECT ref", 1) for arm in exact_arms]
        exact_union = " UNION ".join(exact_arms)
        exact_ref_union = " UNION ".join(exact_refs)
        # Existence does not need duplicate elimination; keep the indexed arms
        # streaming so a hit can stop at the first matching locator.
        exact_found_sql = f"SELECT 1 FROM ({' UNION ALL '.join(exact_refs)}) LIMIT 1"
        exact_found = self.db.execute(exact_found_sql, exact_params).fetchone() is not None
        if exact_found:
            exact_total = None
            if include_total:
                exact_total = self.db.execute(
                    f"SELECT count(*) FROM ({exact_ref_union})", exact_params).fetchone()[0]
            sql = f"SELECT * FROM ({exact_union}) ORDER BY agentref_session_order(updatedAt,createdAt,mtime) DESC, ref DESC"
            params = list(exact_params)
            if limit is None and offset:
                sql += " LIMIT -1 OFFSET ?"
                params.append(offset)
            elif limit is not None:
                sql += " LIMIT ? OFFSET ?"
                params.extend((limit, offset))
            rows = [dict(row) for row in self.db.execute(sql, params).fetchall()]
            result = self._overlay_metadata(rows)
            return (result, exact_total) if include_total else result
        alias = query.split(":", 1)[-1].casefold()
        if limit is not None or offset:
            page = self._query_page(enabled, alias, limit, offset, include_total)
            if page is not None:
                return page
        rows = self.sessions(agent)
        matches = [r for r in rows if alias in r["title"].casefold()
                   or r["sessionId"].casefold().startswith(alias)
                   or alias in Path(r["cwd"]).name.casefold()]
        page = matches[offset:offset + limit] if limit is not None else matches[offset:]
        return (page, len(matches)) if include_total else page

    def read(self, row):
        if row["agent"] not in self.adapters:
            raise ValueError("source agent is not enabled")
        adapter = self.adapters[row["agent"]]
        return adapter.read_indexed(row)
