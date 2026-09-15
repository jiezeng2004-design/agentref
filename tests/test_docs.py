from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_every_script_is_classified(self):
        text = (ROOT / "docs/SCRIPTS.md").read_text(encoding="utf-8")
        documented = set(re.findall(r"`(scripts/[^`]+\.(?:py|mjs|cjs))`", text))
        actual = {path.relative_to(ROOT).as_posix() for path in (ROOT / "scripts").iterdir()
                  if path.suffix in (".py", ".mjs", ".cjs")}
        self.assertEqual(documented, actual)

    def test_local_documentation_links_exist(self):
        for path in [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]:
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                with self.subTest(document=path.name, target=target):
                    self.assertTrue((path.parent / target.split("#", 1)[0]).is_file())
