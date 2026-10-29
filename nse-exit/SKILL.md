---
name: nse-exit
description: >-
  Exit Planner for an NSE intraday trade, set before the entry. The stop is the larger of 10 % of the
  14-day ATR and 0.4 % of the price, rounded to the NSE tick, and widened tick by tick if it is so tight
  that charges would eat more than a quarter of the risk; the only other exit is a hard exit at 15:10,
  ahead of Zerodha's 15:25 MIS auto square-off. Shows the risk per share, the net loss at the stop after
  charges, the real break-even, and 1R/2R/3R levels for the journal. Writes intraday/plan.json. Use when
  the user says "where's my stop", "exit plan", "stop loss kahan lagayein", "kab nikalna hai", "target
  kya rakhein", or right after /nse-entry triggers.
argument-hint: "[SYMBOL] [--entry PRICE]"
---

# nse-exit

The exit is decided before the entry, never during the trade.

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/plan.py"                          # uses intraday/entry.json
python3 "${CLAUDE_SKILL_DIR}/plan.py" SBIN --entry 812.45 --margin 12000
python3 "${CLAUDE_SKILL_DIR}/plan.py" SBIN --no-fit --json
```

## The plan
| Part | Rule | Why |
| --- | --- | --- |
| Stop | max(10 % × ATR(14), 0.4 % × entry), rounded away from the entry onto the tick | The study's stop was 10 % of ATR; the 0.4 % floor stops Indian charges from eating the trade |
| Charges fit | If net at 1R < 3 × charges, widen the stop one tick at a time until it passes | A trade that can't pay its costs at 1R isn't worth taking (turn off with `--no-fit`) |
| Exit | The stop, or everything at 15:10 (`hard_exit`) | The study held winners to the close; Zerodha auto squares off MIS at 15:25 and charges ₹50 + GST |
| Targets | None. 1R/2R/3R are written as *shadow* levels for the journal only | Winners must run all day for this edge; the journal shows what fixed targets would have done |

The stop goes **to the exchange** right after the fill (nse-kite does it), so it works even if your
laptop sleeps or Claude isn't running.

## Example
An ₹808 stock (illustration), long, trigger ₹808.05, ATR ₹20: 10 % of ATR is ₹2.00, 0.4 % of price is
₹3.23 → stop ₹804.80. 12 shares (the ₹10,000 per-stock cap): charges 0.25R, net at 1R ₹29.39 against
3 × ₹9.61 = ₹28.83, a pass. With the study's ₹2.00 stop alone charges would be 0.40R and the gate would
fail. When a trade misses the gate by a few paise, the stop is widened tick by tick until it passes, and
the plan says so (`widened_for_charges`).

## Never
Never moves a stop further away once the trade is open, never adds a target that exits early without
the user changing the config, never places an order.

## Safety
Education and tooling, not financial advice. Paper trading is the default; only nse-kite can lead to an
order, after nse-risk passes that exact order and the user types yes for it.
