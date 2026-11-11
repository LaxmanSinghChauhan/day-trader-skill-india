"""trader-analyst, offline: Reliance's quarters as Yahoo carried them on 11 Nov 2026."""
import datetime as dt
import json
import os
import tempfile
import unittest

from _load import fix, load, run

facts = load("trader-analyst", "facts")
DIR = fix("trader-analyst")
with open(os.path.join(DIR, "fundamentals-RELIANCE.json"), encoding="utf-8") as _fh:
    DOC = json.load(_fh)


def synth(values, currency="INR"):
    """A Yahoo timeseries answer with quarterly revenue and net income only: {end: (revenue, net income)}."""
    def rows(i):
        return [{"asOfDate": e, "periodType": "3M", "currencyCode": currency, "reportedValue": {"raw": v[i]}}
                for e, v in sorted(values.items())]
    return {"timeseries": {"result": [
        {"meta": {"type": ["quarterlyTotalRevenue"]}, "quarterlyTotalRevenue": rows(0)},
        {"meta": {"type": ["quarterlyNetIncome"]}, "quarterlyNetIncome": rows(1)}]}}


class Quarters(unittest.TestCase):
    def setUp(self):
        self.r = facts.analyse(DOC, name="Reliance Industries Limited", symbol="RELIANCE")

    def test_latest_quarter(self):
        row = self.r["rows"][0]
        self.assertEqual((row["end"], row["fiscal"]), ("2026-09-30", "Q2 FY27"))
        self.assertEqual((row["revenue"], row["net_income"], row["eps_diluted"]), (3306010000000.0, 255480000000.0, 18.88))
        self.assertEqual((row["gross_margin"], row["operating_margin"], row["net_margin"]), (27.1, 12.5, 7.7))
        self.assertIsNone(row["revenue_yoy"])                    # Yahoo has no September 2025 quarter
        self.assertEqual(self.r["currency"], "INR")

    def test_a_missing_quarter_is_shown_as_a_gap(self):
        ends = [r["end"] for r in self.r["rows"]]
        self.assertEqual(ends, ["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30"])
        self.assertEqual([r["gap_before"] for r in self.r["rows"]], [False, False, False, True, False])
        june = self.r["rows"][1]
        self.assertEqual((june["revenue_yoy"], june["eps_yoy"]), (27.0, -22.4))    # June 2025 is there

    def test_last_four_quarters(self):
        self.assertEqual(self.r["ttm"], {"revenue": 11990330000000.0, "net_income": 821100000000.0, "eps_diluted": 60.68})

    def test_what_changed(self):
        lines = facts.changes(self.r)
        self.assertEqual(lines[0], "Quarter ending 2026-09-30 (Q2 FY27): revenue ₹3,30,601 crore, net profit "
                                   "₹25,548 crore, diluted EPS ₹18.88.")
        self.assertIn("No growth figures: Yahoo's data has no quarter a year before 2026-09-30 to compare with.", lines)
        self.assertIn("Operating margin 12.5% (+2.0 points vs the quarter before).", lines)

    def test_render(self):
        text = facts.render("RELIANCE", self.r, None, today=dt.date(2026, 11, 11))
        self.assertIn("Reliance Industries Limited (RELIANCE). ₹ crore except EPS.", text)
        self.assertIn("2026-09-30  Q2 FY27     3,30,601        -   27.1%   12.5%    7.7%     25,548    18.88       -", text)
        self.assertIn("(a quarter is missing before this one)", text)
        self.assertIn("Last 4 quarters: revenue ₹11,99,033 crore, net profit ₹82,110 crore, diluted EPS ₹60.68.", text)
        self.assertNotIn("NOTE:", text)
        self.assertIn("nseindia.com", text)

    def test_metrics_row(self):
        row = facts.metrics_row("RELIANCE", self.r)
        self.assertEqual((row["ticker"], row["period_end"], row["fiscal"], row["eps_ttm"], row["currency"]),
                         ("RELIANCE", "2026-09-30", "Q2 FY27", 60.68, "INR"))


