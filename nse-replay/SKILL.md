---
name: nse-replay
description: >-
  Replay for the NSE Stocks-in-Play ORB rule: runs the exact rule over every past session in your candle
  files (rank by opening relative volume, top 10, entry at the trigger with slippage, never past the IOC
  cap, stop as nse-exit sets it, exit at the stop or 15:10), after Zerodha charges, assuming the worst when
  a bar holds both the entry and the stop. Reports trades, win rate with its 95 % range, expectancy in R
  with a day-block bootstrap range, the chance it's above zero, drawdown, long vs short and charges paid,
  and an honest verdict. Use when the user asks "does this strategy work", "backtest", "replay", "pichle
  dino mein kya hota", "is it profitable after charges", "how sure are we", or before paper trading a rule.
argument-hint: "[--symbols A,B] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--seed N]"
---

# nse-replay

Before you risk a rupee, see what the same rule did on the days you already have, after the costs you
would really have paid, and how wide the uncertainty still is.

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/replay.py"                                  # all candle files → intraday/replay.json
python3 "${CLAUDE_SKILL_DIR}/replay.py" --from 2026-08-01 --seed 7
python3 "${CLAUDE_SKILL_DIR}/replay.py" --symbols LT,SBIN --json
```

## What it assumes (say these when you report)
| Assumption | Effect |
| --- | --- |
| 5-minute bars, not ticks | Order inside a bar is unknown; a bar with both the entry and the stop counts as a stop |
| Fill at the trigger + 1 tick, or at the open if it gapped past (skipped if past the IOC cap) | Some slippage; real fills can be worse at the open |
| Stop exit at the stop − 1 tick, or the open if it gapped through | Gaps through stops are counted |
| Exit at the 15:10 bar's open | Matches the hard exit |
| Zerodha intraday charges per trade, exact | The number that decides Indian intraday |
| Today's universe for every day | Survivorship: stocks that left the Nifty 500 aren't in the files |

## Reading the result
- **Expectancy (R)** is the main number: average net result per trade in units of the risk.
- The **95 % range** comes from resampling whole days, because trades on the same day move together.
  If it straddles zero, the honest answer is "we don't know yet", whatever the average says.
- With Yahoo's ~60 days, a strict 3× filter may give only a few dozen trades: too few. Kite's historical
  API gives longer history; record more and replay again.
- Compare long vs short separately before turning either on.

## Never
Never calls a replay a prediction, never rounds a range up to "profitable", never suggests loosening
the rule until the replay looks good (that's overfitting: pick rules before you look, then test).

## Safety
Education and tooling, not financial advice. Paper trading is the default; only nse-kite can lead to an
order, after nse-risk passes that exact order and the user types yes for it.
