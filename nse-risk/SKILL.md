---
name: nse-risk
description: >-
  Risk Manager for NSE intraday orders: PASS or BLOCK with the reason, before anything can reach the
  broker. Checks the market is open (NSE holidays, 09:15–15:30), the entry window (09:20–14:30), event
  windows (RBI policy, Budget) and results-day stocks, the exchange stop, the net loss at the stop after
  charges (₹500), the 3 × charges gate, the per-stock cap (₹10,000), the daily (₹1,500) and weekly
  (₹5,000) loss caps including the worst case of what's already open, trades per day (30), open positions
  and one trade per stock per day. Exits are never blocked by a limit. Use when the user says "check my
  order", "risk check", "is this safe", "can I take this trade", "limit cross toh nahi ho rahi", or
  always before /nse-kite.
argument-hint: "[--orders FILE] [--now 'YYYY-MM-DD HH:MM']"
---

# nse-risk

The gate between a plan and the broker. A BLOCK is final for that order: it isn't shown for a yes and
it isn't sent. These limits keep each loss and each day's losses small; they don't make a trade win.

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                      # intraday/orders.json → intraday/state/risk.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --json --no-write
```

## The checks
| Check | Blocks an entry when |
| --- | --- |
| format | missing fields, quantity not a whole number, LIMIT price off the tick grid, a market or SL-M order without market protection |
| market | NSE is closed (weekend, NSE holiday, outside 09:15–15:30) |
| window | before `entries_from` (09:20), after `entries_until` (14:30), or after the 15:10 hard exit |
| event | now is inside an event window (`event_windows` in config or from nse-news) |
| news | the stock is on today's avoid list from nse-news (results, board meeting …) |
| blocked | the stock is on your `blocked` list |
| short / product | a short while shorts are off; anything other than MIS |
| stop | no exchange stop, or on the wrong side |
| loss | net loss at the stop, charges included, over `risk_per_trade` |
| charges | net at 1R under 3 × charges |
| size | position value over `max_per_stock` |
| daily / weekly loss | realised loss so far + the worst case of everything open + this order would pass the cap |
| trades / positions / duplicate | `max_trades_per_day`, `max_open_positions`, one trade per stock per day |

Warnings (not blocks): the margin wasn't checked; the holiday calendar for this year isn't loaded.

An **exit** (square-off, stop, cancel) is checked for format only. Getting out is always allowed.

Each verdict carries the order's fingerprint. If anything in the order changes (price, quantity, stop),
it is a different order and must be checked again before nse-kite will show it.

## Steps
1. Run it after /nse-size, every time.
2. Read every reason to the user in plain words. A BLOCK ends that order: never suggest editing the
   config to get around it in the moment.

## Safety
Education and tooling, not financial advice. A PASS is a rules check, not a recommendation. Paper trading
is the default; only nse-kite can lead to an order, after this skill passes that exact order and the user
types yes for it.
