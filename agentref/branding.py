"""Bundled agent marks; MCP icons never need an external image request."""
import base64
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=8)
def agent_icons(agent):
    if agent not in ("claude", "grok", "opencode", "antigravity", "dsh"):
        return []
    return [{"src": "data:image/png;base64," + base64.b64encode(
                (Path(__file__).parent / "assets" / f"{agent}-{theme}.png").read_bytes()
            ).decode("ascii"), "mimeType": "image/png", "theme": theme}
            for theme in ("light", "dark")]
