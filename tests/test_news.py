"""trader-news, offline: Google News headlines, NSE's filing and board-meeting feeds, the day's move."""
import datetime as dt
import json
import os
import tempfile
import unittest

from _load import fix, load, run

news = load("trader-news", "news")
DIR = fix("trader-news")


def raw(name):
    with open(os.path.join(DIR, name), "rb") as fh:
        return fh.read()


class Names(unittest.TestCase):
    def test_name_key_ignores_limited_and_entities(self):
        self.assertEqual(news.name_key("Mahindra &amp; Mahindra Limited"), news.name_key("Mahindra & Mahindra Ltd."))
        self.assertEqual(news.name_key("The State Bank of India"), "state bank of india")
        self.assertEqual(news.short_name("Reliance Industries Limited"), "Reliance Industries")
        self.assertEqual(news.nse_symbol("reliance.ns"), "RELIANCE")
        self.assertEqual(news.yahoo_symbol("M&M"), "M%26M.NS")

    def test_names_come_from_nse_when_missing(self):
        watch = {"RELIANCE": None, "M&M": None, "NOPE": None}
        news.company_names(news.Fetcher(offline=DIR), {}, watch, universe=None)
        self.assertEqual(watch["RELIANCE"], "Reliance Industries Limited")
        self.assertEqual(watch["M&M"], "Mahindra & Mahindra Limited")
        self.assertIsNone(watch["NOPE"])

    def test_search_url(self):
        url = news.search_url("RELIANCE", "Reliance Industries Limited", 48)
        self.assertIn("q=%22Reliance+Industries%22+when%3A2d", url)
        self.assertIn("gl=IN", url)
        self.assertIn("when%3A1d", news.search_url("X", None, 12))


class Parsing(unittest.TestCase):
    def test_times(self):
        self.assertEqual(news.parse_nse_time("11-Nov-2026 20:26:24"),
                         dt.datetime(2026, 11, 11, 14, 56, 24, tzinfo=dt.timezone.utc))
        self.assertEqual(news.parse_nse_time("11-Nov-2026 20:26").hour, 14)
        self.assertIsNone(news.parse_nse_time("soon"))
        self.assertEqual(news.to_ist(dt.datetime(2026, 11, 11, 4, 30, tzinfo=dt.timezone.utc)),
                         dt.datetime(2026, 11, 11, 10, 0))
        self.assertEqual(news.parse_now("2026-11-11 10:00"), dt.datetime(2026, 11, 11, 4, 30, tzinfo=dt.timezone.utc))

    def test_headlines(self):
        items = news.parse_rss(raw("gnews-RELIANCE.xml"), "RELIANCE")
        self.assertEqual(len(items), 4)
        for it in items:
            self.assertEqual((it["kind"], it["ticker"]), ("headline", "RELIANCE"))
            self.assertTrue(it["title"] and it["link"].startswith("https://news.google.com/"))
            self.assertIsNotNone(it["time"])
            self.assertTrue(it["title"].endswith(it["source"]))     # "Headline - Publisher"

    def test_filings_are_matched_by_company_name(self):
        by_name = {news.name_key("State Bank of India"): "SBIN",
                   news.name_key("Mahindra & Mahindra Limited"): "M&M"}
        items = news.parse_nse_feed(raw("nse-announcements.xml"), by_name)
        self.assertEqual({i["ticker"] for i in items}, {"SBIN", "M&M"})
        sbi = next(i for i in items if i["ticker"] == "SBIN")
        self.assertEqual(sbi["title"], "State Bank of India filed with NSE: Analysts/Institutional Investor Meet/Con. "
                                       "Call Updates")
        self.assertEqual((sbi["label"], sbi["important"], sbi["source"]), ("investor meet", False, "NSE"))
        self.assertTrue(sbi["link"].startswith("https://nsearchives.nseindia.com/corporate/"))
        self.assertEqual(news.to_ist(sbi["time"]).strftime("%Y-%m-%d %H:%M"), "2026-11-11 19:00")

    def test_board_meetings(self):
        by_name = {news.name_key("Himatsingka Seide Limited"): "HIMATSEIDE"}
        items = news.parse_nse_feed(raw("nse-board-meetings.xml"), by_name, "board meeting")
        self.assertTrue(items)
        it = items[0]
        self.assertEqual(it["title"], "Himatsingka Seide Limited: board meeting on 14-Nov-2026")
        self.assertEqual((it["kind"], it["meeting_date"], it["important"]), ("board meeting", "14-Nov-2026", True))

    def test_subject_labels(self):
        for subject, label in (("Outcome of Board Meeting", "results"), ("Financial Results", "results"),
                               ("Board Meeting Intimation", "board meeting"),
                               ("Change in Directors/KMP/SMP/Auditor/RTA", "director or officer change"),
                               ("Bagging/Receiving of orders/contracts", "order win"),
                               ("Spurt in Volume", "exchange query"), ("Press Release", "press release"),
                               ("Declaration of NAV", "")):
            self.assertEqual(news.subject_label(subject), label, subject)
        self.assertIn("results", news.IMPORTANT)

    def test_move(self):
        m = news.parse_chart(raw("chart-M&M.json"), "M&M")
        self.assertEqual((m["price"], m["prev_close"], m["pct"]), (3465.0, 3290.6, 5.3))
        self.assertEqual(news.render_moves([m])[0],
                         "M&M         3,465.00 +5.30% vs yesterday's close 3,290.60 at 15:29 IST  MOVING")


