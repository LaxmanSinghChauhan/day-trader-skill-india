"""trader-risk: PASS or BLOCK, with India's session, holidays and whole shares."""
import json
import os
import tempfile
import unittest

from _load import ROOT, load, run

check = load("trader-risk", "check")
ticket = load("trader-broker", "ticket")
with open(os.path.join(ROOT, "trader-budget", "config.example.json"), encoding="utf-8") as _fh:
    CFG = json.load(_fh)
ORDER = {"symbol": "RELIANCE", "exchange": "NSE", "product": "MIS", "side": "buy", "qty": "27", "type": "market",
         "time_in_force": "day", "order_class": "bracket", "take_profit_limit_price": "1349.90",
         "stop_loss_stop_price": "1335.70",
         "plan": {"entry": 1342.8, "stop": 1335.7, "target": 1349.9, "risk_per_share": 7.1, "max_loss": 191.7,
                  "charges_at_stop": 38.31, "loss_with_charges": 230.01, "setup": "orb", "flat_by": "15:10"}}


def at(text):
    return check.parse_now(text)


def one(order=None, cfg=None, now="2026-11-11 09:36", **kw):
    res = check.check([dict(ORDER, **(order or {}))], dict(CFG, **(cfg or {})), now=at(now), **kw)
    return res, res["results"][0]


def reasons(r):
    return " | ".join(r["reasons"])


class Pass(unittest.TestCase):
    def test_the_reliance_order_passes(self):
        res, r = one()
        self.assertEqual((res["pass"], res["block"], r["verdict"], r["kind"]), (1, 0, "PASS", "entry"))
        self.assertEqual((r["max_loss"], r["risk_per_share"], r["reward_risk"], r["value_inr"]), (191.7, 7.1, 1.0, 36255.6))
        self.assertEqual(res["cash_after"], 13744.4)
        self.assertEqual(res["now_india"], "2026-11-11 09:36")
        self.assertTrue(any("with charges (about ₹38.31, Zerodha intraday) the loss at the stop is about "
                            "₹230.01" in x for x in r["info"]))

    def test_same_fingerprint_as_the_broker(self):
        _, r = one()
        self.assertEqual(r["fingerprint"], ticket.fingerprint(ORDER))
        self.assertNotEqual(r["fingerprint"], ticket.fingerprint(dict(ORDER, qty="28")))
        self.assertNotEqual(r["fingerprint"], ticket.fingerprint(dict(ORDER, product="CNC")))


class Window(unittest.TestCase):
    def test_closed_in_the_evening(self):
        _, r = one(now="2026-11-11 20:00")
        self.assertIn("window: the market is closed (Wed 2026-11-11 20:00 IST; the session is 09:15 to 15:30)", reasons(r))

    def test_holiday_and_weekend(self):
        _, r = one(now="2026-11-10 10:00")
        self.assertIn("NSE holiday: Diwali Balipratipada", reasons(r))
        _, r = one(now="2026-11-07 10:00")
        self.assertIn("weekend", reasons(r))

    def test_before_and_after_the_entry_window(self):
        _, r = one(now="2026-11-11 09:20")
        self.assertIn("window: no new entries before 09:30 IST (it is 09:20)", reasons(r))
        _, r = one(now="2026-11-11 14:31")
        self.assertIn("window: no new entries after 14:30 IST (it is 14:31)", reasons(r))
        _, r = one(now="2026-11-11 14:30")
        self.assertEqual(r["verdict"], "PASS")

    def test_unknown_year_warns(self):
        res, _ = one(now="2027-01-04 10:00")
        self.assertTrue(any("check nseindia.com" in w for w in res["warnings"]))


class Format(unittest.TestCase):
    def test_no_rupee_amount_orders(self):
        _, r = one({"qty": None, "notional": "10000"})
        self.assertIn("NSE takes whole shares only", reasons(r))

    def test_whole_shares(self):
        _, r = one({"qty": "27.5"})
        self.assertIn("whole shares only, got qty '27.5'", reasons(r))

    def test_exchange_and_product(self):
        _, r = one({"exchange": "NYSE"})
        self.assertIn("exchange must be NSE", reasons(r))
        _, r = one({"product": "NRML"})
        self.assertIn("product must be MIS (intraday) or CNC (delivery)", reasons(r))
        _, r = one({"product": "CNC"})
        self.assertEqual(r["verdict"], "PASS")
        self.assertTrue(any("not squared off by the broker" in w for w in r["warnings"]))

    def test_bracket_needs_both_legs_and_a_day_order(self):
        _, r = one({"take_profit_limit_price": None})
        self.assertIn("needs both take_profit_limit_price and stop_loss_stop_price", reasons(r))
        _, r = one({"time_in_force": "ioc"})
        self.assertIn("a bracket order needs time_in_force day", reasons(r))

    def test_futures_and_options_are_off(self):
        for sym in ("NIFTY26NOV24000CE", "RELIANCE26NOVFUT", "BANKNIFTY2611352000PE"):
            _, r = one({"symbol": sym})
            self.assertIn("is a futures or options contract; F&O is off", reasons(r), sym)
        _, r = one({"symbol": "BTC/USD"})
        self.assertIn("does not look like an NSE share symbol", reasons(r))
        for sym in ("M&M", "BAJAJ-AUTO", "3MINDIA"):
            _, r = one({"symbol": sym, "plan": dict(ORDER["plan"])})
            self.assertFalse(any(x.startswith("asset") for x in r["reasons"]), sym)


