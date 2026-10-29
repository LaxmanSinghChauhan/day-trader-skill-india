#!/usr/bin/env python3
"""Entry timer for a Stocks-in-Play breakout: waiting, triggered, too far, expired or skipped.

  entry.py check SBIN [--price 812.40] [--upper 890 --lower 730] [--now "2026-10-29 09:42"]
  entry.py check LT --quote kite        # live price and circuit limits from Kite (Connect app)
  entry.py watch LT --every 20          # poll Kite until it triggers or expires
Writes intraday/entry.json for nse-exit.
"""
from __future__ import annotations

import argparse
import json
import sys
import time as systime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import candles as cd  # noqa: E402
from nse_core import clock, state  # noqa: E402
from nse_core.ticks import to_tick  # noqa: E402


def find_hit(symbol: str) -> dict | None:
    wl = state.read_json("watchlist.json") or {}
    return next((h for h in wl.get("hits", []) if h["symbol"] == symbol), None)


def traded_today(symbol: str, day: str) -> bool:
    ledger = state.read_json("state/ledger.json", {"trades": []})
    return any(t["symbol"] == symbol and t.get("date") == day for t in ledger["trades"])


def last_bar_price(symbol: str):
    f = state.path(f"candles/{symbol}.json")
    if not f.exists():
        return None, None
    bars = cd.load(f)["bars"]
    return (bars[-1].c, bars[-1].t) if bars else (None, None)


def decide(hit: dict, price: float, now, cfg: dict, upper=None, lower=None, already=False) -> dict:
    side, trig, tick = hit["side"], hit["trigger"], hit["tick"]
    cap = cfg["entry_cap_pct"]
    limit = float(to_tick(trig * (1 + cap), tick, "down")) if side == "LONG" else float(to_tick(trig * (1 - cap), tick, "up"))
    out = {"symbol": hit["symbol"], "side": side, "trigger": trig, "limit": limit, "price": price,
           "at": now.isoformat(timespec="seconds"), "validity": "IOC"}
    t = now.time()
    if already and cfg["one_trade_per_stock"]:
        return {**out, "status": "skipped", "why": "already traded this stock today (one trade per stock)"}
    if t < clock.hhmm(cfg["entries_from"]):
        return {**out, "status": "waiting", "why": f"entries open at {cfg['entries_from']}"}
    if t > clock.hhmm(cfg["entries_until"]):
        return {**out, "status": "expired", "why": f"no new entries after {cfg['entries_until']}"}
    room = cfg["circuit_room_pct"] / 100
    if side == "LONG" and upper and price >= upper * (1 - room):
        return {**out, "status": "skipped", "why": f"within {cfg['circuit_room_pct']}% of the upper circuit ₹{upper}"}
    if side == "SHORT" and lower and price <= lower * (1 + room):
        return {**out, "status": "skipped", "why": f"within {cfg['circuit_room_pct']}% of the lower circuit ₹{lower}"}
    crossed = price >= trig if side == "LONG" else price <= trig
    if not crossed:
        gap = abs(trig - price)
        return {**out, "status": "waiting", "why": f"₹{gap:.2f} from the trigger"}
    beyond = price > limit if side == "LONG" else price < limit
    if beyond:
        return {**out, "status": "too far", "why": f"price ₹{price:,.2f} is past the IOC cap ₹{limit:,.2f}: don't chase"}
    return {**out, "status": "triggered", "why": f"LIMIT {'BUY' if side == 'LONG' else 'SELL'} at ₹{limit:,.2f}, IOC"}


def live_quote(symbol: str):
    from nse_core.kite import Kite
    q = Kite().quote([f"NSE:{symbol}"])[f"NSE:{symbol}"]
    return q["last_price"], q.get("upper_circuit_limit"), q.get("lower_circuit_limit")


def check(a, cfg) -> dict | None:
    symbol = a.symbol.upper()
    hit = find_hit(symbol)
    if not hit or "trigger" not in hit:
        print(f"{symbol} isn't on today's tradable watchlist: run /nse-scanner first.")
        return None
    now = clock.parse_now(a.now)
    upper, lower = a.upper, a.lower
    if a.quote == "kite":
        price, upper, lower = live_quote(symbol)
    elif a.price:
        price = a.price
    else:
        price, when = last_bar_price(symbol)
        if price is None:
            print("No price: pass --price, or --quote kite, or fetch candles.")
            return None
        print(f"(price from the last 5-minute bar, {when:%H:%M}: not live)")
    return decide(hit, price, now, cfg, upper, lower, traded_today(symbol, now.date().isoformat()))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["check", "watch"])
    p.add_argument("symbol")
    p.add_argument("--price", type=float)
    p.add_argument("--upper", type=float)
    p.add_argument("--lower", type=float)
    p.add_argument("--quote", choices=["kite"])
    p.add_argument("--now")
    p.add_argument("--every", type=int, default=20)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    cfg = state.load_config()
    if a.mode == "watch":
        a.quote = "kite"
    while True:
        out = check(a, cfg)
        if out is None:
            return 1
        state.write_json("entry.json", out)
        print(json.dumps(out, indent=2) if a.json else f"{out['at'][11:16]} {out['symbol']} {out['side']}: {out['status']} ({out['why']})")
        if a.mode == "check" or out["status"] != "waiting":
            return 0 if out["status"] == "triggered" else 1
        systime.sleep(max(5, a.every))


if __name__ == "__main__":
    sys.exit(main())
