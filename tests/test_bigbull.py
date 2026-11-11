"""trader-bigbull, offline: NSE's real bulk and block deal files of Wed 11 Nov 2026."""
import json
import os
import tempfile
import unittest

from _load import fix, load, run

deals = load("trader-bigbull", "deals")
DIR = fix("trader-bigbull")


def text(name):
    with open(os.path.join(DIR, name), encoding="utf-8") as fh:
        return fh.read()


class Parsing(unittest.TestCase):
    def test_block_file(self):
        rows = deals.parse_deals(text("block.csv"), "block")
        self.assertEqual(len(rows), 6)
        d = next(r for r in rows if r["client"] == "MOTILAL OSWAL MUTUAL FUND")
        self.assertEqual(d, {"kind": "block", "date": "2026-11-11", "symbol": "CPPLUS", "name": "Aditya Infotech Limited",
                             "client": "MOTILAL OSWAL MUTUAL FUND", "side": "buy", "qty": 842977, "price": 4140.0,
                             "value": 3489924780.0, "remarks": ""})

    def test_bulk_file(self):
        rows = deals.parse_deals(text("bulk.csv"), "bulk")
        self.assertEqual(len(rows), 71)
        self.assertEqual({r["date"] for r in rows}, {"2026-11-11"})
        self.assertEqual({r["side"] for r in rows}, {"buy", "sell"})

    def test_the_download_format_with_spaced_headers(self):
        csv_text = ("Date ,Symbol ,Security Name ,Client Name ,Buy / Sell ,Quantity Traded ,"
                    "Trade Price / Wght. Avg. Price ,Remarks \n"
                    "01-Oct-2026,ITC,ITC Limited,SOME INVESTOR LLP,BUY,\"1,00,000\",285.50,-\n")
        rows = deals.parse_deals(csv_text, "bulk")
        self.assertEqual((rows[0]["date"], rows[0]["qty"], rows[0]["price"], rows[0]["value"]),
                         ("2026-10-01", 100000, 285.5, 28550000.0))

    def test_not_a_deal_file(self):
        with self.assertRaises(deals.DealsError):
            deals.parse_deals("Symbol,Name\nITC,ITC Limited\n", "bulk")
        self.assertEqual(deals.parse_deals("", "bulk"), [])
        self.assertEqual(deals.parse_deals("NO RECORDS\n", "bulk"), [])

    def test_dates(self):
        self.assertEqual(deals.parse_date("11-NOV-2026").isoformat(), "2026-11-11")
        self.assertEqual(deals.parse_date("01/10/2026").isoformat(), "2026-10-01")
        self.assertIsNone(deals.parse_date("soon"))


class Loading(unittest.TestCase):
    def test_a_block_printed_in_both_files_counts_once(self):
        both = deals.load_deals(["bulk", "block"], DIR)
        self.assertEqual(len(both), 72)                     # 71 bulk + 6 block - 5 copies
        cpplus = [d for d in both if d["symbol"] == "CPPLUS"]
        self.assertEqual([(d["kind"], d["side"], d["qty"]) for d in cpplus],
                         [("block", "buy", 842977), ("block", "sell", 702481), ("block", "sell", 702481),
                          ("block", "buy", 561985)])        # two equal sells in one file are two trades
        self.assertEqual(both[0]["value"], max(d["value"] for d in both))

    def test_filters(self):
        both = deals.load_deals(["bulk", "block"], DIR)
        mo = deals.select(both, clients=["motilal oswal"])
        self.assertEqual([(d["symbol"], d["side"]) for d in mo], [("CPPLUS", "buy")])
        self.assertEqual(len(deals.select(both, symbols=["cpplus"])), 4)
        big = deals.select(both, min_cr=100)
        self.assertTrue(all(d["value"] >= 100 * deals.CRORE for d in big))
        self.assertEqual(len(big), 6)
        self.assertEqual(deals.select(both, since="2026-11-12"), [])

    def test_client_matching(self):
        d = {"client": "MOTILAL OSWAL MUTUAL FUND"}
        self.assertTrue(deals.matches_client(d, ["motilal"]))
        self.assertTrue(deals.matches_client(d, ["Oswal Motilal"]))
        self.assertTrue(deals.matches_client(d, ["kotak", "motil"]))      # any of the names; a word may be a prefix
        self.assertFalse(deals.matches_client(d, ["kotak"]))
        self.assertFalse(deals.matches_client(d, ["motilal securities"]))
        self.assertTrue(deals.matches_client(d, []))


