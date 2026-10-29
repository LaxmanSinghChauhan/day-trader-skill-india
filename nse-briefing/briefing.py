#!/usr/bin/env python3
"""Morning briefing, the parts that are facts: is NSE open today, the session clock, expiry and special
days, your limits and how much room is left this week.

  briefing.py [--now "2026-10-29 08:45"] [--json]
Market context (GIFT Nifty, global cues, India VIX, FII/DII flows, events) is gathered by Claude from
public sources as SKILL.md describes; this script never guesses it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import clock, state  # noqa: E402
from nse_core import orders as od  # noqa: E402


def build(now, cfg) -> dict:
    day = now.date()
    extra = cfg["extra_holidays"]
    led = od.ledger()
    week_loss = -od.realised(led, od.week_start(day), day)
    info = {
        "date": day.isoformat(), "weekday": now.strftime("%A"), "now": now.strftime("%H:%M"),
        "trading_day": clock.is_trading_day(day, extra), "holiday": clock.holiday_name(day, extra),
        "special_session": clock.SPECIAL_SESSIONS.get(day), "calendar_known": clock.calendar_known(day),
        "phase": clock.phase(now, extra), "next_trading_day": clock.next_trading_day(day, extra).isoformat(),
        "monthly_expiry_day": clock.is_last_tuesday(day),
        "session": {"pre_open": "09:00–09:08 orders, 09:08–09:15 matching", "normal": "09:15–15:30",
                    "opening_range": f"09:15–09:{15 + cfg['orb_minutes']:02d}", "entries": f"{cfg['entries_from']}–{cfg['entries_until']}",
                    "hard_exit": cfg["hard_exit"], "zerodha_mis_square_off": "15:25 (₹50 + GST per position)"},
        "mode": "PAPER" if cfg["paper"] else "LIVE",
        "limits": {k: cfg[k] for k in ("capital", "risk_per_trade", "max_daily_loss", "max_weekly_loss",
                                        "max_trades_per_day", "max_open_positions", "max_per_stock")},
        "week_so_far": {"net": od.realised(led, od.week_start(day), day),
                        "room_left": round(max(0.0, cfg["max_weekly_loss"] - max(0.0, week_loss)), 2)},
        "event_windows_today": [w for w in cfg["event_windows"] if w["from"][:10] == day.isoformat()],
        "open_positions": len(od.open_trades(led)),
    }
    return info


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--now")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    cfg = state.load_config()
    b = build(clock.parse_now(a.now), cfg)
    if a.json:
        print(json.dumps(b, indent=2))
        return 0 if b["trading_day"] else 1
    print(f"{b['weekday']} {b['date']} · {b['now']} IST · {b['mode']} mode")
    if not b["calendar_known"]:
        print(f"  ! the NSE holiday list for {b['date'][:4]} isn't loaded: check NSE's circular, add extra_holidays")
    if not b["trading_day"]:
        print(f"  NSE is closed today ({b['holiday'] or 'weekend'}). Next session: {b['next_trading_day']}.")
        if b["special_session"]:
            print(f"  Special session: {b['special_session']}")
        return 1
    s = b["session"]
    print(f"  pre-open {s['pre_open']}; normal {s['normal']}")
    print(f"  opening range {s['opening_range']} · entries {s['entries']} · hard exit {s['hard_exit']}"
          f" · Zerodha MIS square-off {s['zerodha_mis_square_off']}")
    if b["monthly_expiry_day"]:
        print("  last Tuesday: monthly F&O expiry; index heavyweights can swing near the close")
    for w in b["event_windows_today"]:
        print(f"  event pause {w['from'][11:]}–{w['to'][11:]}: {w.get('why', '')}")
    L = b["limits"]
    print(f"  limits: ₹{L['risk_per_trade']}/trade, ₹{L['max_daily_loss']}/day, ₹{L['max_weekly_loss']}/week,"
          f" {L['max_trades_per_day']} trades, {L['max_open_positions']} open, ₹{L['max_per_stock']:,}/stock")
    print(f"  this week so far: net ₹{b['week_so_far']['net']:,.2f}; room before the weekly cap ₹{b['week_so_far']['room_left']:,.2f}")
    if b["open_positions"]:
        print(f"  ! {b['open_positions']} position(s) still open in the ledger: check nse-kite status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
