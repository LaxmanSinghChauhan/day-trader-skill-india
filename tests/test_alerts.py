"""trader-alerts: the NSE clock and the alerts of the Reliance plan, offline."""
import json
import os
import tempfile
import unittest

from _load import fix, load, run

alerts = load("trader-alerts", "alerts")
QUOTES = fix("trader-alerts")
PLAN = {"symbol": "RELIANCE", "date": "2026-11-11", "stop": 1335.7, "stop_label": "opening-range midpoint",
        "target": 1349.9, "target_label": "1R (one times the risk)", "flat_by": "15:10"}


def at(text):
    return alerts.parse_now(text)


class Clock(unittest.TestCase):
    def test_open_and_closed(self):
        st = alerts.market_status(at("2026-11-11 10:00"))
        self.assertEqual((st["open"], st["reason"], st["opens"], st["closes"]), (True, "regular session", "09:15", "15:30"))
        self.assertEqual(st["now_india"], "2026-11-11 10:00")
        self.assertIsNone(st["early_close"])
        st = alerts.market_status(at("2026-11-11 09:10"))
        self.assertEqual((st["open"], st["reason"], st["next_open"]), (False, "before the open", "2026-11-11 09:15"))
        st = alerts.market_status(at("2026-11-11 15:30"))
        self.assertEqual((st["open"], st["reason"], st["next_open"]), (False, "after the close", "2026-11-12 09:15"))

    def test_holiday_and_weekend(self):
        st = alerts.market_status(at("2026-11-10 10:00"))
        self.assertEqual((st["open"], st["reason"], st["next_open"]),
                         (False, "NSE holiday: Diwali Balipratipada", "2026-11-11 09:15"))
        st = alerts.market_status(at("2026-11-07 12:00"))             # Saturday
        self.assertEqual((st["reason"], st["next_open"]), ("weekend", "2026-11-09 09:15"))
        st = alerts.market_status(at("2026-12-24 12:00"))             # Thursday before Christmas
        self.assertEqual(alerts.market_status(at("2026-12-24 16:00"))["next_open"], "2026-12-28 09:15")
        self.assertTrue(st["open"])

    def test_unknown_year(self):
        self.assertFalse(alerts.market_status(at("2027-01-04 10:00"))["calendar_known"])

    def test_cli(self):
        code, out, _ = run(alerts, ["clock", "--now", "2026-11-10 10:00"])
        self.assertEqual(code, 1)
        self.assertIn("India 2026-11-10 10:00 (Tuesday): NSE closed, NSE holiday: Diwali Balipratipada.", out)
        self.assertIn("Next open: 2026-11-11 09:15 IST.", out)
        code, out, _ = run(alerts, ["clock", "--now", "2026-11-11 10:00"])
        self.assertEqual(code, 0)
        self.assertIn("Today's session: 09:15 to 15:30.", out)