class Tagging(unittest.TestCase):
    def test_tags_and_touches(self):
        watch = {"RELIANCE": "Reliance Industries Limited", "SBIN": "State Bank of India"}
        items = [{"id": "a", "kind": "headline", "ticker": "RELIANCE", "link": "l1", "time": None, "summary": "",
                  "title": "State Bank of India and Reliance Industries hit upper circuit after Q2 results"},
                 {"id": "b", "kind": "filing", "ticker": "SBIN", "link": "l2", "time": None, "summary": "",
                  "title": "State Bank of India filed with NSE: Outcome of Board Meeting", "label": "results"}]
        news.tag(items, watch)
        self.assertEqual(items[0]["touches"], ["RELIANCE", "SBIN"])
        self.assertIn("earnings", items[0]["tags"])
        self.assertIn("halt", items[0]["tags"])
        self.assertEqual(items[1]["tags"][:2], ["earnings", "results"])


class Cli(unittest.TestCase):
    ARGS = ["--tickers", "RELIANCE", "SBIN", "M&M", "HIMATSEIDE", "--offline", DIR, "--now", "2026-11-11 21:30"]

    def test_shows_each_item_once(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(news, self.ARGS + ["--json"], cwd=d)
            self.assertEqual(code, 0)
            doc = json.loads(out)
            self.assertEqual(doc["notes"], [])
            moves = {m["ticker"]: m for m in doc["moves"]}
            self.assertTrue(moves["M&M"]["moving"])
            self.assertFalse(moves["RELIANCE"]["moving"])
            kinds = [(i["ticker"], i["kind"]) for i in doc["items"]]
            self.assertIn(("HIMATSEIDE", "board meeting"), kinds)
            self.assertIn(("SBIN", "filing"), kinds)
            self.assertIn(("M&M", "filing"), kinds)
            self.assertEqual(sum(1 for t, k in kinds if k == "headline"), 4)
            times = [i["time"] for i in doc["items"]]
            self.assertEqual(times, sorted(times, reverse=True))        # newest first
            code, out, _ = run(news, self.ARGS, cwd=d)                    # second look: nothing new
            self.assertEqual(code, 1)
            self.assertIn("Nothing new.", out)
            self.assertIn("Checked 2026-11-11 21:30 IST.", out)
            code, out, _ = run(news, self.ARGS + ["--all"], cwd=d)
            self.assertIn("! 2026-11-11 20:13 IST  HIMATSEIDE  NSE           Himatsingka Seide Limited: board meeting "
                          "on 14-Nov-2026", out)

    def test_headlines_only(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(news, self.ARGS + ["--no-filings", "--no-moves", "--json", "--dry-run"], cwd=d)
            doc = json.loads(out)
            self.assertEqual({i["kind"] for i in doc["items"]}, {"headline"})
            self.assertEqual(doc["moves"], [])
            self.assertFalse(os.path.exists(os.path.join(d, "trader")))

    def test_no_symbols(self):
        with tempfile.TemporaryDirectory() as d:
            code, _, err = run(news, ["--offline", DIR], cwd=d)
            self.assertEqual(code, 2)
            self.assertIn("no symbols", err)


if __name__ == "__main__":
    unittest.main()
