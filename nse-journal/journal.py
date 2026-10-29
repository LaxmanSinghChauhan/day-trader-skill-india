#!/usr/bin/env python3
"""Trade journal: today, this week, all time; long vs short; and a yearly CSV for your tax filing.

  journal.py day [--date 2026-10-29]      journal.py week      journal.py all
  journal.py add --symbol SBIN --side LONG --qty 12 --entry 812.40 --exit 815.10 --stop 809.15 --date 2026-10-29 [--note …]
  journal.py export --year 2026           # → intraday/tax-2026.csv (speculative business income)
Reads closed trades from intraday/state/ledger.json (nse-kite writes them; `add` records a manual trade).
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import charges as ch  # noqa: E402
from nse_core import clock, state  # noqa: E402
from nse_core import orders as od  # noqa: E402


def summary(trades: list[dict]) -> dict:
    n = len(trades)
    if not n:
        return {"trades": 0}
    wins = [t for t in trades if t["net"] > 0]
    losses = [t for t in trades if t["net"] <= 0]
    rs = [t["r"] for t in trades if t.get("r") is not None]
    gross = sum(t["gross"] for t in trades)
    charges = sum(t["charges"] for t in trades)
    return {"trades": n, "wins": len(wins), "win_rate": round(len(wins) / n, 3),
            "gross": round(gross, 2), "charges": round(charges, 2), "net": round(gross - charges, 2),
            "avg_win": round(sum(t["net"] for t in wins) / len(wins), 2) if wins else None,
            "avg_loss": round(sum(t["net"] for t in losses) / len(losses), 2) if losses else None,
            "expectancy_r": round(sum(rs) / len(rs), 3) if rs else None,
            "exits": {r: sum(1 for t in trades if t.get("exit_reason") == r) for r in ("stop", "time", "manual")},
            "long": sum(1 for t in trades if t["side"] == "LONG"), "short": sum(1 for t in trades if t["side"] == "SHORT")}


def show(title: str, trades: list[dict]) -> None:
    s = summary(trades)
    print(title)
    if not s["trades"]:
        print("  no closed trades")
        return
    for t in trades:
        print(f"  {t['date']} {t['symbol']:<12} {t['side']:<5} {t['qty']:>4} × ₹{t['entry_price']:,.2f} → ₹{t['exit_price']:,.2f}"
              f" ({t.get('exit_reason', '?')})  net ₹{t['net']:>9,.2f}  {t.get('r', '')}R{'  [paper]' if t.get('paper') else ''}")
    print(f"  {s['trades']} trades, {s['wins']} wins ({s['win_rate']:.0%}); gross ₹{s['gross']:,.2f} − charges ₹{s['charges']:,.2f}"
          f" = net ₹{s['net']:,.2f}; expectancy {s['expectancy_r']}R; exits {s['exits']}; long {s['long']} / short {s['short']}")
    if s["gross"] > 0 and s["charges"] / s["gross"] > 0.5:
        print(f"  charges took {s['charges'] / s['gross']:.0%} of the gross profit")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("day")
    d.add_argument("--date")
    sub.add_parser("week")
    sub.add_parser("all")
    ad = sub.add_parser("add")
    for f in ("symbol", "side", "date"):
        ad.add_argument(f"--{f}", required=True)
    for f in ("entry", "exit", "stop"):
        ad.add_argument(f"--{f}", type=float, required=f != "stop")
    ad.add_argument("--qty", type=int, required=True)
    ad.add_argument("--note")
    ex = sub.add_parser("export")
    ex.add_argument("--year", type=int, required=True)
    a = p.parse_args(argv)
    led = od.ledger()
    closed = [t for t in led["trades"] if t["status"] == "closed"]
    today = clock.now_ist().date()

    if a.cmd == "add":
        side = a.side.upper()
        rt = ch.round_trip(side, a.entry, a.exit, a.qty)
        stop = a.stop or a.entry
        risk = abs(a.entry - stop) * a.qty
        led["trades"].append({"id": f"M-{a.symbol.upper()}-{a.date}-{len(led['trades'])}", "date": a.date,
                              "symbol": a.symbol.upper(), "side": side, "qty": a.qty, "entry_price": a.entry,
                              "stop": stop, "status": "closed", "paper": False, "manual": True, "exit_price": a.exit,
                              "exit_reason": "manual", "charges": rt.total, "gross": rt.gross, "net": rt.net,
                              "r": round(rt.net / risk, 2) if risk else None, "note": a.note})
        od.save_ledger(led)
        print(f"Recorded: net ₹{rt.net:,.2f} after ₹{rt.total:.2f} charges")
        return 0
    if a.cmd == "day":
        day = a.date or today.isoformat()
        show(f"Journal {day}", [t for t in closed if t["date"] == day])
    elif a.cmd == "week":
        start = od.week_start(today).isoformat()
        show(f"Week from {start}", [t for t in closed if t["date"] >= start])
    elif a.cmd == "all":
        show("All closed trades", closed)
        for side in ("LONG", "SHORT"):
            s = summary([t for t in closed if t["side"] == side])
            if s["trades"]:
                print(f"  {side}: {s['trades']} trades, expectancy {s['expectancy_r']}R, net ₹{s['net']:,.2f}")
    else:
        live = [t for t in closed if t["date"].startswith(str(a.year)) and not t.get("paper")]
        out = state.path(f"tax-{a.year}.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "symbol", "side", "qty", "buy_value", "sell_value", "speculative_turnover_abs_pnl", "charges", "net"])
            for t in sorted(live, key=lambda t: t["date"]):
                buy = t["entry_price"] if t["side"] == "LONG" else t["exit_price"]
                sell = t["exit_price"] if t["side"] == "LONG" else t["entry_price"]
                w.writerow([t["date"], t["symbol"], t["side"], t["qty"], round(buy * t["qty"], 2), round(sell * t["qty"], 2),
                            round(abs(t["gross"]), 2), t["charges"], t["net"]])
        total = round(sum(t["net"] for t in live), 2)
        print(f"{len(live)} real trades in {a.year} → {out}; net ₹{total:,.2f}. Intraday equity is speculative business "
              f"income (taxed at your slab, ITR-3); a speculative loss only offsets speculative income and carries forward 4 years. "
              f"Check with a CA; Zerodha's tax P&L report is the reference.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