class Quotes(unittest.TestCase):
    def test_yahoo_symbol_and_url(self):
        self.assertEqual(alerts.yahoo_symbol("reliance"), "RELIANCE.NS")
        self.assertTrue(alerts.yahoo_url("M&M").endswith("/chart/M%26M.NS?range=1d&interval=1d"))

    def test_offline_quotes(self):
        quotes, errors = alerts.get_quotes(["RELIANCE", "ITC", "NOPE"], offline=QUOTES)
        self.assertEqual(sorted(quotes), ["ITC", "RELIANCE"])
        self.assertEqual(len(errors), 1)
        q = quotes["RELIANCE"]
        self.assertEqual((q["symbol"], q["price"], q["prev_close"], q["currency"], q["source"]),
                         ("RELIANCE", 1335.4, 1324.4, "INR", "yahoo"))

    def test_quote_cli_writes_prices(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(alerts, ["quote", "RELIANCE", "--offline", QUOTES, "--write", "--now", "2026-11-11 15:10"],
                               cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("RELIANCE    ₹1335.40 (+0.83% vs prev close ₹1324.40)", out)
            with open(os.path.join(d, "trader", "prices.json"), encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertEqual(doc["prices"], {"RELIANCE": 1335.4})
            self.assertEqual(doc["as_of"], "2026-11-11T09:40:00Z")


class Rules(unittest.TestCase):
    def test_three_alerts_from_the_plan(self):
        rules = alerts.rules_from_plan(PLAN)
        self.assertEqual([r["id"] for r in rules], ["reliance-plan-stop", "reliance-plan-target", "reliance-flat-by"])
        self.assertEqual([r["type"] for r in rules], ["stop", "target", "time"])
        self.assertEqual(rules[2]["at"], "15:10")
        self.assertTrue(all(r["date"] == "2026-11-11" for r in rules))
        self.assertEqual(alerts.rules_from_plan({"symbol": "ITC", "stop": 280.0, "target": 285.0})[2]["at"], "15:10")

    def ring(self, rules, quotes, now, state=None):
        status = alerts.market_status(at(now))
        return alerts.evaluate(rules, quotes, status, state or {}, at(now))

    def test_stop_and_flat_by_ring_once(self):
        rules = alerts.rules_from_plan(PLAN)
        q = {"RELIANCE": {"price": 1335.4, "prev_close": 1324.4}}
        rings, state = self.ring(rules, q, "2026-11-11 15:10")
        self.assertEqual([r["id"] for r in rings], ["reliance-plan-stop", "reliance-flat-by"])
        self.assertEqual(rings[0]["message"], "RELIANCE is ₹1335.40: at or below your stop ₹1335.70 "
                                              "(plan stop: opening-range midpoint).")
        self.assertIn("Flat by close: it is 15:10 IST (set for 15:10), the market closes at 15:30.", rings[1]["message"])
        rings, _ = self.ring(rules, q, "2026-11-11 15:15", state)
        self.assertEqual(rings, [])

    def test_target(self):
        rules = alerts.rules_from_plan(PLAN)
        rings, _ = self.ring(rules, {"RELIANCE": {"price": 1350.0}}, "2026-11-11 11:00")
        self.assertEqual([r["id"] for r in rings], ["reliance-plan-target"])

    def test_plan_rules_are_for_the_plan_day_only(self):
        rules = alerts.rules_from_plan(PLAN)
        rings, _ = self.ring(rules, {"RELIANCE": {"price": 1300.0}}, "2026-11-12 15:20")
        self.assertEqual(rings, [])

    def test_opening_bell_and_pct_move(self):
        rules = [{"id": "opening-bell", "type": "opening_bell"},
                 {"id": "itc-3", "symbol": "ITC", "type": "pct_move", "pct": 3}]
        rings, state = self.ring(rules, {"ITC": {"price": 291.0, "prev_close": 282.0}}, "2026-11-11 09:16")
        self.assertEqual(rings[0]["message"], "Opening bell: NSE is open (2026-11-11 09:16 IST).")
        self.assertEqual(rings[1]["message"], "ITC moved +3.19% to ₹291.00 (from ₹282.00).")
        rings, _ = self.ring(rules, {}, "2026-11-11 09:00")
        self.assertEqual(rings, [])                                    # not open yet

    def test_bad_rules(self):
        with self.assertRaises(alerts.AlertError):
            alerts.validate({"id": "x", "type": "time", "at": "25:00"})
        with self.assertRaises(alerts.AlertError):
            alerts.validate({"id": "x", "type": "stop", "symbol": "ITC"})


class Cli(unittest.TestCase):
    def test_add_from_plan_then_check(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "trader"))
            with open(os.path.join(d, "trader", "plan.json"), "w", encoding="utf-8") as fh:
                json.dump(PLAN, fh)
            code, out, _ = run(alerts, ["add", "--from-plan"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("Added reliance-flat-by", out)
            code, out, _ = run(alerts, ["check", "--offline", QUOTES, "--now", "2026-11-11 10:00"], cwd=d)
            self.assertEqual(code, 0)                                  # the fixture's price is the close: under the stop
            self.assertIn("NSE OPEN (2026-11-11 10:00 IST, regular session).", out)
            self.assertIn("ALERT RELIANCE is ₹1335.40: at or below your stop ₹1335.70", out)
            self.assertIn("The target is an alert only.", out)
            code, out, _ = run(alerts, ["check", "--offline", QUOTES, "--now", "2026-11-11 10:05"], cwd=d)
            self.assertEqual(code, 1)
            self.assertIn("Nothing hit. 3 rule(s) watched today, RELIANCE ₹1335.40.", out)
            code, out, _ = run(alerts, ["reset", "reliance-plan-stop"], cwd=d)
            self.assertEqual(code, 0)
            code, out, _ = run(alerts, ["list"], cwd=d)
            self.assertIn("reliance-plan-target", out)


if __name__ == "__main__":
    unittest.main()