class Words(unittest.TestCase):
    def test_indian_numbers(self):
        self.assertEqual(deals.group(842977), "8,42,977")
        self.assertEqual(deals.group(6293593), "62,93,593")
        self.assertEqual(deals.rupees(4140), "₹4,140.00")
        self.assertEqual(deals.crore(3489924780.0), "₹349 crore")
        self.assertEqual(deals.crore(943950000.0), "₹94.39 crore")

    def test_alert_line(self):
        d = deals.select(deals.load_deals(["block"], DIR), clients=["motilal"])[0]
        self.assertEqual(deals.alert(d, {"CPPLUS": "you hold it"}),
                         "NEW block deal, 2026-11-11: MOTILAL OSWAL MUTUAL FUND bought 8,42,977 shares of CPPLUS "
                         "(Aditya Infotech Limited) at ₹4,140.00, ₹349 crore. You hold it")

    def test_summary(self):
        rows = deals.summarise(deals.load_deals(["block"], DIR))
        self.assertEqual([r["symbol"] for r in rows], ["CPPLUS", "COHANCE"])
        c = rows[0]
        self.assertEqual((c["buy"], c["sell"], c["net"], c["deals"]), (5816542680.0, 5816542680.0, 0.0, 4))
        self.assertEqual(c["buyers"], ["MOTILAL OSWAL MUTUAL FUND", "KOTAK MAHINDRA MUTUAL FUND"])
        self.assertEqual(c["sellers"], ["DIXON TECHNOLOGIES (INDIA) LIMITED"])


class Cli(unittest.TestCase):
    def test_new_alerts_once(self):
        with tempfile.TemporaryDirectory() as d:
            args = ["new", "--offline", DIR, "--client", "motilal oswal", "--tickers", "CPPLUS", "--today", "2026-11-11"]
            code, out, _ = run(deals, args, cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("NEW block deal, 2026-11-11: MOTILAL OSWAL MUTUAL FUND bought 8,42,977 shares of CPPLUS", out)
            self.assertIn("Named by you", out)
            self.assertIn("not advice", out)
            code, out, _ = run(deals, args, cwd=d)
            self.assertEqual(code, 1)
            self.assertIn("Nothing new for the investors and stocks you named.", out)
            with open(os.path.join(d, "trader", "state", "bigbull.json"), encoding="utf-8") as fh:
                state = json.load(fh)
            self.assertEqual((len(state["seen"]), state["last_check"]), (1, "2026-11-11"))

    def test_flags_what_you_hold(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "trader"))
            with open(os.path.join(d, "trader", "portfolio.json"), "w", encoding="utf-8") as fh:
                json.dump({"cash": 1, "positions": [{"ticker": "COHANCE", "shares": 10}]}, fh)
            code, out, _ = run(deals, ["index", "--offline", DIR, "--kind", "block"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("6 deals, 2026-11-11, biggest first:", out)
            self.assertIn("<- you hold it", out)

    def test_watch_file_and_summary(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "bulls.txt"), "w", encoding="utf-8") as fh:
                fh.write("# the funds I follow\nkotak mahindra mutual fund\n")
            code, out, _ = run(deals, ["index", "--offline", DIR, "--watch", "bulls.txt", "--json"], cwd=d)
            doc = json.loads(out)
            self.assertEqual([x["client"] for x in doc["deals"]], ["KOTAK MAHINDRA MUTUAL FUND"])
            code, out, _ = run(deals, ["summary", "--offline", DIR, "--kind", "block"], cwd=d)
            self.assertIn("CPPLUS      Aditya Infotech Limited: bought ₹582 crore, sold ₹582 crore, bought = sold (4 deals)", out)
            code, _, err = run(deals, ["index", "--offline", DIR, "--watch", "nope.txt"], cwd=d)
            self.assertEqual(code, 1)

    def test_parse_a_downloaded_file(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(deals, ["parse", os.path.join(DIR, "block.csv"), "--client", "jasti"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("JASTI FAMILY TRUST", out)
            self.assertIn("block COHANCE     SELL", out)


if __name__ == "__main__":
    unittest.main()
