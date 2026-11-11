---
name: trader-risk
description: >-
  Risk Manager for Indian stocks. Checks every trade against your limits and
  stops anything over them, before it can reach the broker. For a day trade: a
  stop is required, the loss at the stop must fit your max loss per trade
  (measured from the higher of the plan's entry and a fresh price),
  reward:risk must meet your minimum, the day's total risk must fit your daily
  loss limit, no more than your trades per day, and only inside your entry
  window on an NSE trading day (9:15 to 15:30 IST, holidays known). Whole
  shares only, NSE and MIS or CNC only, futures and options off, no margin, no
  shorts. Each order gets PASS or BLOCK with the reason; an exit is never
  blocked by a limit. Use when the user says "check the risk", "is this trade
  ok", "risk check karo", "can I place this", "am I over my limit", or after
  /trader-budget, before /trader-broker.
argument-hint: "[--orders trader/orders.json]"
---

# trader-risk

The Risk Manager is the gate between a proposed order and the broker. It does
not have opinions about the trade. It has your rules, and it applies them the
same way every time: PASS or BLOCK, with the reason in one line. A PASS is a
rules check, not a recommendation. trader-broker only shows an order as ready
if THIS exact order passed today.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                              # the trader/ files -> trader/state/risk.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --now "2026-11-11 10:00"     # pin the clock (India time)
python3 "${CLAUDE_SKILL_DIR}/check.py" --orders trader/orders.json --json
python3 "${CLAUDE_SKILL_DIR}/check.py" --no-write                   # check without recording
```

Exit code 0 when every order passes, 1 when any is blocked.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-budget, or `ticket.py flatten`) |
| `trader/config.json` | your limits |
| `trader/portfolio.json` | cash and shares; if missing, a fresh account funded with the budget |
| `trader/prices.json` | optional fresh prices (trader-alerts) |
| `trader/state/broker.json` | what was placed today: counts toward trades and the daily loss |
| `trader/state/risk.json` | the verdicts, with a fingerprint of each order |

## What blocks an order

Every order:

| rule | blocks when |
| --- | --- |
| format | no symbol or side, no qty, a qty that is not whole shares, a rupee-amount (notional) order, a limit order without a price, an exchange other than NSE, a product other than MIS or CNC, a bracket that is not a day order or misses a leg |
| asset | futures and options (`NIFTY26NOV24000CE`, `RELIANCE26NOVFUT`) unless `allow_options` is true; anything that is not an NSE share |
| short | selling more than you hold, unless `allow_short` is true |

An entry, on top:

| rule | blocks when |
| --- | --- |
| blocked | the symbol is on your `blocked` list |
| size | under `min_order_inr` or over `max_order_inr` |
| position | the stock would be over `max_position_pct` of the account |
| cash | the buy dips into your cash buffer, or needs margin |
| stop | there is no stop (`require_stop`), or it is on the wrong side |
| loss | qty x (entry - stop) is over `max_loss_per_trade_inr` |
| reward:risk | under `min_reward_risk` |
| daily loss | today's risk at the stops plus this one is over `max_daily_loss_inr` |
| trades | `max_trades_per_day` entries already placed today |
| duplicate | the same symbol and side twice, or already placed today |
| window | before `no_entries_before` (09:30) or after `no_entries_after` (14:30), or the market is closed: a weekend, an NSE holiday, outside 9:15 to 15:30 IST |

**An exit is never blocked by a limit.** A sell that only closes what you
hold is checked for format, asset and short sales; every other rule becomes a
warning. Getting out must always be possible.

There is no pattern-day-trader rule in India, so the US pack's day-trade
counter is gone. The loss limit is on the price move; when trader-budget sized the order
the check also shows the loss with Zerodha's charges on top.

## Steps

1. Run `check.py` after `/trader-budget` wrote the order.
2. PASS: say so in one line with the numbers (max loss against the limit,
   reward:risk, trades and daily loss used so far). Then `/trader-broker`.
3. BLOCK: read out every reason. Do not rephrase a reason into something
   softer, and do not suggest changing a limit to get through. The fix is a
   different order (smaller, a closer stop) or no trade.
4. If the order changes in any way, check again: the fingerprint changes too.

## Example: Reliance, Wednesday 11 November 2026

```
PASS  #1 buy RELIANCE 27 shares, entry
          entry 1342.80 (the plan's entry), stop 1335.70, target 1349.90: risk 7.10 a share
          max loss ₹191.70 (limit ₹500), reward:risk 1.00 (min 1)
          with charges (about ₹38.31, Zerodha intraday) the loss at the stop is about ₹230.01
          today before this: 0 of 3 trades, ₹0 of ₹1,500 daily loss

1 passed, 0 blocked at 2026-11-11 09:36 IST. Cash after the passed orders: ₹13,744.40 (paper account).
```

The same order at 8 PM: `BLOCK ... window: the market is closed (Wed
2026-11-11 20:00 IST; the session is 09:15 to 15:30)`.

## What it never does

- Never places an order and never edits your limits.
- Never passes an order it could not price or that has no stop.
- Never blocks an exit because of a daily limit or the entry window.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Nothing here places an order. Orders go only through trader-broker, after
  this check passes that exact order and you say yes; paper trading is the default.
