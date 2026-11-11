"""trader-entry, offline, on Reliance's real 5-minute bars of Wed 11 Nov 2026."""
import datetime
import json
import os
import tempfile
import unittest

from _load import fix, load, run

entry = load("trader-entry", "entry")
REL = fix("trader-entry", "RELIANCE-2026-11-11-5m.json")


def chart():
    return entry.get_chart("RELIANCE", "5m", offline=REL)


def at(hhmm, day="2026-11-11"):
    return entry.parse_now("%s %s" % (day, hhmm))


def synthetic(day, closes, start=(9, 15)):
    """A flat chart: one 5-minute bar per close, high = low = close."""
    t0 = entry.ts_of(entry.ist_to_utc(datetime.datetime.combine(day, datetime.time(*start))))
    bars = [{"t": t0 + 300 * i, "o": c, "h": c, "l": c, "c": c, "v": 1000} for i, c in enumerate(closes)]
    return {"symbol": "TEST", "meta": {}, "bars": bars, "prev_close": closes[0], "data_time": None}


class Symbols(unittest.TestCase):
    def test_nse_symbol_in_yahoo_symbol_out(self):
        self.assertEqual(entry.yahoo_symbol("reliance"), "RELIANCE.NS")
        self.assertEqual(entry.nse_symbol("M&M.NS"), "M&M")
        self.assertIn("/chart/M%26M.NS?", entry.chart_path("M&M", "1d", "5m"))

    def test_the_chart_carries_the_plain_symbol(self):
        self.assertEqual(chart()["symbol"], "RELIANCE")
        with self.assertRaises(entry.EntryError):
            entry.get_chart("SBIN", "5m", offline=REL)        # the file holds RELIANCE


class TheRule(unittest.TestCase):
    def test_range_still_forming(self):
        res = entry.evaluate(chart(), at("09:22"))
        self.assertEqual((res["status"], res["phase"]), ("waiting", "forming"))
        self.assertIn("1 of 3 range bars closed", res["reason"])

    def test_waiting_while_the_trigger_bar_forms(self):
        res = entry.evaluate(chart(), at("09:32"))
        self.assertEqual(res["status"], "waiting")
        self.assertEqual(res["opening_range"]["high"], 1340.9)
        self.assertEqual(res["opening_range"]["low"], 1330.6)
        self.assertEqual(res["forming"]["bar_start"], "09:30")
        self.assertIsNone(res["trigger"])

    def test_triggered_at_935(self):
        res = entry.evaluate(chart(), at("09:36"))
        self.assertEqual(res["status"], "triggered")
        t = res["trigger"]
        self.assertEqual((t["time"], t["bar_start"], t["bar_index"], t["price"]), ("9:35 AM", "09:30", 3, 1342.8))
        self.assertEqual(t["pct_over"], 0.14)
        self.assertEqual(res["level"], 1340.9)
        self.assertEqual(res["no_entries_before"], "09:30")
        self.assertEqual(res["no_entries_after"], "14:30")
        lines = entry.describe(res)
        self.assertIn("TRIGGERED 9:35 AM at ₹1342.80: the 9:30 bar (bar 3) closed above the range high "
                      "₹1340.90 (+0.14%).", lines)
        self.assertIn("IST", lines[0])

    def test_what_really_happened_after_the_entry(self):
        # the README says it: with a stop at 1,335.70 and a target at 1,349.90, the stop came first, at 11:10
        after = [b for b in chart()["bars"] if entry.to_ist(entry.utc_of(b["t"])).strftime("%H:%M") > "09:30"]
        first = next(b for b in after if b["l"] <= 1335.70 or b["h"] >= 1349.90)
        self.assertEqual(entry.to_ist(entry.utc_of(first["t"])).strftime("%H:%M"), "11:10")
        self.assertLessEqual(first["l"], 1335.70)
        self.assertLess(first["h"], 1349.90)

    def test_a_late_look_says_so(self):
        res = entry.evaluate(chart(), at("10:00"))
        self.assertEqual(res["minutes_since"], 25)
        self.assertTrue(any("That was 25 minutes ago" in ln for ln in entry.describe(res)))

    def test_level_setup(self):
        res = entry.evaluate(chart(), at("15:25"), setup="level", level=1343.0)
        self.assertEqual(res["level"], 1343.0)
        self.assertIn(res["status"], ("triggered", "expired"))

    def test_expires_at_the_last_entry_time(self):
        day = datetime.date(2026, 11, 11)
        flat = synthetic(day, [100.0] * 70)                   # never closes above its own range high
        res = entry.evaluate(flat, at("14:31"))
        self.assertEqual(res["status"], "expired")
        self.assertIn("by 14:30, the last time for a new entry", res["reason"])
        res = entry.evaluate(flat, at("14:00"))
        self.assertEqual(res["status"], "waiting")

    def test_no_entries_before_the_window(self):
        day = datetime.date(2026, 11, 11)
        up = synthetic(day, [100.0, 100.0, 100.0, 101.0, 101.0])   # the 9:30 bar closes above at 9:35
        cfg = {"no_entries_before": "09:45", "no_entries_after": "14:30"}
        res = entry.evaluate(up, at("09:41"), cfg=cfg)
        self.assertEqual(res["status"], "waiting")
        self.assertIn("no entries before 9:45", res["reason"])

    def test_holiday_and_weekend(self):
        res = entry.evaluate(chart(), at("10:00", "2026-11-10"))
        self.assertEqual(res["status"], "no-data")
        self.assertEqual(res["reason"], "NSE is closed today (NSE holiday: Diwali Balipratipada)")
        self.assertEqual(res["next_open"], "2026-11-11 09:15")
        res = entry.evaluate(chart(), at("10:00", "2026-11-07"))
        self.assertIn("weekend", res["reason"])
        self.assertEqual(res["next_open"], "2026-11-09 09:15")

    def test_pre_open(self):
        res = entry.evaluate(chart(), at("09:05"))
        self.assertEqual(res["phase"], "pre-open")
        self.assertIn("NSE opens at 9:15", res["reason"])

    def test_no_shorts(self):
        with tempfile.TemporaryDirectory() as d:
            code, _, err = run(entry, ["check", "RELIANCE", "--offline", REL, "--side", "sell"], cwd=d)
            self.assertEqual(code, 1)
            self.assertIn("longs only", err)


