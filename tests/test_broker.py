"""trader-broker: the ticket, your yes, Kite's order legs and the paper trade."""
import json
import os
import tempfile
import unittest

from _load import ROOT, load, run

ticket = load("trader-broker", "ticket")
check = load("trader-risk", "check")
with open(os.path.join(ROOT, "trader-budget", "config.example.json"), encoding="utf-8") as _fh:
    CFG = json.load(_fh)
ORDER = {"symbol": "RELIANCE", "exchange": "NSE", "product": "MIS", "side": "buy", "qty": "27", "type": "market",
         "time_in_force": "day", "order_class": "bracket", "take_profit_limit_price": "1349.90",
         "stop_loss_stop_price": "1335.70",
         "why": "opening-range breakout on RELIANCE: 27 shares, bound by your position cap",
         "plan": {"entry": 1342.8, "stop": 1335.7, "target": 1349.9, "risk_per_share": 7.1, "max_loss": 191.7,
                  "charges_at_stop": 38.31, "loss_with_charges": 230.01, "setup": "orb", "flat_by": "15:10"}}


class KiteLegs(unittest.TestCase):
    def test_entry_is_a_protected_limit(self):
        args, note = ticket.kite_entry(ORDER, CFG)
        self.assertEqual(args, {"variety": "regular", "exchange": "NSE", "tradingsymbol": "RELIANCE",
                                "transaction_type": "BUY", "quantity": 27, "product": "MIS", "order_type": "LIMIT",
                                "price": 1344.2, "validity": "DAY", "tag": "daytraderskill"})
        self.assertIn("limit at 1344.20, 0.1% above 1342.80", note)

    def test_stop_goes_to_the_exchange_as_sl_m(self):
        self.assertEqual(ticket.kite_stop(ORDER, CFG),
                         {"variety": "regular", "exchange": "NSE", "tradingsymbol": "RELIANCE",
                          "transaction_type": "SELL", "quantity": 27, "product": "MIS", "order_type": "SL-M",
                          "trigger_price": 1335.7, "validity": "DAY", "tag": "daytraderskill"})
        self.assertIsNone(ticket.kite_stop({"symbol": "RELIANCE", "side": "sell", "qty": "27"}, CFG))

    def test_a_limit_order_keeps_its_price(self):
        args, note = ticket.kite_entry(dict(ORDER, type="limit", limit_price="1342.00"), CFG)
        self.assertEqual((args["order_type"], args["price"], note), ("LIMIT", 1342.0, ""))

    def test_a_sell_is_protected_downward(self):
        sell = {"symbol": "RELIANCE", "exchange": "NSE", "product": "MIS", "side": "sell", "qty": "27",
                "type": "market", "time_in_force": "day", "ref_price": "1346.00"}
        args, _ = ticket.kite_entry(sell, CFG)
        self.assertEqual((args["transaction_type"], args["order_type"], args["price"]), ("SELL", "LIMIT", 1344.65))
        args, note = ticket.kite_entry(dict(sell, ref_price=None), CFG)
        self.assertEqual(args["order_type"], "MARKET")
        self.assertIn("can reject it", note)

    def test_protected_price_lands_on_the_tick(self):
        self.assertEqual(ticket.protected_price("buy", 1342.8, 0.1, 10), 1344.2)
        self.assertEqual(ticket.protected_price("sell", 1342.8, 0.1, 10), 1341.4)
        self.assertEqual(ticket.protected_price("buy", 282.6, 0.1, 5), 282.9)
        self.assertEqual(ticket.tick_paise(ORDER), 10)
        self.assertEqual(ticket.kite_entry(ORDER, dict(CFG, limit_buffer_pct=0))[0]["price"], 1342.8)


class Yes(unittest.TestCase):
    def test_only_an_explicit_yes(self):
        ok = lambda reply, batch=(): ticket.parse_yes(reply, ORDER, batch)[0]
        self.assertTrue(ok("yes"))
        self.assertTrue(ok("Yes, buy 27 RELIANCE"))
        self.assertTrue(ok("yes, 27"))
        for reply in ("sure", "ok", "go", "yes to all", "yes?", "yes but wait", "", "yes buy 30", "no"):
            self.assertFalse(ok(reply), reply)
        self.assertFalse(ok("yes, the INFY one", ("RELIANCE", "INFY")))
        self.assertFalse(ok("yes M&M", ("RELIANCE", "M&M")))


