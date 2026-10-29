import csv
import unittest
from datetime import date, datetime

from _util import ROOT

from nse_core import charges as ch
from nse_core import clock, state
from nse_core import plan as pl
from nse_core.ticks import tick_size, to_tick


class ChargesMatchZerodha(unittest.TestCase):
    def test_184_calculator_results_to_the_paisa(self):
        with open(ROOT / "tests/fixtures/zerodha-calculator-intraday.csv") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 184)
        for r in rows:
            c = ch.intraday(float(r["buy"]), float(r["sell"]), int(r["qty"]), r["exchange"])
            got = {"turnover": c.turnover, "brokerage": c.brokerage, "stt": c.stt, "exchangeTxn": c.exchange_txn,
                   "gst": c.gst, "sebi": c.sebi, "stamp": c.stamp, "total": c.total, "breakeven": c.breakeven_per_share,
                   "net": c.net}
            for k, v in got.items():
                self.assertAlmostEqual(float(r[k]), v, places=9, msg=f"{r} {k}")

    def test_short_costs_the_same_as_the_mirror_long(self):
        self.assertEqual(ch.round_trip("SHORT", 512.30, 510.0, 19).total, ch.intraday(510.0, 512.30, 19).total)

    def test_documented_example(self):                    # nse-charges and nse-exit SKILL.md
        g = ch.gate("LONG", 808.05, 804.80, 12, 0.05)
        self.assertEqual((g["pass"], g["net_at_1r"], g["charges_at_1r"], g["net_at_stop"], g["break_even_exit"]),
                         (True, 29.39, 9.61, -48.58, 808.85))
        self.assertEqual(ch.gate("LONG", 808.05, 806.05, 12, 0.05)["charges_in_r"], 0.4)

    def test_off_grid_entry_is_refused(self):
        with self.assertRaises(ValueError):
            ch.break_even_exit("LONG", 1008.05, 9, 0.10)

    def test_gate_math_at_the_edge(self):                  # a ₹0.05 tick case where the gate misses by 3 paise
        g = ch.gate("LONG", 1008.05, 1004.00, 9, 0.05)
        self.assertEqual(g["break_even_exit"], 1009.10)
        self.assertEqual(g["net_at_stop"], -45.54)
        self.assertFalse(g["pass"])                       # 27.33 < 3 × 9.12, by three paise
        self.assertTrue(ch.gate("LONG", 1008.05, 1003.95, 9, 0.05)["pass"])

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            ch.intraday(100, 101, 0)
        with self.assertRaises(ValueError):
            ch.gate("LONG", 100, 101, 10, 0.01)


class Clock(unittest.TestCase):
    def test_holidays_and_weekends(self):
        self.assertFalse(clock.is_trading_day(date(2026, 10, 20)))       # Dussehra
        self.assertFalse(clock.is_trading_day(date(2026, 10, 24)))       # Saturday
        self.assertTrue(clock.is_trading_day(date(2026, 10, 29)))
        self.assertEqual(clock.previous_trading_day(date(2026, 10, 21)), date(2026, 10, 19))
        self.assertEqual(clock.next_trading_day(date(2026, 11, 9)), date(2026, 11, 11))   # skips Balipratipada
        self.assertEqual(clock.holiday_name(date(2027, 1, 26), {"2027-01-26": "Republic Day"}), "Republic Day")

    def test_phases(self):
        at = lambda h, m: datetime(2026, 10, 29, h, m, tzinfo=clock.IST)
        self.assertEqual(clock.phase(at(9, 5)), "pre-open")
        self.assertEqual(clock.phase(at(9, 15)), "open")
        self.assertEqual(clock.phase(at(15, 30)), "post-close")
        self.assertEqual(clock.phase(at(8, 0)), "closed")

    def test_last_tuesday(self):
        self.assertTrue(clock.is_last_tuesday(date(2026, 10, 27)))
        self.assertFalse(clock.is_last_tuesday(date(2026, 10, 20)))


class Ticks(unittest.TestCase):
    def test_slabs(self):
        cases = {"249.99": "0.01", "250": "0.05", "1000": "0.05", "1000.10": "0.10", "5000": "0.10",
                 "5000.5": "0.50", "10000": "0.50", "15000": "1", "20001": "5"}
        for price, tick in cases.items():
            self.assertEqual(str(tick_size(price)), tick, price)

    def test_rounding(self):
        self.assertEqual(float(to_tick(1004.03, 0.05, "down")), 1004.00)
        self.assertEqual(float(to_tick(1004.01, 0.05, "up")), 1004.05)
        self.assertEqual(float(to_tick(123.456, 0.01)), 123.46)


class Plan(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(state.DEFAULTS)

    def test_stop_rule_and_charges_fit(self):
        stop, why = pl.base_stop("LONG", 1008.05, 24.0, 0.05, self.cfg)
        self.assertEqual(stop, 1004.00)
        self.assertIn("0.4%", why)
        self.assertEqual(pl.fit_stop_to_charges("LONG", 1008.05, stop, 0.05, self.cfg), (1003.95, 9, True))
        short_stop, _ = pl.base_stop("SHORT", 500.0, 40.0, 0.05, self.cfg)
        self.assertEqual(short_stop, 504.0)                               # 10 % of ATR 40 = 4.00 > 0.4 % = 2.00

    def test_quantity_limits(self):
        self.assertEqual(pl.quantity("LONG", 1008.05, 1003.95, self.cfg), (9, "per-stock cap"))
        self.assertEqual(pl.quantity("LONG", 1008.05, 1003.95, self.cfg, margin=1000), (4, "margin"))
        tight = dict(self.cfg, risk_per_trade=50, max_per_stock=100000)
        qty, limit = pl.quantity("LONG", 1008.05, 1003.95, tight)
        self.assertEqual(limit, "risk")
        self.assertLessEqual(-ch.net_pnl("LONG", 1008.05, 1003.95, qty), 50)
        self.assertGreater(-ch.net_pnl("LONG", 1008.05, 1003.95, qty + 1), 50)


if __name__ == "__main__":
    unittest.main()
