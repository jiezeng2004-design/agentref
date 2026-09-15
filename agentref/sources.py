"""Source descriptions, independent of adapters and host discovery.

Host visibility is policy, not source support: Codex is a readable source but
is intentionally absent from the Codex-host agent-entry menu.
"""
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class Source:
    label: str
    format: str
    codex_menu_label: str | None = None


SOURCES = MappingProxyType({
    "claude": Source("Claude", "Claude content blocks", "Claude Code"),
    "codex": Source("Codex", "Codex rollout JSONL"),
    "grok": Source("Grok", "Grok ACP updates/raw chat fallback", "Grok"),
    "opencode": Source("OpenCode", "OpenCode SQLite message/part", "OpenCode"),
    "antigravity": Source("Antigravity", "Antigravity SQLite Step protobuf (experimental)", "Antigravity"),
    "dsh": Source("DSH", "DSH session JSONL / JSONL.zstd", "DSH · DeepSeek Harness"),
})


def supported_formats():
    return [source.format for source in SOURCES.values()]
