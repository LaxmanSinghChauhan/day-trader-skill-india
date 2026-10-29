---
name: nse-entry
description: >-
  Entry Timer for an NSE Stocks-in-Play breakout. For one stock on today's watchlist it says waiting,
  triggered, too far, expired or skipped: triggered when the price crosses the trigger (one tick beyond
  the 09:15–09:20 range), with an IOC limit capped 0.05 % beyond it so you never chase; skipped near the
  circuit limit or if the stock was already traded today; no entries before 09:20 or after 14:30.
  Writes intraday/entry.json for nse-exit. Use when the user says "should I enter", "has it broken out",
  "watch SBIN", "entry de do", "trigger hua kya", "time my entry", or after /nse-scanner.
argument-hint: "[check | watch] SYMBOL [--price P | --quote kite]"
---

# nse-entry

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/entry.py" check SBIN --price 812.40
python3 "${CLAUDE_SKILL_DIR}/entry.py" check SBIN --quote kite      # live LTP + circuit limits (Connect)
python3 "${CLAUDE_SKILL_DIR}/entry.py" watch SBIN --every 20        # polls Kite until not "waiting"
```

Exit 0 only when triggered.

## Statuses
| Status | Meaning |
| --- | --- |
| waiting | Before 09:20, or the price hasn't reached the trigger yet (it says how far) |
| triggered | The price is at or beyond the trigger and within the cap: a LIMIT IOC at the capped price |
| too far | It already ran past the cap (0.05 % beyond the trigger). Don't chase; the trade is gone |
| expired | After 14:30 (`entries_until`) |
| skipped | Within 2 % of the circuit limit, or already traded this stock today |

**Why IOC + a cap:** a breakout order that rests in the book can fill much later at a worse price. IOC
fills now, at the cap or better, or cancels. A partial fill is traded as it is (the stop and exit cover
only the filled quantity).

## Price source
`--quote kite` is live (Connect app). `--price` is whatever the user reads in the Kite app. Without
either, the last 5-minute bar is used and the output says it's not live. Always say which one it was.

## Next
Triggered → `/nse-exit` (stop and hard exit) → `/nse-size` → `/nse-risk` → `/nse-kite`. All of that has
to happen within seconds to a minute, or the price moves on: re-run `check` before placing.

## Never
Never places an order, never says "buy now", never overrides "too far".

## Safety
Education and tooling, not financial advice. Paper trading is the default; only nse-kite can lead to an
order, after nse-risk passes that exact order and the user types yes for it.
