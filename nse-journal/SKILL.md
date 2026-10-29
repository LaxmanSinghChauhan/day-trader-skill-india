---
name: nse-journal
description: >-
  Trade journal for Indian intraday trading: every closed trade with entry, exit, why it closed (stop,
  15:10 time exit, manual), gross, Zerodha charges, net and R; daily and weekly summaries, win rate,
  expectancy in R, long vs short, how much of the gross went to charges; manual trades; and a yearly CSV
  for the tax filing (intraday equity is speculative business income). Use when the user says "how did I
  do today", "journal", "P&L", "aaj ka hisaab", "weekly report", "expectancy", "tax report", "ITR", or at
  15:45 after the close.
argument-hint: "[day | week | all | add … | export --year YYYY]"
---

# nse-journal

The journal is the only honest answer to "does it work for me?". Look at it every evening.

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/journal.py" day
python3 "${CLAUDE_SKILL_DIR}/journal.py" week
python3 "${CLAUDE_SKILL_DIR}/journal.py" all
python3 "${CLAUDE_SKILL_DIR}/journal.py" add --symbol SBIN --side LONG --qty 12 --entry 812.40 --exit 815.10 --stop 809.15 --date 2026-10-29
python3 "${CLAUDE_SKILL_DIR}/journal.py" export --year 2026
```

## The evening review (15:45)
1. `ticket.py status` (nse-kite): nothing may still be open. If it is, say so first.
2. `journal.py day`: read each trade in one line, then the day's net after charges.
3. Compare with the plan: did every trade have its stop at the exchange? Any exit late? Any trade the
   risk check warned about?
4. Weekly, `journal.py all`: expectancy in R, long vs short separately, charges share. Compare with
   `/nse-replay`. If live results fall well below paper or replay, say so plainly.

## When to go from paper to live (suggested gate)
At least a month and a few hundred paper trades; expectancy after charges above zero for long and short
separately; the worst week inside the weekly cap. Then tiny size (1–2 shares) and grow slowly.

## Tax (not advice)
Intraday equity trades are speculative business income, taxed at your slab rate and filed in ITR-3. A
speculative loss can only be set off against speculative income and carries forward for 4 years. The
export lists real trades only (paper trades are excluded). Zerodha's tax P&L report and a CA are the
reference.

## Never
Never counts paper results as real money, never hides a losing day in a weekly average, never prints a
"return" without the charges.

## Safety
Education and tooling, not financial advice. Paper trading is the default; only nse-kite can lead to an
order, after nse-risk passes that exact order and the user types yes for it.
