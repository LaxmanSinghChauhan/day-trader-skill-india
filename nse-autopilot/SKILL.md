---
name: nse-autopilot
description: >-
  Paper-trading autopilot for NSE intraday: runs the whole chain by itself for one trading day on your
  computer: at 08:30 it loads history for the Nifty 500 and keeps the liquid names, after the opening window
  it scans for Stocks in Play, then every 5 minutes it fills resting stop-limit entries on paper when a bar
  reaches the trigger, runs the exact nse-risk check on each order, manages exchange-style stops, closes
  everything at 15:10 and writes a report at 15:35. Same fill rules as nse-replay. Paper only: it never
  sends an order to a broker. Use when the user says "run my bot", "start the bot", "autopilot", "bot chala
  do", "paper trade automatically", "what did the bot do today", or "simulate yesterday".
argument-hint: "[run | simulate --date YYYY-MM-DD | status]"
---

# nse-autopilot

Weeks of paper trades are the go-live evidence, and nobody can click through 30 trades a day by hand.
The autopilot collects that evidence on its own, on paper, with the same rules the replay assumes.

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
caffeinate -i python3 "${CLAUDE_SKILL_DIR}/autopilot.py" run            # macOS: keep the Mac awake; runs until 15:35
python3 "${CLAUDE_SKILL_DIR}/autopilot.py" run --source kite            # Kite data (Connect app + today's login)
python3 "${CLAUDE_SKILL_DIR}/autopilot.py" simulate --date 2026-10-29 --source yahoo   # replay one day through the live loop
python3 "${CLAUDE_SKILL_DIR}/autopilot.py" status
```

Start `run` in its own terminal tab any time before 09:20 (or later: it starts from wherever the day is).
It sleeps until 08:30, then wakes 40 s after every 5-minute bar.

## The day
| Time | What it does |
| --- | --- |
| 08:30 | Loads ~40 days of 5-minute bars for the universe; keeps price ≥ ₹50 and average value ≥ ₹20 cr a day |
| 09:20:40 (Kite) / 09:25:40 (Yahoo) | Scans: opening range, relative volume, top 10 with a direction. Arms a resting stop-limit entry for each (trigger, capped 0.05 % beyond) |
| Every 5 min | Refreshes only what it watches or holds. On each new bar: entry fill → stop and size (nse-exit rules) → **nse-risk check_order** → paper position; stop hits; one attempt per stock |
| 14:30 | Armed entries that never triggered are dropped |
| 15:10 bar | Everything still open is closed at that bar's open |
| 15:35 | Report → intraday/reports/autopilot-DATE.json; trades in the paper ledger for nse-journal |

## Honest by construction
- A bar is used only ~40 s after it ends, and an entry can only fill in a bar that **starts after** the
  watchlist was ready. No look-ahead.
- Fills: trigger + 1 tick, never past the cap; a bar that opens past the cap is a missed trade. Stops: the
  stop − 1 tick, or the open if it gapped through. Entry bar with both: the stop counts.
- Every entry passes the real nse-risk checks (daily and weekly caps, positions, trades per day, events,
  results-day avoid list).
- `simulate` writes to `state/sim-ledger.json`, never to your paper ledger.

## Limits
- Yahoo data is free and unofficial: its NSE 09:15 bar has no volume, so the volume window is 09:15–09:25
  and the scan is at 09:25:40. Fetching ~500 stocks takes a few minutes; a late scan simply arms later.
- 5-minute bars, not ticks: fine for evidence, not for live execution. Live trading needs tick data, the
  VPS with a static IP, and nse-kite's yes per order.
- If the Mac sleeps, the day pauses. `caffeinate -i` stops idle sleep, not a closed lid.

## Never
Never sends an order to a broker, never switches itself to live, never changes your limits.

## Safety
Education and tooling, not financial advice. Paper results are not real results: real fills, rejections
and slippage are worse. Only nse-kite can lead to a real order, after nse-risk passes that exact order and
the user types yes for it.