class Rules(unittest.TestCase):
    def test_indian_fiscal_quarters(self):
        for end, label in (("2026-06-30", "Q1 FY27"), ("2026-09-30", "Q2 FY27"), ("2026-12-31", "Q3 FY27"),
                           ("2027-03-31", "Q4 FY27"), ("2026-03-31", "Q4 FY26")):
            self.assertEqual(facts.fiscal_label(end), label)

    def test_consecutive(self):
        self.assertTrue(facts.consecutive(["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"]))
        self.assertFalse(facts.consecutive(["2025-06-30", "2025-12-31"]))

    def test_no_trailing_sum_across_a_gap(self):
        doc = synth({"2025-06-30": (100e7, 10e7), "2025-12-31": (110e7, 11e7), "2026-03-31": (120e7, 12e7),
                     "2026-06-30": (130e7, 13e7)})
        r = facts.analyse(doc, symbol="X")
        self.assertEqual(r["ttm"], {})
        self.assertEqual(r["rows"][0]["revenue_yoy"], 30.0)

    def test_units(self):
        self.assertEqual(facts.unit("INR"), ("₹", "crore", 1e7))
        self.assertEqual(facts.unit("USD"), ("USD ", "million", 1e6))
        self.assertEqual(facts.crore(3306010000000.0), "3,30,601")
        self.assertEqual(facts.crore(5076000000.0, "USD"), "5,076")
        self.assertEqual(facts.crore(None), "-")
        self.assertEqual(facts.crore(-25e7), "-25")

    def test_a_dollar_filer_is_labelled(self):
        r = facts.analyse(synth({"2026-06-30": (5.0e9, 0.8e9), "2026-09-30": (5.1e9, 0.82e9)}, "USD"), name="Infosys Limited",
                          symbol="INFY")
        text = facts.render("INFY", r, None, today=dt.date(2026, 11, 11))
        self.assertIn("Infosys Limited (INFY). USD million except EPS.", text)
        self.assertIn("Yahoo carries this company's figures in USD, not rupees", text)
        self.assertIn("revenue USD 5,100 million", facts.changes(r)[0])

    def test_stale_quarters_get_a_note(self):
        r = facts.analyse(synth({"2025-03-31": (95e9, 15e9), "2025-06-30": (85e9, 16e9)}), symbol="HDFCBANK")
        note = facts.stale_note(r, dt.date(2026, 11, 11))
        self.assertIn("Yahoo's quarters for HDFCBANK stop at 2025-06-30 (Q1 FY26)", note)
        self.assertIsNone(facts.stale_note(r, dt.date(2025, 8, 1)))

    def test_no_data(self):
        with self.assertRaises(facts.FactsError):
            facts.analyse({"timeseries": {"result": []}})
        with self.assertRaises(facts.FactsError):
            facts.analyse({"oops": 1})

    def test_url(self):
        url = facts.fundamentals_url("M&M", dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc))
        self.assertIn("/timeseries/M%26M.NS?type=", url)
        self.assertIn("quarterlyTotalRevenue", url)
        self.assertIn("annualDilutedEPS", url)


class Filings(unittest.TestCase):
    def test_board_meeting_from_nse(self):
        f = facts.latest_filings(facts.Fetcher(offline=DIR), "Himatsingka Seide Limited")
        self.assertEqual(f["board_meeting"]["date"], "14-Nov-2026")
        self.assertTrue(f["board_meeting"]["url"].startswith("https://nsearchives.nseindia.com/"))
        self.assertIsNone(f["results"])

    def test_names(self):
        names = facts.company_names(facts.Fetcher(offline=DIR), {"RELIANCE", "INFY"}, universe=None)
        self.assertEqual(names, {"RELIANCE": "Reliance Industries Limited", "INFY": "Infosys Limited"})


class Cli(unittest.TestCase):
    def test_report_and_metrics(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(facts, ["RELIANCE", "--offline", DIR, "--metrics", "trader/metrics.json"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("Reliance Industries Limited (RELIANCE).", out)
            self.assertIn("wrote trader/metrics.json (1 companies)", out)
            with open(os.path.join(d, "trader", "metrics.json"), encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertEqual(doc["companies"][0]["revenue_ttm"], 11990330000000.0)

    def test_unknown_symbol(self):
        with tempfile.TemporaryDirectory() as d:
            code, _, err = run(facts, ["NOPE", "--offline", DIR], cwd=d)
            self.assertEqual(code, 2)
            self.assertIn("NOPE", err)


if __name__ == "__main__":
    unittest.main()
