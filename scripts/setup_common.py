"""Small shared primitives for explicit local host setup, not a host installer."""
import os
from pathlib import Path
import tempfile


def local_executable(repo, platform=None):
    platform = os.name if platform is None else platform
    return Path(repo) / ".venv" / ("Scripts/agentref.exe" if platform == "nt" else "bin/agentref")


def check_target(path):
    """Refuse linked targets/ancestors before reading or replacing a config."""
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise ValueError("Reparse-point target refused: " + str(path))
    if path.exists() and not path.is_file():
        raise ValueError("Expected a regular configuration file: " + str(path))


def read_current(path):
    path = Path(path)
    check_target(path)
    return path.read_bytes() if path.exists() else b""


def atomic_write(path, before, after):
    """Compare, stage beside target, recheck and replace; no config backups.

This detects observed concurrent changes, not an OS-level compare-and-swap.
The host should be closed while applying configuration changes.
"""
    path = Path(path)
    if read_current(path) != before:
        raise ValueError("Concurrent change: " + str(path))
    if before == after:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".agentref-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        if read_current(path) != before:
            raise ValueError("Concurrent change: " + str(path))
        os.replace(temporary, path)
        if read_current(path) != after:
            raise ValueError("Post-write verification failed: " + str(path))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
