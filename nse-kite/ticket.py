#!/usr/bin/env python3
"""Order tickets for Zerodha Kite: show, place (paper by default), exits, status, sync.

  ticket.py show                                   # PASSed orders in plain words + their confirm codes
  ticket.py place ORDER_ID --confirm CODE [--fill 812.40]
  ticket.py exits                                  # open positions + exit codes (use at 15:10)
  ticket.py exit POSITION_ID --confirm CODE [--price 1012.40]
  ticket.py close POSITION_ID --price 1003.95 --reason stop     # paper: record what happened
  ticket.py status | sync                          # sync: live only, reads Kite's orders
A live order needs "paper": false in intraday/config.json, a PASS from nse-risk for that exact order in the
last 5 minutes, and the order's confirm code, which only `show` prints.
"""
from __future__ import annotations

import argparse
import sys
import time as systime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import charges as ch  # noqa: E402
from nse_core import clock, state  # noqa: E402
from nse_core import orders as od  # noqa: E402

MAX_VERDICT_AGE_S = 300
TERMINAL = {"COMPLETE", "CANCELLED", "REJECTED"}


def passed_orders(now) -> list[tuple[dict, dict]]:
    orders = (state.read_json("orders.json", {"orders": []}) or {}).get("orders", [])
    verdicts = (state.read_json("state/risk.json", {"verdicts": []}) or {}).get("verdicts", [])
    out = []
    for o in orders:
        fp = od.fingerprint(o)
        v = next((x for x in verdicts if x["fingerprint"] == fp and x["date"] == now.date().isoformat()), None)
        if v and v["verdict"] == "PASS":
            out.append((o, v))
    return out


def describe(o: dict, paper: bool) -> str:
    mode = "PAPER (simulated)" if paper else "LIVE (real money)"
    s = o["stop"]
    return (f"[{mode}] {o['transaction_type']} {o['quantity']} {o['symbol']} on {o['exchange']}, LIMIT ₹{o['price']:,.2f}, "
            f"IOC, intraday (MIS), value ₹{o['value']:,.2f}\n"
            f"   right after the fill: {s['transaction_type']} the filled quantity, SL-M trigger ₹{s['trigger_price']:,.2f}"
            f" at the exchange (if Zerodha rejects the stop, the position is exited at once)\n"
            f"   if the stop doesn't hit: exit at {o['hard_exit']}\n"
            f"   worst case at the stop price: −₹{o['net_loss_at_stop']:.2f} after charges")


def cmd_show(a, cfg, now) -> int:
    rows = passed_orders(now)
    if not rows:
        print("No order has a PASS from nse-risk today. Run /nse-size and /nse-risk first.")
        return 1
    for o, v in rows:
        age = (now - clock.parse_now(v["checked_at"][:19])).total_seconds()
        print(f"{o['id']}\n   {describe(o, cfg['paper'])}")
        print(f"   risk check: PASS {int(age)} s ago{'  (stale: re-run nse-risk)' if age > MAX_VERDICT_AGE_S else ''}")
        print(f"   to place it, the user says yes to this exact order; code {od.confirm_code(o)}")
    return 0


def kite_client():
    from nse_core.kite import Kite
    return Kite()


def wait_for(kite, order_id: str, seconds: float = 15) -> dict:
    deadline = systime.time() + seconds
    last = {}
    while systime.time() < deadline:
        hist = kite.order_history(order_id)
        last = hist[-1] if hist else {}
        if last.get("status") in TERMINAL:
            break
        systime.sleep(0.5)
    return last


def record_open(led, o, qty, price, now, paper, ids, note=None):
    trade = {"id": f"P-{o['id']}", "date": now.date().isoformat(), "symbol": o["symbol"], "side": o["side"],
             "qty": qty, "entry_price": price, "entry_at": now.isoformat(timespec="seconds"),
             "stop": o["stop"]["trigger_price"], "hard_exit": o["hard_exit"], "status": "open", "paper": paper,
             "tag": o["tag"], "fingerprint": od.fingerprint(o), **ids}
    if note:
        trade["note"] = note
    led["trades"].append(trade)
    return trade


def record_close(trade, price, reason, now, exchange="NSE"):
    rt = ch.round_trip(trade["side"], trade["entry_price"], price, trade["qty"], exchange)
    risk = abs(trade["entry_price"] - trade["stop"]) * trade["qty"]
    trade.update({"status": "closed", "exit_price": price, "exit_at": now.isoformat(timespec="seconds"),
                  "exit_reason": reason, "charges": rt.total, "gross": rt.gross, "net": rt.net,
                  "r": round(rt.net / risk, 2) if risk else None})