class Limits(unittest.TestCase):
    def test_max_loss(self):
        _, r = one(cfg={"max_loss_per_trade_inr": 150})
        self.assertIn("loss: 27 shares x 7.10 risk a share = ₹191.70 at the stop, over your ₹150 max loss", reasons(r))

    def test_size_and_cash(self):
        _, r = one(cfg={"max_order_inr": 30000})
        self.assertIn("size: ₹36,255.60 is over your ₹30,000 max order", reasons(r))
        _, r = one(cfg={"budget": 36000})
        self.assertIn("that would be margin (borrowed money)", reasons(r))

    def test_stop_is_required(self):
        o = {"stop_loss_stop_price": None, "take_profit_limit_price": None, "order_class": None,
             "plan": {"entry": 1342.8}}
        _, r = one(o)
        self.assertIn("stop: no stop", reasons(r))

    def test_reward_to_risk(self):
        _, r = one(cfg={"min_reward_risk": 2})
        self.assertIn("reward:risk: 1.00", reasons(r))

    def test_daily_loss_and_trades_from_the_log(self):
        placed = {"orders": [{"status": "placed", "date": "2026-11-11", "kind": "entry", "side": "buy",
                              "symbol": s, "max_loss": 450.0} for s in ("INFY", "SBIN", "ITC")]}
        _, r = one(state=placed)
        self.assertIn("daily loss: ₹1,350 already at risk today plus ₹191.70 for this one", reasons(r))
        self.assertIn("trades: 3 entries placed today", reasons(r))

    def test_duplicate(self):
        res = check.check([dict(ORDER), dict(ORDER)], CFG, now=at("2026-11-11 09:36"))
        self.assertEqual((res["pass"], res["block"]), (1, 1))
        self.assertIn("duplicate: a second buy RELIANCE in this batch", reasons(res["results"][1]))

    def test_an_exit_is_never_blocked_by_the_limits(self):
        pf = {"cash": 13744.4, "positions": [{"ticker": "RELIANCE", "shares": 27,
                                               "lots": [{"shares": 27, "cost": 36255.6}]}]}
        sell = {"symbol": "RELIANCE", "exchange": "NSE", "product": "MIS", "side": "sell", "qty": "27",
                "type": "market", "time_in_force": "day"}
        res = check.check([sell], CFG, portfolio=pf, now=at("2026-11-11 15:20"))
        r = res["results"][0]
        self.assertEqual((r["verdict"], r["kind"]), ("PASS", "exit"))    # after 14:30, and it still passes
        self.assertEqual(r["reasons"], [])
        res = check.check([sell], dict(CFG, blocked=["RELIANCE"]), portfolio=pf, now=at("2026-11-11 15:20"))
        r = res["results"][0]
        self.assertEqual(r["verdict"], "PASS")
        self.assertIn("exit, not blocked: blocked: RELIANCE is on your blocked list", r["warnings"])

    def test_no_short_selling(self):
        sell = {"symbol": "RELIANCE", "side": "sell", "qty": "27", "type": "market", "time_in_force": "day"}
        res = check.check([sell], CFG, now=at("2026-11-11 10:00"))
        self.assertIn("short: selling more RELIANCE than you hold", reasons(res["results"][0]))


class Cli(unittest.TestCase):
    def test_writes_the_verdicts(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "trader"))
            with open(os.path.join(d, "trader", "orders.json"), "w", encoding="utf-8") as fh:
                json.dump({"orders": [ORDER]}, fh)
            with open(os.path.join(d, "trader", "config.json"), "w", encoding="utf-8") as fh:
                json.dump(CFG, fh)
            code, out, _ = run(check, ["--now", "2026-11-11 09:36"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("PASS  #1 buy RELIANCE 27 shares, entry", out)
            self.assertIn("1 passed, 0 blocked at 2026-11-11 09:36 IST.", out)
            with open(os.path.join(d, "trader", "state", "risk.json"), encoding="utf-8") as fh:
                rec = json.load(fh)
            self.assertEqual((rec["date"], rec["pass"]), ("2026-11-11", 1))
            code, out, _ = run(check, ["--now", "2026-11-11 15:31", "--no-write"], cwd=d)
            self.assertEqual(code, 1)
            self.assertIn("BLOCK", out)


if __name__ == "__main__":
    unittest.main()
