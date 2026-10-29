---
name: nse-briefing
description: >-
  Pre-market briefing for an Indian intraday trader at about 08:45 IST: whether NSE is open today (NSE
  holiday calendar, Muhurat session), the session clock (pre-open, 09:15 open, 09:20 entries, 15:10 hard
  exit, Zerodha's 15:25 MIS square-off), monthly expiry, your limits and how much room is left this week;
  then the market context from public sources with times: GIFT Nifty, how the US and Asia closed, India
  VIX, FII/DII cash flows, RBI or Budget events, and results or board meetings for stocks you watch. Use
  when the user says "good morning", "market kaisa khulega", "pre-market", "morning briefing", "aaj market
  khula hai kya", "is NSE open today", or at the start of a trading day before /nse-scanner.
argument-hint: "[--now 'YYYY-MM-DD HH:MM']"
---

# nse-briefing

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/briefing.py"
python3 "${CLAUDE_SKILL_DIR}/briefing.py" --now "2026-11-10 08:45" --json
```

## Steps
1. Run `briefing.py`. If NSE is closed, say so and stop.
2. Gather the context below with your web tools. **Every number gets its source and its time.** If a
   source can't be reached, say "not checked", never fill it in.

   | Item | Where (official first) | Why it matters for an opening-range trader |
   | --- | --- | --- |
   | GIFT Nifty (NSE IX) | nseix.com, or a broker's market page | Where Nifty may open |
   | US close, Asia now | exchange or index provider pages | Gap risk |
   | India VIX | nseindia.com | High VIX → wider ranges, more fake breakouts |
   | FII / DII cash, yesterday (provisional) | nseindia.com "FII/DII trading activity" | Flow, not a signal |
   | RBI policy, Budget, big data releases today | rbi.org.in, the Union Budget site, MoSPI | Add an event window (nse-news) |
   | Results / board meetings today for the watchlist | /nse-news | Skip those stocks today |
3. Write the briefing in five short lines: open or closed, gap view in plain words (no prediction),
   volatility, events and pauses, your room for the day and the week.
4. Hand on to /nse-scanner after 09:20.

## Rules
- Never predict the day ("market will go up"). Say what is known and when it was known.
- Say the mode (PAPER or LIVE) every morning.
- If last week's loss used most of the weekly cap, say so first.

## Safety
Education and tooling, not financial advice. Paper trading is the default; only nse-kite can lead to an
order, after nse-risk passes that exact order and the user types yes for it.