def cmd_place(a, cfg, now) -> int:
    match = [(o, v) for o, v in passed_orders(now) if o["id"] == a.order_id]
    if not match:
        print("That order has no PASS from nse-risk today (or it changed since). Nothing placed.")
        return 1
    o, v = match[0]
    if a.confirm.upper() != od.confirm_code(o):
        print("The confirm code doesn't match this order. Nothing placed.")
        return 1
    age = (now - clock.parse_now(v["checked_at"][:19])).total_seconds()
    if age > MAX_VERDICT_AGE_S:
        print(f"The risk check is {int(age)} s old (limit {MAX_VERDICT_AGE_S} s): re-run nse-risk. Nothing placed.")
        return 1
    led = od.ledger()
    if any(t.get("fingerprint") == od.fingerprint(o) for t in led["trades"]) or od.fingerprint(o) in led.get("placed", []):
        print("This exact order was already sent. Nothing placed.")
        return 1
    led.setdefault("placed", []).append(od.fingerprint(o))
    if cfg["paper"]:
        limit = o["price"]
        fill = a.fill if a.fill is not None else limit
        marketable = fill <= limit if o["side"] == "LONG" else fill >= limit
        if not marketable:
            od.save_ledger(led)
            print(f"PAPER: IOC not filled (price ₹{fill:,.2f} is past the limit ₹{limit:,.2f}); cancelled. No position.")
            return 1
        t = record_open(led, o, o["quantity"], fill, now, True, {},
                        None if a.fill is not None else "fill assumed at the limit: pass --fill with the real price")
        od.save_ledger(led)
        print(f"PAPER: filled {t['qty']} {t['symbol']} at ₹{fill:,.2f}; paper stop at ₹{t['stop']:,.2f}; position {t['id']}")
        return 0

    # LIVE
    kite = kite_client()
    od.save_ledger(led)            # remember it was sent before sending, so a crash can't send it twice
    entry_id = kite.place_order(exchange=o["exchange"], tradingsymbol=o["symbol"],
                                transaction_type=o["transaction_type"], order_type="LIMIT", quantity=o["quantity"],
                                price=o["price"], product=o["product"], validity="IOC", tag=o["tag"])
    last = wait_for(kite, entry_id)
    filled = int(last.get("filled_quantity") or 0)
    if filled <= 0:
        print(f"LIVE: entry {entry_id} {last.get('status', 'unknown')}, nothing filled. {last.get('status_message') or ''}")
        return 1
    avg = float(last.get("average_price") or o["price"])
    systime.sleep(1 / max(1, cfg["max_orders_per_second"]))
    s = o["stop"]
    ids = {"entry_order_id": entry_id}
    try:
        ids["stop_order_id"] = kite.place_order(exchange=o["exchange"], tradingsymbol=o["symbol"],
                                                transaction_type=s["transaction_type"], order_type="SL-M",
                                                quantity=filled, trigger_price=s["trigger_price"], product=o["product"],
                                                validity="DAY", market_protection=-1, tag=o["tag"])
    except Exception as e:
        print(f"LIVE: STOP REJECTED ({e}). Exiting the position now, as the ticket said.")
        exit_id = kite.place_order(exchange=o["exchange"], tradingsymbol=o["symbol"],
                                   transaction_type=s["transaction_type"], order_type="MARKET", quantity=filled,
                                   product=o["product"], validity="DAY", market_protection=-1, tag=o["tag"])
        ids["exit_order_id"] = exit_id
    t = record_open(led, o, filled, avg, now, False, ids)
    od.save_ledger(led)
    print(f"LIVE: filled {filled}/{o['quantity']} {o['symbol']} at ₹{avg:,.2f}; stop {ids.get('stop_order_id', 'NOT PLACED')}; "
          f"position {t['id']}. Run `ticket.py sync` to follow it.")
    return 0


def exit_order(t: dict) -> dict:
    return {"kind": "exit", "date": t["date"], "symbol": t["symbol"], "exchange": "NSE", "position_id": t["id"],
            "transaction_type": "SELL" if t["side"] == "LONG" else "BUY", "order_type": "MARKET",
            "quantity": t["qty"], "product": "MIS", "validity": "DAY", "stop": None, "price": None}


def cmd_exits(a, cfg, now) -> int:
    opens = od.open_trades(od.ledger())
    if not opens:
        print("Nothing open.")
        return 0
    for t in opens:
        e = exit_order(t)
        print(f"{t['id']}: {t['side']} {t['qty']} {t['symbol']} from ₹{t['entry_price']:,.2f}, stop ₹{t['stop']:,.2f}"
              f" [{'PAPER' if t['paper'] else 'LIVE'}]\n   exit = cancel the stop, {e['transaction_type']} {t['qty']} at market"
              f" (protected); code {od.confirm_code(e)}")
    return 0


def find_open(led, pid):
    return next((t for t in od.open_trades(led) if t["id"] == pid), None)


