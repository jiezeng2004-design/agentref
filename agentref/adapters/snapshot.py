"""Read-only adapters for multi-file and database-backed session stores."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
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
    def scan_files(self, paths, reader):
        self.scan_errors = []
        for path in paths:
            try:
                result = reader(path)
                if isinstance(result, list):
                    yield from result
                elif result is not None:
                    yield result
            except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
                self.scan_errors.append(self.agent + ": source metadata unavailable or unsupported")

    def checked(self, path):
        path = Path(path)
        resolved = path.resolve()
        if path.is_symlink() or not any(resolved.is_relative_to(r) for r in self.roots):
            raise ValueError("source escaped configured session root")
        # Reject symlink/junction ancestors, including links to an in-root target.
        for parent in (path, *path.parents):
            if parent in self.roots:
                break
            if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
                raise ValueError("linked session source")
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
