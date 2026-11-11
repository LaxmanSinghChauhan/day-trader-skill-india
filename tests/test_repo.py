import json
import os
import re
import unittest

from _load import ROOT

# the eleven folders, skill for skill the US pack's eleven (the Pelosi Tracker became the Big Bull Tracker)
SKILLS = ["trader-scanner", "trader-news", "trader-entry", "trader-exit", "trader-timemachine",
          "trader-risk", "trader-budget", "trader-broker", "trader-alerts", "trader-analyst",
          "trader-bigbull"]
TOOLS = {"trader-scanner": "scan.py", "trader-news": "news.py", "trader-entry": "entry.py", "trader-exit": "exit.py",
         "trader-timemachine": "timemachine.py", "trader-risk": "check.py", "trader-budget": "size.py",
         "trader-broker": "ticket.py", "trader-alerts": "alerts.py", "trader-analyst": "facts.py",
         "trader-bigbull": "deals.py"}
ABOUT = ("11 Claude skills for day trading Indian stocks: scan thousands of NSE charts, track breaking news, time "
         "every entry and exit, and replay every outcome before you risk a rupee.")
# skills on the way to an order carry the safety block
ORDER_PATH = ["trader-scanner", "trader-entry", "trader-exit", "trader-timemachine", "trader-budget",
              "trader-bigbull", "trader-risk", "trader-broker", "trader-alerts"]
# words that belong to the US pack only: none may be left in a skill or a tool
US_ONLY = ["Alpaca", "alpaca", "place_stock_order", "NYSE", "Nasdaq", "New York", "SEC EDGAR", "EDGAR", "sec_user_agent",
           "FINRA", "pdt_guard", "trader-pelosi", "House Clerk", "_usd", "TSLA", "AAPL"]


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else ""), text


def every_text_file():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in files:
            if f.endswith((".md", ".py", ".json", ".csv", ".txt", ".xml")) or f == "LICENSE":
                yield os.path.join(base, f)


