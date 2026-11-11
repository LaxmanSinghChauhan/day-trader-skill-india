"""trader-timemachine, offline, on Reliance's real last 60 days of 5-minute bars (to Wed 11 Nov 2026)."""
import json
import os
import tempfile
import unittest

from _load import fix, load, run

tm = load("trader-timemachine", "timemachine")
REL60 = fix("trader-timemachine", "RELIANCE-60d5m.json.gz")
PLAN = {"symbol": "RELIANCE", "side": "buy", "date": "2026-11-11", "setup": "orb", "entry": 1342.8,
        "entry_time": "9:35 AM", "entry_bar": 3, "stop": 1335.7, "target": 1349.9, "tick": 0.1,
        "opening_range": {"high": 1340.9, "low": 1330.6, "minutes": 15}, "stop_rule": "or_mid",
        "interval": "5m", "flat_by": "15:10"}
NOW = tm.parse_now("2026-11-11 21:00")
_cache = {}


def doc(**kw):
    key = json.dumps(kw, sort_keys=True)
    if key not in _cache:
        text = tm.read_offline(REL60, "RELIANCE")
        plan = tm.normalize_plan(dict(PLAN, **kw.pop("plan", {})))
        _cache[key] = tm.time_machine(text, plan, NOW, source="offline", **kw)
    return _cache[key]


class Window(unittest.TestCase):
    def test_the_intraday_window(self):
        self.assertEqual((tm.SESSION_BARS, tm.OPEN_MIN, tm.CLOSE_MIN), (72, 9 * 60 + 15, 15 * 60 + 15))
        self.assertEqual(tm.clock12(tm.OPEN_MIN + 5 * 4), "9:35 AM")

    def test_pool_is_full_sessions_only(self):
        d = doc()
        m = d["mc"]
        self.assertEqual((m["pool_sessions"], m["pool_from"], m["pool_to"]), (58, "2026-08-14", "2026-11-09"))
        self.assertEqual(d["data"]["short_sessions_left_out"], [{"date": "2026-10-15", "bars": 70}])
        self.assertEqual(d["data"]["symbol"], "RELIANCE")

    def test_until_defaults_to_the_flat_by(self):
        m = doc()["mc"]
        self.assertEqual((m["until"], m["bars_left"]), ("15:10", 67))
        m = doc(until="15:15")["mc"]
        self.assertEqual((m["until"], m["bars_left"]), ("15:15", 68))
        with self.assertRaises(tm.TMError):
            doc(until="15:30")                      # past the window


class Replays(unittest.TestCase):
    def test_ten_thousand_replays_seed_19(self):
        m = doc()["mc"]
        self.assertEqual((m["replays"], m["seed"], m["window"]), (10000, 19, 2))
        self.assertEqual((m["p_target"], m["p_stop"], m["p_neither"], m["p_green"]), (0.4816, 0.4887, 0.0297, 0.4969))
        self.assertEqual((m["median_close"], m["p5_close"], m["p95_close"]), (1342.03, 1321.53, 1363.82))
        self.assertEqual(m["avg_R"], -0.007)
        self.assertEqual(len(m["bands"]), 68)
        self.assertEqual(len(m["sample_paths"]), tm.SAMPLE_PATHS)

    def test_verdict(self):
        d = doc()
        self.assertEqual(d["verdict"], "Close to a coin flip: target first 48.2 % vs stop first 48.9 %.")
        self.assertEqual(d["verdict_notes"], [])

    def test_another_seed_other_numbers_same_story(self):
        m = doc(seed=7, replays=2000)["mc"]
        self.assertNotEqual(m["p_target"], 0.4816)
        self.assertLess(abs(m["p_target"] - m["p_stop"]), 0.08)

    def test_history_of_the_same_rule(self):
        h = doc()["history"]
        self.assertEqual((h["sessions"], h["triggered"], h["target"], h["stop"], h["close"]), (58, 30, 13, 11, 6))
        self.assertEqual(h["avg_R"], 0.017)
        self.assertEqual(h["rule"], {"setup": "orb", "or_minutes": 15, "stop_rule": "or_mid", "target_r": 1.0,
                                     "tick_paise": 10})
        for t in h["trades"]:                       # every stop and target sits on the 0.10 grid
            self.assertEqual(round(t["stop"] * 100) % 10, 0, t)
            self.assertEqual(round(t["target"] * 100) % 10, 0, t)

    def test_report_and_chart(self):
        lines = tm.report(doc())
        self.assertEqual(lines[0], "RELIANCE buy, Wednesday 2026-11-11: entry 1342.80 at 9:35 AM (bar 3), stop 1335.70, "
                                   "target 1349.90 (1R, risk 7.10 a share).")
        self.assertIn("  neither        3.0 %    still open at 3:10 PM", lines)
        self.assertTrue(any("fired 30 times: 13 target, 11 stop, 6 neither" in ln for ln in lines))
        chart = tm.render_chart(doc())
        self.assertIn("target", chart[6] + chart[5] + chart[4])
        self.assertIn("9:35", chart[-2])
        self.assertIn("3:10", chart[-2])