class Cli(unittest.TestCase):
    def test_check_writes_the_entry(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(entry, ["check", "RELIANCE", "--offline", REL, "--now", "2026-11-11 09:36", "--write"],
                               cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("This is the moment to get in, if you take the trade. Nothing was placed.", out)
            with open(os.path.join(d, "trader", "entry.json"), encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertEqual(doc["symbol"], "RELIANCE")
            self.assertEqual(doc["status"], "triggered")
            self.assertEqual((doc["time"], doc["price"], doc["bar_index"]), ("9:35 AM", 1342.8, 3))
            self.assertEqual(doc["opening_range"], {"high": 1340.9, "low": 1330.6, "minutes": 15})

    def test_watch_replays_the_morning(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(entry, ["watch", "RELIANCE", "--offline", REL, "--now", "2026-11-11 09:16"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("opening range set: high ₹1340.90, low ₹1330.60", out)
            self.assertIn("TRIGGERED: closed above ₹1340.90 (+0.14%)", out)
            self.assertTrue(os.path.exists(os.path.join(d, "trader", "entry.json")))

    def test_watchlist_table(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "trader"))
            os.makedirs(os.path.join(d, "charts"))
            with open(REL, encoding="utf-8") as fh:
                text = fh.read()
            with open(os.path.join(d, "charts", "RELIANCE.json"), "w", encoding="utf-8") as fh:
                fh.write(text)
            with open(os.path.join(d, "trader", "watchlist.json"), "w", encoding="utf-8") as fh:
                json.dump({"hits": [{"symbol": "RELIANCE"}]}, fh)
            code, out, _ = run(entry, ["watchlist", "--offline", "charts", "--now", "2026-11-11 09:36"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("1 of 1 triggered.", out)
            self.assertIn("₹1342.80", out)


if __name__ == "__main__":
    unittest.main()
