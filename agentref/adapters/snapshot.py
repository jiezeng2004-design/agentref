"""Read-only adapters for multi-file and database-backed session stores."""
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import stat
from .base import BaseAdapter


def timestamp(value):
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and value:
        try:
            if value > 100_000_000_000:
                value /= 1000
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError) as exc:
            # Keep invalid metadata inside the adapter's per-source error boundary.
            raise ValueError("unsupported source timestamp") from exc
    return ""


class SnapshotAdapter(BaseAdapter):
    index_mode = "snapshot"
    metadata_cache_enabled = False
    metadata_uses_wal = False

    def __init__(self, roots):
        super().__init__(roots)
        self.scan_errors = []
        self.metadata_reuse = None

    def scan_files(self, paths, reader, path_roots=None):
        self.scan_errors = []
        reuse = self.metadata_reuse
        path_roots = path_roots or {}
        for path in paths:
            try:
                signature = (self.metadata_signature(path, root=path_roots.get(path))
                             if reuse is not None else None)
                if reuse is not None and reuse(path, signature, False):
                    continue
                result = reader(path)
                if isinstance(result, (list, Iterator)):
                    items = result
                elif result is not None:
                    items = (result,)
                else:
                    items = ()
                source_paths = []
                for item in items:
                    source_path = getattr(item, "sourcePath", None)
                    if isinstance(source_path, str):
                        source_paths.append(source_path)
                    yield item
                if (reuse is not None
                        and signature == self.metadata_signature(path, root=path_roots.get(path))):
                    reuse(path, signature, True, tuple(source_paths))
            except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
                self.scan_errors.append(self.agent + ": source metadata unavailable or unsupported")

    def metadata_dependencies(self, path):
        """Files whose changes can affect this source's listed metadata."""
        path = Path(path)
        if self.metadata_uses_wal:
            return (path, Path(str(path) + "-wal"))
        return (path,)

    def metadata_signature(self, path, root=None):
        signature = []
        for dependency in self.metadata_dependencies(path):
            try:
                checked = self.checked(dependency, root=root)
                stat = checked.stat()
                signature.append((str(checked), stat.st_dev, stat.st_ino,
                                  stat.st_mtime_ns, stat.st_size))
            except FileNotFoundError:
                signature.append((str(dependency), None))
        return tuple(signature)

    @staticmethod
    def _stat_is_symlink_or_junction(info):
        if stat.S_ISLNK(info.st_mode):
            return True
        mount_point = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)
        return getattr(info, "st_reparse_tag", None) == mount_point

    @staticmethod
    def _is_symlink_or_junction(path):
        try:
            info = os.lstat(path)
        except OSError:
            return False
        return SnapshotAdapter._stat_is_symlink_or_junction(info)

    def checked(self, path, root=None):
        path = Path(path)
        # Scan results are built from the already-resolved configured roots.
        # Avoid resolving each ancestor again for this common path while still
        # rejecting links and junctions anywhere below the trusted root.
        lexical_root = None
        relative_parts = None
        if root in self.roots:
            try:
                relative_parts = path.relative_to(root).parts
                lexical_root = root
            except ValueError:
                raise ValueError("source escaped configured session root")
        else:
            for candidate in self.roots:
                try:
                    relative_parts = path.relative_to(candidate).parts
                    lexical_root = candidate
                    break
                except ValueError:
                    continue
        if lexical_root is not None:
            if ".." in relative_parts or self._is_symlink_or_junction(path):
                raise ValueError("source escaped configured session root")
            parent = lexical_root
            for part in relative_parts[:-1]:
                parent /= part
                if self._is_symlink_or_junction(parent):
                    raise ValueError("linked session source")
            return path

        # Preserve support for system aliases such as macOS /var -> /private/var.
        resolved = path.resolve()
        if path.is_symlink() or not any(resolved.is_relative_to(r) for r in self.roots):
            raise ValueError("source escaped configured session root")
        # Reject symlink/junction ancestors, including links to an in-root target.
        for parent in (path, *path.parents):
            if parent in self.roots:
                break
            if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
                raise ValueError("linked session source")
            # A configured root may be reached through a system ancestor alias
            # (macOS /var -> /private/var). Stop at that same root, but only
            # after rejecting links inside the session path itself.
            if parent.resolve() in self.roots:
                break
        return resolved

    @contextmanager
    def database(self, path):
        path = self.checked(path)
        # mode=ro includes committed WAL data; immutable=1 would hide live changes.
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            yield db
        finally:
            db.close()

    def read_indexed(self, row):
        return self.readSession(self.checked(row["sourcePath"]))
