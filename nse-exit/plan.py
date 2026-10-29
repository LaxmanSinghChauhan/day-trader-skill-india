#!/usr/bin/env python3
"""Exit plan before the entry: the stop, the hard exit at 15:10, what 1R is, and the charges at each.

  plan.py [SYMBOL] [--entry 808.10] [--margin 12000] [--no-fit] [--json] [--no-write]
Reads intraday/entry.json (or the watchlist trigger), writes intraday/plan.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import charges as ch  # noqa: E402
from nse_core import plan as pl  # noqa: E402
from nse_core import state  # noqa: E402


def build(hit: dict, entry: float, cfg: dict, margin=None, fit=True) -> dict:
    side, tick, atr = hit["side"], hit["tick"], hit["atr"]
    stop, why = pl.base_stop(side, entry, atr, tick, cfg)
    widened = False
    if fit:
        stop, qty, widened = pl.fit_stop_to_charges(side, entry, stop, tick, cfg, margin, cfg["exchange"])
    else:
        qty, _ = pl.quantity(side, entry, stop, cfg, margin, cfg["exchange"])
    risk = round(abs(entry - stop), 2)
    plan = {"symbol": hit["symbol"], "side": side, "entry": entry, "stop": stop, "stop_rule": why,
            "widened_for_charges": widened, "risk_per_share": risk, "tick": tick, "atr": atr,
            "hard_exit": cfg["hard_exit"], "qty_estimate": qty,
            "shadow_targets": {f"{k}R": round(entry + k * risk if side == "LONG" else entry - k * risk, 2) for k in (1, 2, 3)}}
    if qty > 0:
        g = ch.gate(side, entry, stop, qty, tick, cfg["exchange"])
        plan.update({"net_at_stop": g["net_at_stop"], "charges_in_r": g["charges_in_r"],
                     "break_even_exit": g["break_even_exit"], "gate": "PASS" if g["pass"] else "FAIL",
                     "gate_reason": g["reason"]})
    return plan


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("symbol", nargs="?")
    p.add_argument("--entry", type=float)
    p.add_argument("--margin", type=float, help="available margin in ₹ (else not checked here)")
    p.add_argument("--no-fit", action="store_true", help="don't widen a stop that fails the charges gate")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-write", action="store_true")
    a = p.parse_args(argv)
    cfg = state.load_config()
    entry_state = state.read_json("entry.json") or {}
    symbol = (a.symbol or entry_state.get("symbol") or "").upper()
    wl = state.read_json("watchlist.json") or {}
    hit = next((h for h in wl.get("hits", []) if h["symbol"] == symbol), None)
    if not hit:
        print("No watchlist entry for that symbol: run /nse-scanner (and /nse-entry) first.")
        return 1
    entry = a.entry or (entry_state.get("limit") if entry_state.get("symbol") == symbol else None) or hit["trigger"]
    plan = build(hit, float(entry), cfg, a.margin, not a.no_fit)
    if not a.no_write:
        state.write_json("plan.json", plan)
    if a.json:
        print(json.dumps(plan, indent=2))
    else:
        s = plan
        print(f"{s['symbol']} {s['side']} from ₹{s['entry']:,.2f}")
        print(f"  stop ₹{s['stop']:,.2f} ({s['stop_rule']}{'; widened to pass the charges gate' if s['widened_for_charges'] else ''})"
              f" → ₹{s['risk_per_share']:.2f} a share at risk")
        print(f"  exit: the stop, or everything at {s['hard_exit']} (Zerodha squares off MIS at 15:25 for ₹50 + GST)")
        if s["qty_estimate"]:
            print(f"  about {s['qty_estimate']} shares: net at the stop ₹{s['net_at_stop']:.2f}; charges {s['charges_in_r']:.2f}R;"
                  f" real break-even ₹{s['break_even_exit']:,.2f}; gate {s['gate']}")
        else:
            print("  no quantity fits the limits: no trade")
        print(f"  for the journal only (not exits): 1R ₹{s['shadow_targets']['1R']:,.2f}, 2R ₹{s['shadow_targets']['2R']:,.2f}")
    return 0 if plan["qty_estimate"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
