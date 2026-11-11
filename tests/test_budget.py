"""trader-budget: the size of the Reliance trade, and what Zerodha's charges make of it."""
import json
import os
import tempfile
import unittest

from _load import ROOT, load, run

size = load("trader-budget", "size")
PLAN = {"created_by": "trader-exit", "symbol": "RELIANCE", "side": "buy", "date": "2026-11-11", "setup": "orb",
        "entry": 1342.8, "entry_time": "9:35 AM", "entry_bar": 3, "interval": "5m", "tick": 0.1,
        "opening_range": {"high": 1340.9, "low": 1330.6, "minutes": 15},
        "stop": 1335.7, "stop_rule": "or_mid", "stop_label": "opening-range midpoint",
        "target": 1349.9, "target_r": 1.0, "target_label": "1R (one times the risk)",
        "risk_per_share": 7.1, "reward_risk": 1.0, "flat_by": "15:10"}
with open(os.path.join(ROOT, "trader-budget", "config.example.json"), encoding="utf-8") as _fh:
    CFG = json.load(_fh)


class Config(unittest.TestCase):
    def test_example_config_matches_the_defaults(self):
        for k, v in CFG.items():
            self.assertEqual(size.DEFAULTS.get(k, v) if k != "budget" else v, v, k)
        self.assertEqual((CFG["budget"], CFG["max_loss_per_trade_inr"], CFG["max_daily_loss_inr"]), (50000, 500, 1500))
        self.assertEqual((CFG["no_entries_before"], CFG["no_entries_after"], CFG["flat_by"]), ("09:30", "14:30", "15:10"))
        self.assertTrue(CFG["paper"])
        self.assertFalse(CFG["allow_margin"])
        self.assertNotIn("pdt_guard", CFG)
        self.assertFalse(any(k.endswith("_usd") for k in CFG))


class Charges(unittest.TestCase):
    def test_round_trip_to_the_stop(self):
        # 27 x 1,342.80 = 36,255.60 bought, 27 x 1,335.70 = 36,063.90 sold. By hand:
        # brokerage 0.03 %: 10.88 + 10.82 = 21.70; STT 0.025 % of the sell = 9.02 -> 9; exchange 2.15 + 0.07 = 2.22;
        # SEBI 0.07; stamp 0.003 % of the buy = 1.09 -> 1; GST 18 % of (21.70 + 2.22 + 0.07) = 4.32. Total 38.31.
        self.assertEqual(size.intraday_charges(1342.80, 1335.70, 27),
                         {"brokerage": 21.7, "stt": 9.0, "exchange": 2.22, "sebi": 0.07, "stamp": 1.0, "gst": 4.32,
                          "total": 38.31})

    def test_round_trip_to_the_target(self):
        self.assertEqual(size.intraday_charges(1342.80, 1349.90, 27)["total"], 38.45)

    def test_brokerage_is_capped_at_twenty_a_leg(self):
        c = size.intraday_charges(1000.0, 1000.0, 1000)      # 10 lakh a leg: 0.03 % would be 300
        self.assertEqual(c["brokerage"], 40.0)

    def test_nothing_to_charge(self):
        self.assertEqual(size.intraday_charges(100, 100, 0)["total"], 0.0)


