#!/usr/bin/env python3
"""Position size and the order ticket for the current plan: entry LIMIT IOC + its exchange stop (SL-M).

  size.py [--margin 12000 | --margin kite] [--json] [--no-write]
Reads intraday/plan.json and intraday/config.json, writes intraday/orders.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import charges as ch  # noqa: E402
from nse_core import clock, state  # noqa: E402
from nse_core import plan as pl  # noqa: E402


def make_order(plan: dict, qty: int, cfg: dict, now) -> dict:
    side = plan["side"]
    tag = "sip" + hashlib.sha1(f"{plan['symbol']}{now:%Y%m%d%H%M%S}".encode()).hexdigest()[:10]
    return {
        "id": f"{plan['symbol']}-{now:%H%M%S}",
        "kind": "entry",
        "date": now.date().isoformat(),
        "symbol": plan["symbol"],
        "exchange": cfg["exchange"],
        "side": side,
        "transaction_type": "BUY" if side == "LONG" else "SELL",
        "order_type": "LIMIT",
        "price": plan["entry"],
        "quantity": qty,
        "product": cfg["product"],
        "validity": "IOC",
        "tag": tag,                                   # Kite allows 20 characters
        "stop": {"transaction_type": "SELL" if side == "LONG" else "BUY", "order_type": "SL-M",
                 "trigger_price": plan["stop"], "market_protection": -1, "validity": "DAY"},
        "hard_exit": plan["hard_exit"],
        "tick": plan["tick"],
        "value": round(qty * plan["entry"], 2),
        "net_loss_at_stop": round(-ch.net_pnl(side, plan["entry"], plan["stop"], qty, cfg["exchange"]), 2),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--margin", help="available margin in ₹, or 'kite' to read it from Kite")
    p.add_argument("--now")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-write", action="store_true")
    a = p.parse_args(argv)
    cfg = state.load_config()
    plan = state.read_json("plan.json")
    if not plan:
        print("No plan yet: run /nse-exit first.")
        return 1
    margin = None
    if a.margin == "kite":
        from nse_core.kite import Kite, KiteError
        try:
            margin = float(Kite().margins()["available"]["live_balance"])
        except (KiteError, KeyError) as e:
            print(f"Couldn't read the margin from Kite: {e}")
            return 1
    elif a.margin:
        margin = float(a.margin)
    qty, limit = pl.quantity(plan["side"], plan["entry"], plan["stop"], cfg, margin, cfg["exchange"])
    if qty <= 0:
        print(f"No quantity fits ({limit} limit). No order.")
        return 1
    order = make_order(plan, qty, cfg, clock.parse_now(a.now))
    order["sized_by"] = limit
    order["margin_checked"] = margin is not None
    if not a.no_write:
        state.write_json("orders.json", {"orders": [order]})
    if a.json:
        print(json.dumps(order, indent=2))
    else:
        o = order
        print(f"{o['transaction_type']} {o['quantity']} {o['symbol']} LIMIT ₹{o['price']:,.2f} IOC, {o['product']}"
              f" (₹{o['value']:,.2f}; set by the {limit} limit)")
        print(f"  then at the exchange: {o['stop']['transaction_type']} SL-M trigger ₹{o['stop']['trigger_price']:,.2f}")
        print(f"  net loss if the stop fills at its price: ₹{o['net_loss_at_stop']:.2f} (limit ₹{cfg['risk_per_trade']})")
        if margin is None:
            print("  margin not checked: pass --margin or --margin kite")
    return 0


if __name__ == "__main__":
    sys.exit(main())
