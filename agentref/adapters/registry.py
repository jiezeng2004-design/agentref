import os
from pathlib import Path
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .grok import GrokAdapter
from .opencode import OpenCodeAdapter
from .antigravity import AntigravityAdapter
from .dsh import DshAdapter

ADAPTERS = {a.agent: a for a in (ClaudeAdapter, CodexAdapter, GrokAdapter, OpenCodeAdapter, AntigravityAdapter, DshAdapter)}


def default_adapters():
    home = Path.home()
    codex = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude"))
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    return [ClaudeAdapter([claude / "projects"]),
            CodexAdapter([codex / "sessions", codex / "archived_sessions"]),
            GrokAdapter([home / ".grok/sessions"]),
            OpenCodeAdapter([data / "opencode"]),
            AntigravityAdapter([home / ".gemini/antigravity/conversations", home / ".gemini/antigravity-cli/conversations"]),
            DshAdapter([Path(os.environ.get("DSH_HOME", home / ".dsh"))])]
