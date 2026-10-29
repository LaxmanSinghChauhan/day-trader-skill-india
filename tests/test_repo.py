"""The pack itself: every skill folder is well formed, every script compiles, no secrets slipped in."""
import json
import py_compile
import re
import unittest

from _util import ROOT

SKILLS = sorted(p.parent for p in ROOT.glob("*/SKILL.md"))


class Repo(unittest.TestCase):
    def test_twelve_skills_with_matching_names(self):
        self.assertEqual(len(SKILLS), 12)
        for d in SKILLS:
            text = (d / "SKILL.md").read_text()
            self.assertTrue(text.startswith("---\n"), d)
            front = text.split("---")[1]
            self.assertIn(f"name: {d.name}\n", front)
            self.assertIn("description:", front)
            self.assertIn("## Safety", text, d)

    def test_scripts_compile(self):
        for py in list(ROOT.glob("*/*.py")) + list(ROOT.glob("nse_core/*.py")):
            py_compile.compile(str(py), doraise=True)

    def test_plugin_manifests(self):
        plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(plugin["name"], market["plugins"][0]["name"])

    def test_no_secrets(self):
        pattern = re.compile(r"(api_secret|access_token)\s*[=:]\s*['\"][A-Za-z0-9]{16,}")
        for f in ROOT.rglob("*"):
            if f.is_file() and ".git" not in f.parts and f.suffix in {".py", ".md", ".json"}:
                self.assertIsNone(pattern.search(f.read_text(errors="ignore")), f)

    def test_paper_is_the_default(self):
        from nse_core import state
        self.assertTrue(state.DEFAULTS["paper"])
        self.assertTrue(json.loads((ROOT / "config.example.json").read_text())["paper"])


if __name__ == "__main__":
    unittest.main()