def cmd_exit(a, cfg, now) -> int:
    led = od.ledger()
    t = find_open(led, a.position_id)
    if not t:
        print("No open position with that id.")
        return 1
    if a.confirm.upper() != od.confirm_code(exit_order(t)):
        print("The confirm code doesn't match this exit. Nothing sent.")
        return 1
    if t["paper"]:
        if a.price is None:
            print("PAPER exit needs --price (what the market shows now).")
            return 1
        record_close(t, a.price, "manual", now)
        od.save_ledger(led)
        print(f"PAPER: closed {t['id']} at ₹{a.price:,.2f}: net ₹{t['net']:.2f} ({t['r']}R)")
        return 0
    kite = kite_client()
    if t.get("stop_order_id"):
        try:
            kite.cancel_order(t["stop_order_id"])
        except Exception as e:
            print(f"Couldn't cancel the stop ({e}): it may have filled already. Run `ticket.py sync`; nothing else sent.")
            return 1
    e = exit_order(t)
    exit_id = kite.place_order(exchange=e["exchange"], tradingsymbol=e["symbol"],
                               transaction_type=e["transaction_type"], order_type="MARKET", quantity=e["quantity"],
                               product="MIS", validity="DAY", market_protection=-1, tag=t["tag"])
    last = wait_for(kite, exit_id)
    if last.get("status") == "COMPLETE":
        record_close(t, float(last["average_price"]), "manual", now)
        od.save_ledger(led)
        print(f"LIVE: closed {t['id']} at ₹{t['exit_price']:,.2f}: net ₹{t['net']:.2f}")
        return 0
    t["exit_order_id"] = exit_id
    od.save_ledger(led)
    print(f"LIVE: exit {exit_id} is {last.get('status', 'unknown')}: check the Kite app now.")
    return 1


def cmd_close(a, cfg, now) -> int:
    led = od.ledger()
    t = find_open(led, a.position_id)
    if not t or not t["paper"]:
        print("close is for open PAPER positions only (live ones close through Kite; use sync).")
        return 1
    record_close(t, a.price, a.reason, now)
    od.save_ledger(led)
    print(f"PAPER: {t['id']} closed at ₹{a.price:,.2f} ({a.reason}): net ₹{t['net']:.2f} ({t['r']}R)")
    return 0


def cmd_sync(a, cfg, now) -> int:
    led = od.ledger()
    lives = [t for t in od.open_trades(led) if not t["paper"]]
    if not lives:
        print("No open live positions.")
        return 0
    kite = kite_client()
    for t in lives:
        for key, reason in (("stop_order_id", "stop"), ("exit_order_id", "exit")):
            if t.get(key):
                last = (kite.order_history(t[key]) or [{}])[-1]
                if last.get("status") == "COMPLETE":
                    record_close(t, float(last["average_price"]), reason, now)
                    break
    od.save_ledger(led)
    return cmd_status(a, cfg, now)


def cmd_status(a, cfg, now) -> int:
    led = od.ledger()
    day = now.date()
    opens = od.open_trades(led)
    print(f"{'PAPER' if cfg['paper'] else 'LIVE'} mode · today net ₹{od.realised(led, day, day):,.2f} · "
          f"week net ₹{od.realised(led, od.week_start(day), day):,.2f} · open {len(opens)}, worst case −₹{od.open_risk(led):,.2f}")
    for t in opens:
        print(f"  {t['id']}: {t['side']} {t['qty']} {t['symbol']} @ ₹{t['entry_price']:,.2f}, stop ₹{t['stop']:,.2f}, exit by {t['hard_exit']}")
    if opens and now.time() >= clock.hhmm(cfg["hard_exit"]):
        print(f"  It's past {cfg['hard_exit']}: run `ticket.py exits` and close everything.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--now")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    pl = sub.add_parser("place")
    pl.add_argument("order_id")
    pl.add_argument("--confirm", required=True)
    pl.add_argument("--fill", type=float)
    sub.add_parser("exits")
    ex = sub.add_parser("exit")
    ex.add_argument("position_id")
    ex.add_argument("--confirm", required=True)
    ex.add_argument("--price", type=float)
    cl = sub.add_parser("close")
    cl.add_argument("position_id")
    cl.add_argument("--price", type=float, required=True)
    cl.add_argument("--reason", choices=["stop", "time", "manual"], required=True)
    sub.add_parser("status")
    sub.add_parser("sync")
    a = p.parse_args(argv)
    cfg = state.load_config()
    now = clock.parse_now(a.now)
    cmds = {"show": cmd_show, "place": cmd_place, "exits": cmd_exits, "exit": cmd_exit, "close": cmd_close,
            "status": cmd_status, "sync": cmd_sync}
    try:
        return cmds[a.cmd](a, cfg, now)
    except Exception as e:     # a broker error must never look like success
        print(f"Stopped: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
