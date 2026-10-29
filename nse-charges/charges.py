#!/usr/bin/env python3
"""Zerodha intraday charges, break-even and the 3× charges gate for one trade.

  charges.py trade --buy 808.05 --sell 830 --qty 12 [--exchange BSE]
  charges.py breakeven --side LONG --entry 808.05 --qty 12 [--tick 0.05]
  charges.py gate --side LONG --entry 808.05 --stop 804.80 --qty 12
  add --json for machine-readable output
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import charges as ch  # noqa: E402
from nse_core.ticks import tick_size  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trade")
    t.add_argument("--buy", type=float, required=True)
    t.add_argument("--sell", type=float, required=True)
    t.add_argument("--qty", type=int, required=True)
    b = sub.add_parser("breakeven")
    b.add_argument("--side", choices=["LONG", "SHORT", "long", "short"], required=True)
    b.add_argument("--entry", type=float, required=True)
    b.add_argument("--qty", type=int, required=True)
    b.add_argument("--tick", type=float)
    g = sub.add_parser("gate")
    g.add_argument("--side", choices=["LONG", "SHORT", "long", "short"], required=True)
    g.add_argument("--entry", type=float, required=True)
    g.add_argument("--stop", type=float, required=True)
    g.add_argument("--qty", type=int, required=True)
    g.add_argument("--tick", type=float)
    for s in (t, b, g):
        s.add_argument("--exchange", default="NSE", choices=["NSE", "BSE"])
        s.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    try:
        if a.cmd == "trade":
            out = ch.intraday(a.buy, a.sell, a.qty, a.exchange).as_dict()
            text = (f"{a.exchange} intraday, {a.qty} × buy ₹{a.buy:,.2f} / sell ₹{a.sell:,.2f}\n"
                    f"  turnover ₹{out['turnover']:,.2f}\n"
                    f"  brokerage ₹{out['brokerage']:.2f} · STT ₹{out['stt']:.2f} · exchange ₹{out['exchange_txn']:.2f}"
                    f" · SEBI ₹{out['sebi']:.2f} · stamp ₹{out['stamp']:.2f} · GST ₹{out['gst']:.2f}\n"
                    f"  total charges ₹{out['total']:.2f} (₹{out['breakeven_per_share']:.2f} a share)\n"
                    f"  gross ₹{out['gross']:,.2f} → net ₹{out['net']:,.2f}")
        elif a.cmd == "breakeven":
            tick = a.tick or float(tick_size(a.entry))
            be = ch.break_even_exit(a.side, a.entry, a.qty, tick, a.exchange)
            out = {"side": a.side.upper(), "entry": a.entry, "qty": a.qty, "tick": tick, "break_even_exit": be}
            text = f"{a.side.upper()} {a.qty} from ₹{a.entry:,.2f}: net P&L turns ≥ 0 at ₹{be:,.2f} (tick {tick})"
        else:
            tick = a.tick or float(tick_size(a.entry))
            out = ch.gate(a.side, a.entry, a.stop, a.qty, tick, a.exchange)
            verdict = "PASS" if out["pass"] else "FAIL"
            text = (f"{verdict}: {a.side.upper()} {a.qty} @ ₹{a.entry:,.2f}, stop ₹{a.stop:,.2f}\n"
                    f"  at 1R (₹{out['one_r_price']:,.2f}): net ₹{out['net_at_1r']:.2f} after ₹{out['charges_at_1r']:.2f}"
                    f" charges (needs ≥ {ch.MIN_NET_TO_CHARGES_AT_1R} × charges)\n"
                    f"  at the stop: net ₹{out['net_at_stop']:.2f}; charges are {out['charges_in_r']:.2f}R\n"
                    f"  real break-even exit ₹{out['break_even_exit']:,.2f}")
            if out["reason"]:
                text += f"\n  {out['reason']}"
    except ValueError as e:
        print(f"Can't compute: {e}")
        return 2
    print(json.dumps(out, indent=2) if a.json else text)
    return 0 if a.cmd != "gate" or out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
