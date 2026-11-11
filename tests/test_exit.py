"""trader-exit: the stop and the target on NSE's tick grid."""
import datetime
import json
import os
import tempfile
import unittest
from decimal import Decimal

from _load import fix, load, run

ex = load("trader-exit", "exit")
REL = fix("trader-entry", "RELIANCE-2026-11-11-5m.json")
ENTRY = {"created_by": "trader-entry", "symbol": "RELIANCE", "setup": "orb", "side": "buy", "date": "2026-11-11",
         "status": "triggered", "time": "9:35 AM", "bar_start": "09:30", "bar_index": 3, "price": 1342.8,
         "level": 1340.9, "interval": "5m", "opening_range": {"high": 1340.9, "low": 1330.6, "minutes": 15}}


def D(x):
    return Decimal(str(x))


class Ticks(unittest.TestCase):
    def test_slabs(self):
        for price, tick in ((249.99, "0.01"), (250, "0.05"), (1000, "0.05"), (1000.05, "0.1"), (5000, "0.1"),
                            (5000.5, "0.5"), (10000, "0.5"), (10001, "1"), (20000, "1"), (20005, "5")):
            self.assertEqual(ex.slab_tick(price), D(tick), price)

    def test_the_tick_the_prices_really_sit_on(self):
        self.assertEqual(ex.tick_for([D("1342.80"), D("1340.90"), D("1330.60")]), D("0.1"))     # Reliance
        self.assertEqual(ex.tick_for([D("1065.65"), D("1065.00"), D("1055.05")]), D("0.05"))    # SBI: last month's slab
        self.assertEqual(ex.tick_for([D("5031.20"), D("5027.10"), D("4981.40")]), D("0.1"))     # HAL, same reason
        self.assertEqual(ex.tick_for([D("49930"), D("49885"), D("49205")]), D("5"))             # Bosch
        self.assertEqual(ex.tick_for([D("187.45"), D("187.42"), D("186.05")]), D("0.01"))       # Tata Steel

    def test_rounding(self):
        self.assertEqual(ex.floor_tick("1335.75", D("0.1")), D("1335.70"))
        self.assertEqual(ex.round_tick("1349.95", D("0.1")), D("1350.00"))
        self.assertEqual(ex.floor_tick("1060.025", D("0.05")), D("1060.00"))
        self.assertEqual(ex.tk(D("0.1")), "0.10")
        self.assertEqual(ex.tk(D("5")), "5")


class Compute(unittest.TestCase):
    def test_reliance_or_mid_one_r(self):
        c = ex.compute(1342.8, "or_mid", None, "r", D(1), 1340.9, 1330.6)
        self.assertEqual((c["stop"], c["target"], c["risk"], c["tick"]), (D("1335.70"), D("1349.90"), D("7.10"), D("0.1")))
        self.assertEqual(c["reward_risk"], D("1.00"))
        self.assertIn("rounded down to the 0.10 tick", c["stop_detail"])

    def test_two_r_and_or_low(self):
        c = ex.compute(1342.8, "or_mid", None, "r", D(2), 1340.9, 1330.6)
        self.assertEqual(c["target"], D("1357.00"))
        c = ex.compute(1342.8, "or_low", None, "r", D(2), 1340.9, 1330.6)
        self.assertEqual((c["stop"], c["target"]), (D("1330.60"), D("1367.20")))

    def test_sbi_on_its_five_paise_grid(self):
        c = ex.compute(1065.65, "or_mid", None, "r", D(2), 1065.0, 1055.05)
        self.assertEqual((c["stop"], c["target"], c["tick"]), (D("1060.00"), D("1076.95"), D("0.05")))

    def test_pct_stop_and_a_given_tick(self):
        c = ex.compute(1169.4, "pct", D(1), "r", D(2), tick="0.05")
        self.assertEqual(c["stop"], D("1157.70"))
        with self.assertRaises(ex.PlanError):
            ex.compute(1169.4, "pct", D(1), "r", D(2), tick="0.03")

    def test_refusals(self):
        with self.assertRaises(ex.PlanError) as cm:
            ex.compute(1342.8, "price", D("1350"), "r", D(1))
        self.assertIn("at or above the entry", str(cm.exception))
        with self.assertRaises(ex.PlanError) as cm:
            ex.compute(1342.8, "price", D("1342.5"), "r", D(1))
        self.assertIn("too tight", str(cm.exception))
        with self.assertRaises(ex.PlanError):
            ex.compute(1342.8, "or_mid", None, "price", D("1340"), 1340.9, 1330.6)

    def test_money(self):
        self.assertEqual(ex.money("1234567.5"), "₹12,34,567.50")
        self.assertEqual(ex.D("₹1,342.80"), D("1342.80"))


