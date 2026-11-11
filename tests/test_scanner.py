"""trader-scanner, offline, on real data: NSE's equity list and the Nifty 50's bars of Wed 11 Nov 2026."""
import datetime
import json
import os
import tempfile
import unittest

from _load import fix, load, run

scan = load("trader-scanner", "scan")
SYMDIR = fix("trader-scanner", "symdir")
WALL = fix("trader-scanner", "wall5m-2026-11-11.json.gz")
DAILY = fix("trader-scanner", "daily")


def texts(*names):
    out = {}
    for n in names:
        with open(os.path.join(SYMDIR, n), encoding="utf-8") as fh:
            out[n] = fh.read()
    return out


class Universe(unittest.TestCase):
    def test_keeps_series_eq_only(self):
        kept, counts, created = scan.build_universe(texts("EQUITY_L.csv"))
        self.assertEqual(len(kept), 2397)
        self.assertEqual(counts["rows"], 2633)
        self.assertEqual(counts["series BE"], 202)
        self.assertEqual(counts["series BZ"], 34)
        self.assertIsNone(created)
        names = dict(kept)
        self.assertEqual(names["RELIANCE"], "Reliance Industries Limited")
        self.assertIn("M&M", names)            # symbols with & and - are real NSE symbols
        self.assertIn("BAJAJ-AUTO", names)

    def test_nifty500_filter(self):
        kept, counts, _ = scan.build_universe(texts("EQUITY_L.csv", "ind_nifty500list.csv"), "nifty500")
        self.assertEqual(len(kept), 495)
        self.assertEqual(counts["not in the Nifty 500"], 1902)

    def test_classify(self):
        self.assertEqual(scan.classify({"SYMBOL": "X", "NAME OF COMPANY": "X Ltd", "SERIES": "EQ"}), "keep")
        self.assertEqual(scan.classify({"SYMBOL": "X", "NAME OF COMPANY": "X Ltd", "SERIES": "BE"}), "series BE")
        self.assertEqual(scan.classify({"SYMBOL": "", "NAME OF COMPANY": "X Ltd", "SERIES": "EQ"}), "no symbol or name")

    def test_not_an_nse_file(self):
        with self.assertRaises(scan.ScanError):
            scan.build_universe({"EQUITY_L.csv": "Symbol|Security Name\nAAPL|Apple\n"})

    def test_cli_writes_the_universe(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(scan, ["universe", "--offline", SYMDIR, "--index", "nifty500"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("Kept 495 NSE stocks in series EQ that are in the Nifty 500.", out)
            with open(os.path.join(d, "trader", "universe.txt"), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            self.assertEqual(len(lines), 495)
            self.assertIn("M&M|Mahindra & Mahindra Limited", lines)


class Helpers(unittest.TestCase):
    def test_yahoo_symbols(self):
        self.assertEqual(scan.to_yahoo("reliance"), "RELIANCE.NS")
        self.assertEqual(scan.to_yahoo("RELIANCE.NS"), "RELIANCE.NS")
        self.assertEqual(scan.from_yahoo("M&M.NS"), "M&M")
        self.assertIn("M%26M.NS", scan.chart_path("M&M", "1d", "5m"))
        self.assertIn("M%26M.NS,BAJAJ-AUTO.NS", scan.spark_path(["M&M", "BAJAJ-AUTO"], "3mo", "1d"))

    def test_india_time_has_no_daylight_saving(self):
        utc = datetime.datetime(2026, 11, 11, 4, 30)
        self.assertEqual(scan.to_ist(utc), datetime.datetime(2026, 11, 11, 10, 0))
        self.assertEqual(scan.ist_to_utc(datetime.datetime(2026, 6, 1, 10, 0)), datetime.datetime(2026, 6, 1, 4, 30))
        self.assertEqual(scan.parse_now("2026-11-11 10:00"), utc)
        self.assertEqual(scan.parse_now("2026-11-11T04:30:00Z"), utc)

    def test_nse_calendar(self):
        self.assertEqual(scan.trading_day(datetime.date(2026, 11, 10)), (False, "NSE holiday: Diwali Balipratipada"))
        self.assertEqual(scan.trading_day(datetime.date(2026, 11, 8)), (False, "weekend"))
        self.assertEqual(scan.trading_day(datetime.date(2026, 11, 11)), (True, ""))
        self.assertEqual(scan.session(datetime.date(2026, 11, 11)), (datetime.time(9, 15), datetime.time(15, 30)))
        self.assertIsNone(scan.session(datetime.date(2026, 1, 26)))

    def test_rupees_with_indian_grouping(self):
        self.assertEqual(scan.money(1234567.5), "₹12,34,567.50")
        self.assertEqual(scan.money(1342.8), "₹1,342.80")
        self.assertEqual(scan.money(285), "₹285.00")
        self.assertEqual(scan._floors(50, 0, 20), "₹50+ and ₹20 crore+ traded")

    def test_setups_from_closes(self):
        flat = [100.0] * 29
        tags, nums = scan.find_setups(flat + [101.0])
        self.assertIn("breakout_20d", tags)
        self.assertEqual(scan.find_setups(flat + [100.0])[0], [])
        falling = [100.0 - i for i in range(30)]
        self.assertIn("oversold", scan.find_setups(falling)[0])


class Daily(unittest.TestCase):
    def test_pre_market_scan_of_the_nifty_50(self):
        data, failed = scan.load_offline(DAILY)
        self.assertEqual(len(data), 50)
        now = scan.parse_now("2026-11-11 08:30")
        hits, counts, last = scan.scan_daily(data, sorted(data), now, 50.0, 0, 20 * scan.CRORE)
        self.assertEqual(last, datetime.date(2026, 11, 9))     # 10 Nov was a holiday; 11 Nov has not closed yet
        self.assertEqual(counts["scanned"], 50)
        self.assertEqual(len(hits), 19)
        self.assertEqual(hits[0]["symbol"], "ICICIBANK")       # most rupees traded first
        rel = next(h for h in hits if h["symbol"] == "RELIANCE")
        self.assertEqual(rel["setups"], ["breakout_20d"])
        self.assertEqual(rel["price"], 1324.4)
        self.assertEqual(rel["close_date"], "2026-11-09")

    def test_turnover_floor(self):
        data, _ = scan.load_offline(DAILY)
        now = scan.parse_now("2026-11-11 08:30")
        _, counts, _ = scan.scan_daily(data, sorted(data), now, 50.0, 0, 1e15)
        self.assertEqual(counts["illiquid"], 50)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(scan, ["daily", "--offline", DAILY, "--now", "2026-11-11 08:30"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("Daily scan, Wed 2026-11-11 08:30 IST, closes through 2026-11-09", out)
            self.assertIn("(₹50+ and ₹20 crore+ traded)", out)
            with open(os.path.join(d, "trader", "watchlist.json"), encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertEqual(doc["mode"], "daily")
            self.assertEqual(len(doc["hits"]), 19)
            self.assertEqual(doc["filters"]["min_turnover_cr"], 20.0)


class Orb(unittest.TestCase):
    def setUp(self):
        self.data, self.failed = scan.load_offline(WALL)
        self.day = datetime.date(2026, 11, 11)

    def scan_at(self, hhmm):
        h, m = map(int, hhmm.split(":"))
        cutoff = datetime.datetime.combine(self.day, datetime.time(h, m))
        return scan.scan_orb(self.data, sorted(self.data), self.day, cutoff, 15, 50.0, 0)

    def test_the_wall_at_ten(self):
        hits, counts, failed = self.scan_at("10:00")
        self.assertEqual((counts["fetched"], counts["scanned"], counts["candidates"]), (50, 50, 30))
        self.assertEqual(len(hits), 18)
        self.assertEqual(failed, {})
        rel = next(h for h in hits if h["symbol"] == "RELIANCE")
        self.assertEqual(rel, {"symbol": "RELIANCE", "setups": ["orb"], "price": 1342.8, "at": "9:35 AM",
                               "bar_start": "09:30", "bar_index": 3, "or_high": 1340.9, "or_low": 1330.6,
                               "pct_over": 0.14})
        self.assertEqual(hits[0]["at"], "9:35 AM")              # earliest first
        self.assertEqual(hits[-1]["symbol"], "TATASTEEL")
        self.assertEqual(hits[-1]["at"], "10:00 AM")

    def test_fewer_hits_earlier(self):
        hits, _, _ = self.scan_at("09:35")
        self.assertEqual(sorted(h["symbol"] for h in hits),
                         ["BSE", "ETERNAL", "HCLTECH", "INDIGO", "INFY", "JSWSTEEL", "RELIANCE"])

    def test_window_messages(self):
        now = scan.parse_now("2026-11-11 09:25")
        with self.assertRaises(scan.ScanError) as cm:
            scan.orb_window(now, None, 15, datetime.time(14, 30))
        self.assertIn("opening range runs 9:15 to 9:30 AM", str(cm.exception))
        with self.assertRaises(scan.ScanError) as cm:
            scan.orb_window(scan.parse_now("2026-11-10 10:00"), None, 15, datetime.time(14, 30))
        self.assertIn("NSE holiday: Diwali Balipratipada", str(cm.exception))
        with self.assertRaises(scan.ScanError) as cm:
            scan.orb_window(scan.parse_now("2026-11-11 14:45"), None, 15, datetime.time(14, 30))
        self.assertIn("after 14:30", str(cm.exception))

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(scan, ["orb", "--offline", WALL, "--now", "2026-11-11 10:00"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("18 of 50 charts closed above their opening-range high by 10:00 AM", out)
            self.assertIn("RELIANCE       ₹1,342.80  range 1,330.60 to 1,340.90  +0.14% over", out)
            with open(os.path.join(d, "trader", "watchlist.json"), encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertEqual(doc["as_of"], "2026-11-11 10:00 IST")
            self.assertEqual(doc["mode"], "orb")


if __name__ == "__main__":
    unittest.main()
