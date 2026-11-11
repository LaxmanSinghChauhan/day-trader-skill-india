---
name: trader-budget
description: >-
  Budget Manager for Indian stocks. Sizes every position to your budget and
  your max loss per trade, in rupees and whole shares. Reads the trade plan
  from trader-exit (entry, stop, target), finds the shares that fit inside
  four limits (max loss per trade, position cap, max order, cash after your
  buffer), says which limit decided it, shows what Zerodha's intraday charges
  (brokerage, STT, exchange fees, stamp duty, GST) make of the loss at the
  stop and the gain at the target, and writes ONE bracket order (entry,
  stop-loss, take-profit) to trader/orders.json for trader-risk. No leverage:
  the size always fits in your own cash. Use when the user says "how many
  shares", "kitne shares lun", "size this trade", "position size", "what will
  I lose if the stop hits", "charges kitne lagenge", or after
  /trader-timemachine.
argument-hint: "[--limit [PRICE]] [--write]"
---

# trader-budget

The Budget Manager turns a plan into a number of shares. The rule is simple
and it is the one that keeps accounts alive: decide what you can lose on one
trade first, then let the distance to the stop decide the size. It never
places, approves or schedules an order, and it never raises a limit on its own.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                    # trader/plan.json + trader/config.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --write            # -> trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit            # a limit order at the plan's entry
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit 1342.00 --write
python3 "${CLAUDE_SKILL_DIR}/size.py" --budget 100000 --json
```

## Setup: your limits

Copy `config.example.json` (in this folder) to `trader/config.json` once, and
make the numbers yours:

```json
{"budget": 50000, "cash_buffer_pct": 10, "max_position_pct": 75, "max_order_inr": 40000,
 "max_loss_per_trade_inr": 500, "max_daily_loss_inr": 1500, "max_trades_per_day": 3,
 "min_reward_risk": 1.0, "no_entries_before": "09:30", "no_entries_after": "14:30", "flat_by": "15:10",
 "exchange": "NSE", "product": "MIS", "broker": "zerodha", "paper": true, "allow_margin": false}
```

`"paper": true` stays until the user changes it themselves.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the plan from trader-exit |
| `trader/config.json` | your limits (above) |
| `trader/prices.json` | optional, from trader-alerts: a price under 15 minutes old and above the plan's entry is used instead, because the risk got bigger |
| `trader/portfolio.json` | optional: its cash caps the size |
| `trader/orders.json` | written on `--write`: ONE proposed bracket order, with `why` and the `plan` numbers |

## How many shares

Whole shares only (NSE has no fractional shares), the smallest of:

| limit | how |
| --- | --- |
| max loss | `max_loss_per_trade_inr` / risk a share (entry minus stop) |
| position cap | budget x `max_position_pct` / entry |
| max order | `max_order_inr` / entry |
| cash | (budget minus the cash buffer) / entry |

An intraday (MIS) order would let the broker lend you about five times your
cash. This pack does not use that: `allow_margin` is false and the size
always fits in your own money. Zero shares is a plain refusal, and so is a
reward:risk under your minimum.

## Charges

Indian intraday charges are real money on a small trade, so they are shown,
never hidden: brokerage (0.03 % or ₹20 an order, whichever is lower), STT on
the sell (0.025 %), exchange and SEBI fees, stamp duty on the buy (0.003 %)
and 18 % GST on the fees, worked out the way Zerodha's own calculator does
(rates read 18 Oct 2026). The max-loss limit is on the price move; the report
adds what the charges make of it. It is an estimate: the contract note is final.

## Steps

1. Check `trader/config.json` exists; if not, set it up with the user first.
2. Run `size.py`. Read back: the size, which limit decided it, the rupees at
   risk at the stop, and the same with charges.
3. Say the uncomfortable part when it is there: at 1R, charges can take a
   fifth of the win and add a fifth to the loss.
4. `--write` when they agree. Then `/trader-risk`.

## Example: Reliance, Wednesday 11 November 2026, ₹50,000 budget

```
Limits (whole shares; the smallest one wins):
  max loss      ₹500 max loss / 7.10 risk a share                           70 shares
  position cap  75% of ₹50,000 = ₹37,500 / 1342.80                          27 shares  <- binds
  max order     ₹40,000 / 1342.80                                           29 shares
  cash          budget ₹50,000 minus the ₹5,000 cash buffer = ₹45,000 / 1342.80  33 shares

Size: 27 shares of RELIANCE = ₹36,255.60 at 1342.80. Max loss at the stop: 27 x 7.10 = ₹191.70.
Charges (Zerodha intraday, both legs, an estimate): about ₹38.31 if the stop fills, ₹38.45 at the target.
With charges: lose about ₹230.01 at the stop, make about ₹153.25 at the target.
```

A "1 to 1" trade on the chart is ₹153 against ₹230 after charges. That is
why the Time Machine's coin flip is a losing bet at this size.

Weights mode (`--weights RELIANCE=25,ITC=10 --prices trader/prices.json`)
splits a budget across a list in whole shares; it is kept from v1.

## What it never does

- Never places an order, never uses leverage, never sizes a short.
- Never hides charges or rounds a loss down.
- Never raises a limit: only the user edits `trader/config.json`.

## Safety

- Education and tooling, not financial advice. A size is arithmetic, not a recommendation.
- Nothing here places an order. Orders go only through trader-broker, after
  trader-risk passes them and you say yes; paper trading is the default.