class Repo(unittest.TestCase):
    def test_eleven_skill_folders_at_the_root(self):
        found = sorted(d for d in os.listdir(ROOT)
                       if os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
        self.assertEqual(found, sorted(SKILLS))

    def test_root_holds_the_pack_and_nothing_else(self):
        root = sorted(d for d in os.listdir(ROOT) if not d.startswith(".git") and d != ".DS_Store")
        self.assertEqual(root, sorted([".claude-plugin", "LICENSE", "README.md", "tests"] + SKILLS))

    def test_every_skill_has_its_tool(self):
        for s, tool in TOOLS.items():
            self.assertTrue(os.path.isfile(os.path.join(ROOT, s, tool)), "%s/%s" % (s, tool))
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn('"${CLAUDE_SKILL_DIR}/%s"' % tool, text, s)

    def test_frontmatter_name_and_description(self):
        for s in SKILLS:
            fm, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("name: %s\n" % s, fm + "\n", s)
            self.assertRegex(fm, r"description: ", s)
            self.assertGreater(len(fm), 200, "%s description is too thin" % s)
            self.assertGreater(len(text.splitlines()), 60, s)

    def test_order_path_skills_carry_the_safety_rule(self):
        for s in ORDER_PATH:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            low = " ".join(text.lower().split())
            self.assertIn("not financial advice", low, s)
            self.assertIn("yes", low, s)

    def test_plugin_manifest_points_at_the_root_skills(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as fh:
            plugin = json.load(fh)
        self.assertEqual(plugin["name"], "day-trader-skill-india")
        self.assertEqual(plugin["skills"], "./")
        self.assertEqual(plugin["description"], ABOUT)
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as fh:
            market = json.load(fh)
        self.assertEqual(market["name"], "day-trader-skill-india")
        self.assertEqual(market["plugins"][0]["name"], "day-trader-skill-india")

    def test_readme(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = " ".join(fh.read().split())
        self.assertTrue(readme.startswith("# The Day Trader skill, India edition"))
        for line in (ABOUT,
                     "https://github.com/LaxmanSinghChauhan/day-trader-skill-india install skill",
                     "/plugin marketplace add LaxmanSinghChauhan/day-trader-skill-india",
                     "/plugin install day-trader-skill-india@day-trader-skill-india",
                     "## Fine print", "Jake Schincariol", "v1-original"):
            self.assertIn(line, readme)
        for s in SKILLS:
            self.assertIn("/" + s, readme, s)

    def test_the_example_in_the_readme_is_the_tested_one(self):
        # every number here is asserted in the tests of the tool that makes it
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = " ".join(fh.read().split())
        for number in ("18 had closed above", "1,330.60 to 1,340.90", "1,342.80", "1,335.70", "1,349.90",
                       "48.2 %", "48.9 %", "fired 30 times, 13 hit the target, 11 the stop, 6 neither",
                       "27 shares (₹36,255.60)", "₹191.70", "₹38.31", "₹230.01", "₹153.25"):
            self.assertIn(number, readme, number)

    def test_licence_keeps_both_copyrights(self):
        with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("MIT License", text)
        self.assertIn("Jake Schincariol", text)
        self.assertIn("day-trader-skill-india contributors", text)

    def test_no_em_dashes(self):
        for path in every_text_file():
            rel = os.path.relpath(path, ROOT)
            if rel.startswith(os.path.join("tests", "fixtures")):
                continue                    # fixtures are real data, kept as published
            with open(path, encoding="utf-8", errors="replace") as fh:
                self.assertNotIn(chr(0x2014), fh.read(), rel)

    def test_nothing_american_is_left_in_the_skills(self):
        for s in SKILLS:
            folder = os.path.join(ROOT, s)
            for f in sorted(os.listdir(folder)):
                if not f.endswith((".py", ".json", ".txt")) and f != "SKILL.md":
                    continue
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    text = fh.read()
                for word in US_ONLY:
                    if word == "trader-pelosi" or (s == "trader-bigbull" and word in ("House Clerk",)):
                        continue
                    self.assertNotIn(word, text, "%s/%s still says %r" % (s, f, word))
                self.assertNotRegex(text, r"\$\d", "%s/%s has a dollar amount" % (s, f))

    def test_every_tool_runs_on_python_3_8(self):
        # no 3.9+ only modules or syntax in the tools (the README promises 3.8)
        for s, tool in TOOLS.items():
            with open(os.path.join(ROOT, s, tool), encoding="utf-8") as fh:
                src = fh.read()
            for bad in ("import zoneinfo", "from zoneinfo", ".removeprefix(", ".removesuffix("):
                self.assertNotIn(bad, src, "%s/%s" % (s, tool))
            self.assertNotRegex(src, r"(?m)^\s+match \w+.*:$", "%s/%s" % (s, tool))
            for generic in ("list[", "dict[", "tuple["):
                self.assertNotRegex(src, r"(?<![\w.\"'])%s" % re.escape(generic), "%s/%s" % (s, tool))
            self.assertNotIn(":=", src, "%s/%s" % (s, tool))

    def test_every_tool_checks_https_certificates(self):
        for s, tool in TOOLS.items():
            with open(os.path.join(ROOT, s, tool), encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotIn("_create_unverified_context", src, tool)
            self.assertNotIn("CERT_NONE", src, tool)
            if "urlopen" in src:
                self.assertIn("ssl_context()", src, tool)

    def test_day_trading_limits_ship_in_the_example_config(self):
        with open(os.path.join(ROOT, "trader-budget", "config.example.json")) as fh:
            cfg = json.load(fh)
        for k in ("max_loss_per_trade_inr", "max_daily_loss_inr", "max_trades_per_day",
                  "min_reward_risk", "require_stop", "no_entries_after", "flat_by"):
            self.assertIn(k, cfg, k)
        self.assertIs(cfg["require_stop"], True)
        self.assertIs(cfg.get("allow_short", False), False)
        self.assertIs(cfg.get("allow_margin", False), False)
        self.assertEqual((cfg["exchange"], cfg["product"], cfg["broker"]), ("NSE", "MIS", "zerodha"))

    def test_paper_trading_is_the_default(self):
        with open(os.path.join(ROOT, "trader-budget", "config.example.json")) as fh:
            cfg = json.load(fh)
        self.assertIs(cfg["paper"], True)
        self.assertIs(cfg.get("allow_options", False), False)

    def test_no_keys_in_the_broker_example(self):
        with open(os.path.join(ROOT, "trader-broker", "claude_desktop_config.example.json")) as fh:
            text = fh.read()
        self.assertIn("https://mcp.kite.trade/mcp", text)
        self.assertIn("NEVER_IN_CHAT", text)
        self.assertNotRegex(text, r"[a-z0-9]{16,}")          # nothing that looks like a real key


if __name__ == "__main__":
    unittest.main()