class Charges(unittest.TestCase):
    def test_each_leg(self):
        self.assertEqual(ticket.leg_charges("buy", 1343.10, 27), 15.2)
        self.assertEqual(ticket.leg_charges("sell", 1349.90, 27), 23.27)
        self.assertEqual(ticket.leg_charges("buy", 1000.0, 1000), 20.0 + 30.7 + 1.0 + 30.0 + round(0.18 * 51.7, 2))

    def test_money(self):
        self.assertEqual(ticket._money(50145.13), "₹50,145.13")
        self.assertEqual(ticket._money(1500), "₹1,500")


class PaperDay(unittest.TestCase):
    """One paper trade end to end, in a scratch folder: yes -> paper fill -> target -> flat."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        os.makedirs(os.path.join(self.d, "trader"))
        self.write("orders.json", {"orders": [ORDER]})
        self.write("config.json", CFG)
        self.write("plan.json", {"symbol": "RELIANCE", "flat_by": "15:10"})

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, doc):
        with open(os.path.join(self.d, "trader", name), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def read(self, *parts):
        with open(os.path.join(self.d, "trader", *parts), encoding="utf-8") as fh:
            return json.load(fh)

    def go(self, mod, *argv):
        return run(mod, list(argv), cwd=self.d)

    def test_not_ready_without_a_risk_pass(self):
        code, out, _ = self.go(ticket, "show", "--now", "2026-11-11 09:36")
        self.assertEqual(code, 1)
        self.assertIn("NOT READY: trader-risk has not checked these orders", out)
        code, _, err = self.go(ticket, "approve", "--index", "1", "--reply", "yes", "--now", "2026-11-11 09:36")
        self.assertEqual(code, 1)
        self.assertIn("is not ready", err)

    def test_the_whole_paper_trade(self):
        now = ["--now", "2026-11-11 09:36"]
        self.assertEqual(self.go(check, *now)[0], 0)
        code, out, _ = self.go(ticket, "show", *now)
        self.assertEqual(code, 0)
        self.assertIn("ORDER 1 of 1, PAPER account, Zerodha (NSE MIS)", out)
        self.assertIn("max loss about ₹191.70 if the stop fills at 1335.70", out)
        self.assertIn("charges about ₹38.31 on top if the stop fills", out)
        self.assertIn("READY: trader-risk PASS, waiting for your yes", out)
        self.assertIn('"order_type": "SL-M"', out)
        self.assertIn("PAPER: nothing goes to a broker.", out)

        code, out, _ = self.go(ticket, "approve", "--index", "1", "--reply", "sure", *now)
        self.assertEqual(code, 1)
        self.assertIn("Not recorded", out)
        code, _, err = self.go(ticket, "paper", "--index", "1", "--price", "1343.10", *now)
        self.assertEqual(code, 1)                              # no yes yet
        code, out, _ = self.go(ticket, "approve", "--index", "1", "--reply", "yes", *now)
        self.assertEqual(code, 0)
        self.assertIn("PAPER account: nothing goes to a broker.", out)

        code, out, _ = self.go(ticket, "paper", "--index", "1", "--price", "1343.10", "--now", "2026-11-11 09:37")
        self.assertEqual(code, 0)
        self.assertIn("Paper fill: BUY 27 RELIANCE at 1343.10. Nothing went to a broker.", out)
        pf = self.read("portfolio.json")
        self.assertEqual(pf["cash"], round(50000 - 27 * 1343.10 - 15.2, 2))
        self.assertEqual(pf["positions"][0]["shares"], 27.0)
        log = self.read("state", "broker.json")["orders"]
        self.assertEqual([r["status"] for r in log], ["approved", "placed", "filled"])
        self.assertTrue(log[1]["broker_order_id"].startswith("PAPER-"))
        self.assertEqual((log[1]["kind"], log[1]["max_loss"]), ("entry", 191.7))
        self.assertEqual(log[0]["at"], "2026-11-11T09:36:00+05:30")

        code, out, _ = self.go(ticket, "show", "--now", "2026-11-11 09:40")      # decided: not ready any more
        self.assertEqual(code, 1)
        self.assertIn("DONE: placed", out)

        # the target is hit: record the sell, then the account shows what the trade made after charges
        code, out, _ = self.go(ticket, "fill", "--symbol", "RELIANCE", "--side", "sell", "--qty", "27",
                               "--price", "1349.90", "--now", "2026-11-11 11:00")
        self.assertEqual(code, 0)
        pf = self.read("portfolio.json")
        self.assertEqual(pf["positions"], [])
        self.assertEqual(pf["charges_paid"], 38.47)
        self.assertEqual(pf["cash"], 50145.13)                # +183.60 on the price, -38.47 charges

    def test_a_price_past_the_limit_does_not_fill(self):
        now = ["--now", "2026-11-11 09:36"]
        self.go(check, *now)
        self.go(ticket, "approve", "--index", "1", "--reply", "yes", *now)
        code, out, _ = self.go(ticket, "paper", "--index", "1", "--price", "1346.00", "--now", "2026-11-11 09:40")
        self.assertEqual(code, 1)
        self.assertIn("Not filled: 1346.00 is above the limit 1344.20", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "trader", "portfolio.json")))
        self.assertEqual(self.read("state", "broker.json")["orders"][-1]["status"], "failed")

    def test_flatten_and_sell(self):
        self.write("portfolio.json", {"cash": 13721.1, "positions": [
            {"ticker": "RELIANCE", "shares": 27.0, "lots": [{"id": "RELIANCE-1", "date": "2026-11-11", "shares": 27.0,
                                                           "cost": 36263.7}]}]})
        code, out, _ = self.go(ticket, "flatten", "--symbol", "RELIANCE", "--price", "1346.00", "--now", "2026-11-11 15:05")
        self.assertEqual(code, 0)
        self.assertIn("Flatten RELIANCE: SELL 27 shares of RELIANCE, market order, good for today (flat by 15:10 India time).", out)
        order = self.read("orders.json")["orders"][0]
        self.assertEqual((order["side"], order["qty"], order["product"], order["ref_price"]), ("sell", "27", "MIS", "1346.00"))
        self.assertEqual(self.go(check, "--now", "2026-11-11 15:05")[0], 0)      # an exit: past 14:30 is fine
        code, out, _ = self.go(ticket, "show", "--now", "2026-11-11 15:05")
        self.assertIn('"price": 1344.65', out)
        self.go(ticket, "approve", "--index", "1", "--reply", "yes", "--now", "2026-11-11 15:05")
        code, out, _ = self.go(ticket, "paper", "--index", "1", "--price", "1346.00", "--now", "2026-11-11 15:06")
        self.assertEqual(code, 0)
        self.assertEqual(self.read("portfolio.json")["positions"], [])
        code, out, _ = self.go(ticket, "log", "--now", "2026-11-11 15:07")
        self.assertIn("1 placed today.", out)

    def test_live_account_wording_and_no_paper_fill(self):
        self.write("config.json", dict(CFG, paper=False))
        now = ["--now", "2026-11-11 09:36"]
        self.go(check, *now)
        code, out, _ = self.go(ticket, "show", *now)
        self.assertIn("LIVE ACCOUNT, REAL MONEY", out)
        self.assertIn("Claude will call place_order (Kite MCP) with exactly:", out)
        self.assertIn("Allow once places it, Deny stops it.", out)
        code, out, _ = self.go(ticket, "approve", "--index", "1", "--reply", "yes", *now)
        self.assertIn("Now call place_order (Kite MCP) with exactly:", out)
        self.assertIn("do not place the stop", out)
        code, _, err = self.go(ticket, "paper", "--index", "1", *now)
        self.assertEqual(code, 1)
        self.assertIn("LIVE account", err)
        code, out, _ = self.go(ticket, "result", "--index", "1", "--status", "placed", "--broker-id", "2611110001234",
                               "--filled-qty", "27", "--filled-price", "1343.10", *now)
        self.assertEqual(code, 0)
        self.assertEqual(self.read("portfolio.json")["positions"][0]["shares"], 27.0)

    def test_ticket_json(self):
        self.go(check, "--now", "2026-11-11 09:36")
        code, out, _ = self.go(ticket, "show", "--index", "1", "--json", "--now", "2026-11-11 09:36")
        t = json.loads(out)
        self.assertEqual((t["tool"], t["broker"], t["paper"], t["ready"], t["bracket"]), ("place_order", "zerodha", True, True, True))
        self.assertEqual(t["tool_input"]["order_type"], "LIMIT")
        self.assertEqual(t["stop_order"]["order_type"], "SL-M")
        self.assertNotIn("why", t["order"])


if __name__ == "__main__":
    unittest.main()
