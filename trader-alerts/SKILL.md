---
name: trader-alerts
description: >-
  Price Alerts for Indian stocks. Rings when a price, a stop or the opening
  bell hits. Turns the trade plan into three alerts in one go (the stop, the
  target and "flat by close" at your flat-by time, 15:10 IST by default), plus
  above / below / stop / target levels, percent moves from the previous close,
  any time of day, and the NSE opening bell at 9:15, each ringing once so you
  are not spammed. Knows NSE hours and the 2026 trading holidays, fetches free
  delayed quotes for NSE symbols and writes trader/prices.json for the sizing
  and risk checks. Use when the user says "alert me at 1350", "set a stop
  alert", "stop pe alert laga do", "is the market open", "market khula hai
  kya", "watch my trade", "get me a quote", "ring at 3:10", or right after
  /trader-exit writes a plan.
argument-hint: "[clock | quote SYMBOL | add --from-plan | check]"
---

# trader-alerts

Price Alerts watches the levels you chose so you do not have to stare at a
chart: the stop, the target, the time to be flat. An alert is information,
not an order. On a live account the stop-loss order at the exchange is what
actually stops you out; the alert tells you it probably did. The target is an
alert only, so that one needs you.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                          # is NSE open? next open
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote RELIANCE --write         # -> trader/prices.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote --holdings --write       # every symbol you hold or plan
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --from-plan                # stop, target, flat-by from trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --stop 1335.70
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol ITC --pct 3
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --at 15:10 --label "flat by close"
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --opening-bell
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                          # rings what hit, once
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list
python3 "${CLAUDE_SKILL_DIR}/alerts.py" reset reliance-plan-stop
```

`check` exits 0 when something rang and 1 when nothing did. `--now
"2026-11-11 15:10"` (India time) pins the clock; `--offline DIR` reads saved
quotes.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/alerts.json` | your rules (`alerts.example.json` here shows the shape) |
| `trader/state/alerts.json` | which rules have rung, so each rings once |
| `trader/plan.json` | `add --from-plan` reads the stop, the target and flat_by |
| `trader/prices.json` | written by `quote --write` and by `check`: the price and when it was read. trader-budget and trader-risk use a price under 15 minutes old |
| Yahoo chart (`SYMBOL.NS`) | free, delayed, unofficial quotes: for alerts only, never for timing an order |

## Rule types

| type | rings when |
| --- | --- |
| `above` / `target` | the price is at or above `price` |
| `below` / `stop` | the price is at or below `price` |
| `pct_move` | the price moved `pct` percent or more from the previous close (`direction` up or down) |
| `opening_bell` | NSE opened today, 9:15 AM (once per trading day) |
| `time` | the India clock passed `at` (HH:MM) on a trading day |

A rule with a `date` is watched on that day only (rules from a plan are for
the plan's day). A price alert rings once and stays quiet until `reset`,
unless it has `"rearm": true`.

## The NSE clock

9:15 AM to 3:30 PM India time, Monday to Friday, minus NSE's trading
holidays. The 2026 list is in the tool (from Zerodha's holiday calendar, read
29 Oct 2026). NSE publishes the next year's list in December; outside the
listed years the clock says so. NSE has no half days. Muhurat trading, the
one-hour evening session on Diwali, is not in this clock.

## Steps

1. Right after trader-exit writes the plan, run `add --from-plan`. Confirm
   the three alerts back to the user: the stop, the target and the flat-by time.
2. Run `check` while the trade is open: every few minutes from a Claude
   scheduled task or `/loop`. A check reads the latest delayed quote; it is
   not a live feed, and a price can pass a level between two checks.
3. Tell the user what rang, one line each. A stop alert on a live account
   means the stop-loss order has probably filled: check `get_positions` and
   record the fill with trader-broker. A target alert means "take it now, or
   decide": `/trader-broker` flatten. "Flat by close" means close anything
   still open, before the broker squares it off around 3:20 PM.
4. On paper, record the sell yourself (`ticket.py fill`) at the price of the alert.

## Example: Reliance, Wednesday 11 November 2026

```
NSE OPEN (2026-11-11 15:10 IST, regular session).
ALERT RELIANCE is ₹1335.40: at or below your stop ₹1335.70 (plan stop: opening-range midpoint).
ALERT Flat by close: it is 15:10 IST (set for 15:10), the market closes at 15:30. If RELIANCE is still open, close it: trader-broker flatten --symbol RELIANCE builds the sell ticket, then trader-risk and your yes.
```

And the clock on the holiday before it: `India 2026-11-10 10:00 (Tuesday):
NSE closed, NSE holiday: Diwali Balipratipada. Next open: 2026-11-11 09:15 IST.`

## What it never does

- Never places, cancels or changes an order. It rings.
- Never treats a free quote as the fill price: your broker's price is the one that fills.
- Never rings the same alert twice unless you reset or re-arm it.

## Safety

- Education and tooling, not financial advice. An alert is information, not an instruction.
- Nothing here places an order. Orders go only through trader-broker, after
  trader-risk passes them and you say yes; paper trading is the default.
