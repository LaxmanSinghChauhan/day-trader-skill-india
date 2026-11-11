---
name: trader-exit
description: >-
  Exit Planner for Indian stocks. Sets your stop and your target before you
  enter, so you know when to get out. Reads the entry from trader-entry (or a
  price you give), puts the stop at the opening-range midpoint by default (or
  the range low, your price, a percent, or a multiple of the ATR), rounds it
  DOWN onto NSE's tick grid (0.05, 0.10 ... by price slab) and sets the target
  at 2R (or 1R, or your price), also on the grid. Refuses a stop at or above
  the entry, a risk too tight to survive the spread, and a flat-by at or after
  the 3:30 PM close. Flat by 15:10 IST by default, before the broker's MIS
  square-off. Long side only. Use when the user says "where is my stop",
  "stop loss kahan lagaun", "set the target", "plan the exit", "risk reward",
  or after /trader-entry triggers.
argument-hint: "[--stop or-mid|or-low|price:X|pct:X|atr:K] [--target 2R|1R|price:X]"
---

# trader-exit

The Exit Planner decides how the trade ends before it begins: the price that
proves you wrong (the stop), the price where you take the money (the target)
and the time you are out no matter what (flat-by). Deciding these after you
are in is how small losses become big ones. It never places an order.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan                                   # from trader/entry.json: or-mid stop, 2R target
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop or-mid --target 1R --write # -> trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol RELIANCE --entry 1342.80 --or-high 1340.90 --or-low 1330.60
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop atr:1.5                    # ATR of the session's bars
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol INFY --entry 1169.40 --setup level --stop pct:1
python3 "${CLAUDE_SKILL_DIR}/exit.py" show                                   # the current plan
```

Other flags: `--flat-by HH:MM`, `--tick X`, `--now`, `--offline FILE` (for an
ATR stop), `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/entry.json` | the triggered entry from trader-entry (symbol, price, time, opening range) |
| `trader/config.json` | `flat_by` (15:10) and `min_reward_risk` (1.0; only a warning here, trader-risk enforces it) |
| `trader/plan.json` | written on `--write`: entry, tick, stop, target, risk a share, reward:risk, flat-by. trader-timemachine, trader-budget and trader-alerts read it |

## The rules

- **Stop** rounds DOWN to the tick, away from the entry. `or-mid` (default
  for an orb), `or-low`, `price:X`, `pct:X`, `atr:K`.
- **Target** rounds to the nearest tick. `2R` (default), `1R`, `1.5R`,
  `price:X`. R is the risk: entry minus stop.
- **The tick.** NSE prices move in steps set by the price: ₹0.01 under ₹250,
  ₹0.05 to ₹1,000, ₹0.10 to ₹5,000, ₹0.50 to ₹10,000, ₹1 to ₹20,000, ₹5
  above. An order off the grid is rejected. NSE fixes each stock's step once
  a month from the previous month's close, so near a boundary the live step
  can differ (SBI at ₹1,065 still moved in 5 paise in November 2026). The
  tool takes the largest step that the entry and the range already sit on;
  `--tick X` sets it yourself. The broker's instrument list has the exact value.
- **Flat-by** is 15:10 IST. Brokers square off intraday (MIS) positions on
  their own from about 3:20 PM (Zerodha from 3:25 PM, with a charge per
  order). A flat-by after 15:20 gets a note; at or after 15:30 it is refused.
- **Refused**: a stop at or above the entry, a target at or below it, a risk
  under 0.05 % of the price, an entry that has not triggered (unless you give
  `--entry`), a short.

## Steps

1. Run `exit.py plan` right after the trigger. Default: or-mid stop, 2R target.
2. Read the plan back in plain words: entry, stop and why there, target,
   rupees at risk per share and as a percent, reward:risk, the tick, flat-by.
3. If the user wants a different stop or target, run it again with the flag.
   Never move a stop further away after the entry.
4. `--write` when they agree. Then `/trader-timemachine`, then `/trader-budget`.

## Example: Reliance, Wednesday 11 November 2026

```
Exit plan: RELIANCE long, Wed 2026-11-11, opening-range breakout on 5-minute bars
  Entry         ₹1,342.80 at 9:35 AM (bar 3)
  Stop          ₹1,335.70  opening-range midpoint: (₹1,340.90 + ₹1,330.60) / 2 = ₹1335.75, rounded down to the 0.10 tick
  Target        ₹1,349.90  1R (one times the risk)
  Risk a share  ₹7.10 (0.53% of the entry)
  Reward:risk   1.0
  Tick          ₹0.10 (stop and target sit on NSE's price grid)
  Flat by       15:10 IST, win or lose: no overnight hold (intraday, MIS)
```

## What it never does

- Never places an order and never moves a stop for you.
- Never promises a stop fills at its price: a gap or a fast market can fill past it.
- Never counts charges: trader-budget shows what brokerage and taxes make of this plan.

## Safety

- Education and tooling, not financial advice. A stop is a plan, not a guarantee.
- Nothing here places an order. Orders go only through trader-broker, after
  trader-risk passes them and you say yes; paper trading is the default.
