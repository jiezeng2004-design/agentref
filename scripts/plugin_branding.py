"""Apply bundled agent marks to an AgentRef plugin manifest and assets."""
import shutil
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "agentref/assets"


def apply_branding(plugin, manifest):
    name = manifest["name"]
    if name not in ("claude", "grok", "opencode", "antigravity", "dsh"):
        raise ValueError("unknown AgentRef plugin")
    target = Path(plugin) / "assets"
    target.mkdir(parents=True, exist_ok=True)
    for theme in ("light", "dark"):
        shutil.copyfile(ASSETS / f"{name}-{theme}.png", target / f"{name}-{theme}.png")
    for filename in ("SOURCES.md", "LICENSE.lobe-icons"):
        shutil.copyfile(ASSETS / filename, target / filename)
    manifest["interface"].update(composerIcon=f"./assets/{name}-light.png",
                                 logo=f"./assets/{name}-light.png",
                                 logoDark=f"./assets/{name}-dark.png")