class FlatBy(unittest.TestCase):
    DAY = datetime.date(2026, 11, 11)

    def test_default_is_1510(self):
        self.assertEqual(ex.resolve_flat_by(self.DAY, None, dict(ex.DEFAULTS), datetime.time(9, 35)), ("15:10", ""))

    def test_late_flat_by_gets_the_square_off_note(self):
        hhmm, note = ex.resolve_flat_by(self.DAY, "15:25", dict(ex.DEFAULTS), None)
        self.assertEqual(hhmm, "15:25")
        self.assertIn("square off intraday (MIS) positions", note)

    def test_at_or_after_the_close_is_refused(self):
        with self.assertRaises(ex.PlanError):
            ex.resolve_flat_by(self.DAY, "15:30", dict(ex.DEFAULTS), None)
        with self.assertRaises(ex.PlanError):
            ex.resolve_flat_by(self.DAY, None, {"flat_by": "15:55"}, None)     # the US pack's default
        with self.assertRaises(ex.PlanError):
            ex.resolve_flat_by(self.DAY, "10:00", dict(ex.DEFAULTS), datetime.time(10, 5))


class Cli(unittest.TestCase):
    def plan(self, d, *args):
        os.makedirs(os.path.join(d, "trader"), exist_ok=True)
        with open(os.path.join(d, "trader", "entry.json"), "w", encoding="utf-8") as fh:
            json.dump(ENTRY, fh)
        return run(ex, ["plan", "--now", "2026-11-11 09:36"] + list(args), cwd=d)

    def test_plan_from_the_entry(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = self.plan(d, "--stop", "or-mid", "--target", "1R", "--write")
            self.assertEqual(code, 0)
            self.assertIn("Stop          ₹1,335.70  opening-range midpoint", out)
            self.assertIn("Target        ₹1,349.90  1R (one times the risk)", out)
            self.assertIn("Tick          ₹0.10", out)
            self.assertIn("Flat by       15:10 IST", out)
            with open(os.path.join(d, "trader", "plan.json"), encoding="utf-8") as fh:
                plan = json.load(fh)
            self.assertEqual((plan["entry"], plan["stop"], plan["target"], plan["tick"]), (1342.8, 1335.7, 1349.9, 0.1))
            self.assertEqual((plan["risk_per_share"], plan["flat_by"], plan["entry_bar"]), (7.1, "15:10", 3))
            code, out, _ = run(ex, ["show", "--now", "2026-11-11 09:40"], cwd=d)
            self.assertEqual(code, 0)
            self.assertIn("RELIANCE long", out)

    def test_default_target_is_two_r(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = self.plan(d)
            self.assertEqual(code, 0)
            self.assertIn("₹1,357.00  2R (two times the risk)", out)

    def test_atr_stop_on_the_session_bars(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = self.plan(d, "--stop", "atr:1.5", "--offline", REL, "--json")
            self.assertEqual(code, 0)
            plan = json.loads(out)
            self.assertEqual(plan["atr_bars"], 4)
            self.assertLess(plan["stop"], 1342.8)
            self.assertEqual(round(plan["stop"] * 10) / 10, plan["stop"])     # on the 0.10 grid

    def test_not_triggered_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "trader"))
            with open(os.path.join(d, "trader", "entry.json"), "w", encoding="utf-8") as fh:
                json.dump(dict(ENTRY, status="waiting"), fh)
            code, _, err = run(ex, ["plan", "--now", "2026-11-11 09:36"], cwd=d)
            self.assertEqual(code, 1)
            self.assertIn("not triggered", err)


if __name__ == "__main__":
    unittest.main()
