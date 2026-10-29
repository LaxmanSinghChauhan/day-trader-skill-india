#!/usr/bin/env python3
"""Risk manager: PASS or BLOCK for every proposed order, with the reason. Exits are never blocked by limits.

  check.py [--orders intraday/orders.json] [--now "2026-10-29 09:42"] [--json] [--no-write]
Writes intraday/state/risk.json (the verdicts with each order's fingerprint) for nse-kite.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import charges as ch  # noqa: E402
from nse_core import clock, state  # noqa: E402
from nse_core import orders as od  # noqa: E402
from nse_core.ticks import on_tick  # noqa: E402


def in_window(now, windows) -> str | None:
    for w in windows or []:
        if clock.parse_now(w["from"]) <= now <= clock.parse_now(w["to"]):
            return w.get("why", "event window")
    return None


def check_order(o: dict, cfg: dict, led: dict, events: dict, now, batch: list[dict]) -> tuple[list[str], list[str]]:
    block, warn = [], []
    extra = cfg["extra_holidays"]
    # format: applies to every order, entries and exits alike
    for field in ("symbol", "transaction_type", "quantity", "order_type", "product"):
        if not o.get(field):
            block.append(f"format: no {field}")
    if o.get("transaction_type") not in ("BUY", "SELL"):
        block.append("format: transaction_type must be BUY or SELL")
    if not isinstance(o.get("quantity"), int) or o.get("quantity", 0) <= 0:
        block.append("format: quantity must be a whole number above 0")
    if o.get("order_type") == "LIMIT" and (not o.get("price") or not on_tick(o["price"], o.get("tick", 0.01))):
        block.append("format: LIMIT price missing or off the tick grid")
    if o.get("order_type") in ("MARKET", "SL-M") and o.get("market_protection") in (None, 0):
        block.append("format: market orders need market protection (Kite rejects protection 0)")
    if o.get("exchange") not in ("NSE", "BSE"):
        block.append("format: exchange must be NSE or BSE")
    if block or o.get("kind") == "exit":
        if o.get("kind") == "exit" and not clock.phase(now, extra) == "open":
            warn.append("exit outside market hours: it will be rejected or queued")
        return block, warn

    # entries only from here
    day = now.date()
    if not clock.calendar_known(day):
        warn.append(f"the holiday calendar for {day.year} isn't loaded: check NSE's circular")
    if clock.phase(now, extra) != "open":
        block.append(f"market: not open now ({clock.phase(now, extra)})")
    t = now.time()
    if not clock.hhmm(cfg["entries_from"]) <= t <= clock.hhmm(cfg["entries_until"]):
        block.append(f"window: entries only {cfg['entries_from']}–{cfg['entries_until']}")
    why = in_window(now, cfg["event_windows"]) or in_window(now, events.get("event_windows"))
    if why:
        block.append(f"event: inside the {why} window")
    sym = o["symbol"]
    if sym in {s.upper() for s in cfg["blocked"]}:
        block.append("blocked: on your blocked list")
    avoid = (events.get("avoid_today") or {}) if events.get("date") == day.isoformat() else {}
    if sym in avoid:
        block.append(f"news: {avoid[sym]}")
    if o.get("side") == "SHORT" and not cfg["allow_short"]:
        block.append("short: shorts are off in the config")
    if o.get("product") != "MIS":
        block.append("product: this pack trades intraday MIS only")
    stop = (o.get("stop") or {}).get("trigger_price")
    entry = o.get("price")
    stop_ok = False
    if not stop:
        block.append("stop: an entry needs its exchange stop")
    elif o.get("side") not in ("LONG", "SHORT"):
        block.append("format: side must be LONG or SHORT")
    else:
        stop_ok = stop < entry if o["side"] == "LONG" else stop > entry
        if not stop_ok:
            block.append("stop: on the wrong side of the entry")
    if stop_ok and entry:
        g = ch.gate(o["side"], entry, stop, o["quantity"], o.get("tick", 0.05), o["exchange"])
        loss = -g["net_at_stop"]
        if loss > cfg["risk_per_trade"]:
            block.append(f"loss: ₹{loss:.2f} at the stop after charges is over ₹{cfg['risk_per_trade']}")
        if not g["pass"]:
            block.append(f"charges: {g['reason']}")
        value = o["quantity"] * entry
        if value > cfg["max_per_stock"]:
            block.append(f"size: ₹{value:,.2f} is over the ₹{cfg['max_per_stock']:,} per-stock cap")
        today_loss = -od.realised(led, day, day)
        week_loss = -od.realised(led, od.week_start(day), day)
        worst = od.open_risk(led, o["exchange"]) + loss + sum(
            -ch.net_pnl(b["side"], b["price"], b["stop"]["trigger_price"], b["quantity"], b["exchange"]) for b in batch)
        if today_loss + worst > cfg["max_daily_loss"]:
            block.append(f"daily loss: ₹{today_loss:.0f} lost today + ₹{worst:.0f} worst case open would pass ₹{cfg['max_daily_loss']}")
        if week_loss + worst > cfg["max_weekly_loss"]:
            block.append(f"weekly loss: ₹{week_loss:.0f} this week + ₹{worst:.0f} worst case would pass ₹{cfg['max_weekly_loss']}")
        if not o.get("margin_checked"):
            warn.append("margin not checked: Zerodha may reject it for margin")
    entries_today = [x for x in led["trades"] if x["date"] == day.isoformat()]
    if len(entries_today) + len(batch) >= cfg["max_trades_per_day"]:
        block.append(f"trades: {cfg['max_trades_per_day']} entries already today")
    if len(od.open_trades(led)) + len(batch) >= cfg["max_open_positions"]:
        block.append(f"positions: {cfg['max_open_positions']} already open")
    if cfg["one_trade_per_stock"] and (any(x["symbol"] == sym for x in entries_today) or any(b["symbol"] == sym for b in batch)):
        block.append("duplicate: one trade per stock per day")
    hard_exit = clock.hhmm(cfg["hard_exit"])
    if t >= hard_exit:
        block.append(f"window: after the {cfg['hard_exit']} hard exit")
    return block, warn


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--orders", default=None)
    p.add_argument("--now")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-write", action="store_true")
    a = p.parse_args(argv)
    cfg = state.load_config()
    data = json.loads(Path(a.orders).read_text()) if a.orders else state.read_json("orders.json", {"orders": []})
    now = clock.parse_now(a.now)
    led, events = od.ledger(), state.read_json("events.json", {}) or {}
    verdicts, passed = [], []
    for o in data.get("orders", []):
        block, warn = check_order(o, cfg, led, events, now, passed)
        v = {"id": o.get("id"), "fingerprint": od.fingerprint(o), "verdict": "BLOCK" if block else "PASS",
             "reasons": block, "warnings": warn, "checked_at": now.isoformat(timespec="seconds"), "date": now.date().isoformat()}
        verdicts.append(v)
        if not block and o.get("kind") != "exit":
            passed.append(o)
    if cfg["_unknown_keys"]:
        print(f"note: unknown config keys ignored: {', '.join(cfg['_unknown_keys'])}")
    if not a.no_write:
        old = state.read_json("state/risk.json", {"verdicts": []})
        keep = [v for v in old.get("verdicts", []) if v.get("date") == now.date().isoformat()
                and v["fingerprint"] not in {x["fingerprint"] for x in verdicts}]
        state.write_json("state/risk.json", {"verdicts": keep + verdicts})
    if a.json:
        print(json.dumps(verdicts, indent=2))
    else:
        if not verdicts:
            print("No orders to check: run /nse-size first.")
        for v in verdicts:
            print(f"{v['verdict']}  {v['id']}")
            for r in v["reasons"]:
                print(f"   ✗ {r}")
            for w in v["warnings"]:
                print(f"   ! {w}")
    return 0 if verdicts and all(v["verdict"] == "PASS" for v in verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())