class Ticks(unittest.TestCase):
    def test_tick_helpers(self):
        self.assertEqual(tm.tick_away(1335.75, True, 10), 1335.7)
        self.assertEqual(tm.tick_away(1335.75, False, 10), 1335.8)
        self.assertEqual(tm.tick_near(1349.95, 10), 1350.0)
        self.assertEqual(tm.slab_tick_paise(249.99), 1)
        self.assertEqual(tm.slab_tick_paise(1000), 5)
        self.assertEqual(tm.slab_tick_paise(1342.8), 10)
        self.assertEqual(tm.slab_tick_paise(49930), 500)

    def test_plan_tick(self):
        self.assertEqual(tm.plan_tick_paise(0.1, [1342.8, 1335.7, 1349.9]), 10)
        self.assertEqual(tm.plan_tick_paise(None, [1065.65, 1060.0, 1076.95]), 5)     # worked out from the prices
        self.assertEqual(tm.normalize_plan(PLAN)["tick"], 0.1)


class Plans(unittest.TestCase):
    def test_normalize(self):
        p = tm.normalize_plan(dict(PLAN, symbol="reliance.ns"))
        self.assertEqual((p["symbol"], p["entry_bar"], p["entry_time"], p["target_r"]), ("RELIANCE", 3, "9:35 AM", 1.0))
        self.assertEqual(tm.normalize_plan(dict(PLAN, symbol="M&M"))["symbol"], "M&M")

    def test_refusals(self):
        with self.assertRaises(tm.TMError):
            tm.normalize_plan(dict(PLAN, stop=1350.0))
        with self.assertRaises(tm.TMError):
            tm.normalize_plan(dict(PLAN, entry_time="9:37 AM", entry_bar=None))
        with self.assertRaises(tm.TMError) as cm:
            tm.normalize_plan(dict(PLAN, entry_time="3:15 PM", entry_bar=None))
        self.assertIn("between 9:20 AM and 3:10 PM", str(cm.exception))
        with self.assertRaises(tm.TMError) as cm:
            doc(plan={"date": "2026-08-20"})
        self.assertIn("needs at least 20", str(cm.exception))
        with self.assertRaises(tm.TMError) as cm:
            doc(plan={"symbol": "SBIN"})
        self.assertIn("the data is for RELIANCE", str(cm.exception))

    def test_yahoo_url(self):
        self.assertEqual(tm.chart_url("M&M"), "https://query2.finance.yahoo.com/v8/finance/chart/M%26M.NS?range=60d&interval=5m")


class Cli(unittest.TestCase):
    def test_run_and_chart(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "trader"))
            with open(os.path.join(d, "trader", "plan.json"), "w", encoding="utf-8") as fh:
                json.dump(PLAN, fh)
            code, out, _ = run(tm, ["run", "--offline", REL60, "--now", "2026-11-11 21:00", "--write"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("  target first   48.2 %", out)
            self.assertIn("  stop first     48.9 %", out)
            self.assertIn("Charges are not counted.", out)
            code, out, _ = run(tm, ["chart", "--from"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("RELIANCE 2026-11-11, 2,000 replay paths from the 9:35 AM entry (seed 19)", out)


if __name__ == "__main__":
    unittest.main()
