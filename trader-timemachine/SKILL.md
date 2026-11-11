---
name: trader-timemachine
description: >-
  Time Machine for Indian stocks. Replays every possible outcome of a trade
  before you risk a rupee: 10,000 simulated sessions plus every past day the
  setup fired. Takes the plan from trader-exit (entry, stop, target), rebuilds
  the rest of the day 10,000 times from the NSE stock's own 5-minute bars over
  the last 60 days, and re-runs the same rule on every past session. Prints
  the odds of target first, stop first, or neither by your flat-by time, where
  the price sits then, the average R, the history, and one honest verdict,
  then hands off to /trader-budget. Use when the user says "run the time
  machine", "replay this trade", "what are the odds", "kitne chance hain",
  "simulate this trade", "monte carlo", "backtest this setup", "is this a coin
  flip", or after /trader-exit writes a plan, before /trader-budget.
argument-hint: "[path to plan.json, or SYMBOL]"
---

# trader-timemachine

The Time Machine sits between the plan and the money. trader-exit has set
the entry, the stop and the target. Before anything is sized or sent, this
skill asks one question: if today plays out like the stock's own last 60
days, how often does this plan hit the target first, the stop first, or
neither? It answers with 10,000 replays and with the real record of the same
rule on every past session. It is a simulation built from the stock's own
recent bars, not a prediction. Day trading loses most people money, and a
good-looking replay does not change that.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run                    # trader/plan.json, 10,000 replays, seed 19
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --write            # also save trader/timemachine.json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --until 15:15      # replay to the end of the window
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --symbol RELIANCE --date 2026-11-11 \
    --entry 1342.80 --stop 1335.70 --target 1349.90 --entry-time "9:35 AM"
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" chart --from           # ASCII fan chart of the saved run
```

Other flags: `--replays N`, `--seed N` (default 19), `--window N` (default 2
bars), `--offline FILE` (a saved Yahoo chart JSON, `.json` or `.json.gz`),
`--now "2026-11-11 10:00"` (India time) to pin the clock.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the plan from trader-exit: symbol, date, entry, entry_time / entry_bar, stop, stop_rule, target, tick, flat_by, opening range |
| Yahoo chart API | one request: 60 days of 5-minute bars of `SYMBOL.NS` (`range=60d&interval=5m`), free and unofficial, can lag |
| `trader/timemachine.json` | with `--write`: `{plan, mc, history}` plus the verdict. `mc` holds the odds, percentiles, the fan-chart bands, 160 sample paths and a 24-bin histogram |

## How it works

1. **The pool.** It keeps only FULL sessions before the plan's date: all 72
   five-minute bars from 9:15 AM to 3:15 PM India time. That is the window
   an intraday (MIS) trade can live in: brokers square off around 3:20 PM,
   and Yahoo's 60-day history has no prices for NSE's last two bars anyway.
   Days with a gap, and today, are left out. Every bar becomes four ratios to
   the bar before it: open, high, low and close over the previous close.
2. **One replay.** Start at the entry price. For each bar left in the day,
   pick a past bar from the same time of day (plus or minus 2 bars) at
   random, and scale it to the current price. Bar by bar, it checks the stop
   first, then the target. A bar that touches both counts as the stop.
3. **10,000 replays** give four odds. Target first. Stop first. Neither,
   which means the trade was still open at `--until` (default: the plan's
   flat-by, 15:10). Green, which means target first or above the entry then.
   R is +1 at a 1R target, -1 at the stop, and otherwise the distance from
   the entry divided by the risk. A gap through the stop still counts as -1R
   here. A real fill can be worse.
4. **The history.** The plan's own rule (the same opening range, stop rule
   and target R, stops and targets on the plan's tick) runs again on every
   one of those past sessions. That is what really happened, not a simulation.
5. **The verdict** is one line from the numbers. It looks only at the
   replays that hit one side, and asks how often the target came first. A
   bigger target needs to win less often to break even: 1 in (1 + R). That
   is 50 % at 1R, 33 % at 2R. Less than 5 points from break-even: "Close to
   a coin flip". 5 to 15 points: "Leans toward the target" or "the stop".
   15 or more: "Strongly toward" one of them.

**Know what the replays cannot see.** Each bar is drawn on its own, so a
replay has no momentum: it measures how far this stock usually moves in the
time left, not whether a breakout tends to follow through. The history part
is the evidence for that. And **charges are not in R**: a 1R winner pays
brokerage and taxes too (trader-budget shows them), so break-even is a little
above 50 % in real life.

## Steps

1. Run it right after `/trader-exit` wrote the plan. `--write` to keep it.
2. Read out the four odds, the history line and the verdict, word for word.
   Do not round "48.2 % vs 48.9 %" into "about even odds in your favour".
3. Say what it is: a replay of this stock's last 58 or so sessions. Results,
   news and circuit limits can do what those days never did.
4. If the verdict leans toward the stop, say so plainly and ask whether they
   still want to size it. Then `/trader-budget`.

## Example: Reliance, Wednesday 11 November 2026, real data, seed 19

```
RELIANCE buy, Wednesday 2026-11-11: entry 1342.80 at 9:35 AM (bar 3), stop 1335.70, target 1349.90 (1R, risk 7.10 a share).
10,000 replays of the rest of the session, 9:35 AM to 3:10 PM (67 five-minute bars), seed 19.

  target first   48.2 %
  stop first     48.9 %
  neither        3.0 %    still open at 3:10 PM

History: the same rule (15-min opening range, stop at the opening-range midpoint, 1R target) on each of those 58 real sessions fired 30 times: 13 target, 11 stop, 6 neither. Average R +0.017.

Close to a coin flip: target first 48.2 % vs stop first 48.9 %.
```

What happened that day: the stop came first (the 11:10 bar traded down to
1,333.40). The Time Machine did not know that. It said coin flip, and a coin
flip can land either way. That is the point of looking before you risk a rupee.

## What it never does

- Never predicts. It reports frequencies from past bars.
- Never hides a thin pool: under 20 full sessions it refuses.
- Never places, sizes or approves anything.

## Safety

- Education and tooling, not financial advice. A simulation is not a forecast.
- Nothing here places an order. Orders go only through trader-broker, after
  trader-risk passes them and you say yes; paper trading is the default.