class Sizing(unittest.TestCase):
    def test_the_reliance_trade(self):
        s = size.size_trade(PLAN, CFG, today="2026-11-11")
        self.assertEqual([(l["name"], l["shares"]) for l in s["limits"]],
                         [("max loss", 70), ("position cap", 27), ("max order", 29), ("cash", 33)])
        self.assertEqual((s["qty"], s["bound_by"]), (27, "position cap"))
        self.assertEqual((s["cost"], s["max_loss"]), (36255.6, 191.7))
        self.assertEqual((s["charges_at_stop"], s["charges_at_target"]), (38.31, 38.45))
        self.assertEqual((s["loss_with_charges"], s["gain_with_charges"]), (230.01, 153.25))
        self.assertIsNone(s["refusal"])

    def test_the_order(self):
        o = size.bracket_order(size.size_trade(PLAN, CFG, today="2026-11-11"))
        core = {k: v for k, v in o.items() if k not in ("why", "plan")}
        self.assertEqual(core, {"symbol": "RELIANCE", "exchange": "NSE", "product": "MIS", "side": "buy", "qty": "27",
                                "type": "market", "time_in_force": "day", "order_class": "bracket",
                                "take_profit_limit_price": "1349.90", "stop_loss_stop_price": "1335.70"})
        self.assertEqual(o["why"], "opening-range breakout on RELIANCE: 27 shares, bound by your position cap "
                                   "(27 x 7.10 = ₹191.70 at the stop)")
        self.assertEqual((o["plan"]["charges_at_stop"], o["plan"]["loss_with_charges"]), (38.31, 230.01))

    def test_max_loss_binds_with_a_small_limit(self):
        s = size.size_trade(PLAN, dict(CFG, max_loss_per_trade_inr=100), today="2026-11-11")
        self.assertEqual((s["qty"], s["bound_by"], s["max_loss"]), (14, "max loss", 99.4))

    def test_a_fresh_higher_price_raises_the_risk(self):
        s = size.size_trade(PLAN, CFG, price=1345.0, today="2026-11-11")
        self.assertEqual((s["entry"], s["entry_from"], s["risk_per_share"]), (1345.0, "price", 9.3))

    def test_limit_order(self):
        s = size.size_trade(PLAN, CFG, limit=1342.0, today="2026-11-11")
        o = size.bracket_order(s)
        self.assertEqual((o["type"], o["limit_price"]), ("limit", "1342.00"))

    def test_refusals(self):
        s = size.size_trade(PLAN, dict(CFG, max_loss_per_trade_inr=5), today="2026-11-11")
        self.assertEqual(s["qty"], 0)
        self.assertIn("one share risks ₹7.10", s["refusal"])
        self.assertIsNone(size.bracket_order(s))
        s = size.size_trade(PLAN, CFG, price=1348.0, today="2026-11-11")       # the price ran toward the target
        self.assertIn("reward:risk", s["refusal"])
        with self.assertRaises(size.SizeError):
            size.size_trade(PLAN, CFG, today="2026-11-12")
        with self.assertRaises(size.SizeError):
            size.size_trade(dict(PLAN, side="sell"), CFG, today="2026-11-11")
        with self.assertRaises(size.SizeError):
            size.size_trade(PLAN, dict(CFG, blocked=["RELIANCE"]), today="2026-11-11")

    def test_money(self):
        self.assertEqual(size.money(50000), "₹50,000")
        self.assertEqual(size.money(1234567.5), "₹12,34,567.50")
        self.assertEqual(size.money(191.7), "₹191.70")


class Weights(unittest.TestCase):
    PRICES = {"HDFCBANK": 814.1, "RELIANCE": 1342.8, "ICICIBANK": 1589.0, "INFY": 1169.4, "ITC": 282.6}

    def test_whole_shares_always(self):
        with open(os.path.join(ROOT, "trader-budget", "targets.example.json"), encoding="utf-8") as fh:
            rows = size.parse_weights(json.load(fh))
        r = size.size(rows, dict(CFG, max_position_pct=25), prices=self.PRICES)
        self.assertTrue(r["whole_shares"])
        for p in r["positions"]:
            self.assertEqual(p["shares"], int(p["shares"]))
            self.assertLessEqual(p["rupees"], r["cap"] + 0.01)
        self.assertLessEqual(r["invested"], r["investable"])
        orders = size.orders_from(r)
        self.assertEqual({o["product"] for o in orders}, {"CNC"})
        self.assertTrue(all("qty" in o and "notional" not in o for o in orders))

    def test_needs_prices(self):
        with self.assertRaises(size.SizeError):
            size.size(size.parse_weights({"RELIANCE": 60, "ITC": 40}), CFG)


class Cli(unittest.TestCase):
    def test_writes_one_bracket_order(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "trader"))
            for name, doc in (("plan.json", PLAN), ("config.json", CFG)):
                with open(os.path.join(d, "trader", name), "w", encoding="utf-8") as fh:
                    json.dump(doc, fh)
            code, out, _ = run(size, ["--write", "--now", "2026-11-11 09:36"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("Size: 27 shares of RELIANCE = ₹36,255.60 at 1342.80. Max loss at the stop: "
                          "27 x 7.10 = ₹191.70.", out)
            self.assertIn("With charges: lose about ₹230.01 at the stop, make about ₹153.25 at the target.", out)
            self.assertIn("buy 27 RELIANCE (NSE, MIS), market, day, take-profit 1349.90, stop-loss 1335.70", out)
            with open(os.path.join(d, "trader", "orders.json"), encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertEqual((doc["created_by"], doc["status"], doc["paper"], len(doc["orders"])),
                             ("trader-budget", "proposed", True, 1))


if __name__ == "__main__":
    unittest.main()
