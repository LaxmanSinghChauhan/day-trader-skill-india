---
name: trader-entry
description: >-
  Entry Timer for Indian stocks. Watches a setup bar by bar and tells you the
  moment to get in. Reads free Yahoo 1-minute or 5-minute bars of an NSE
  stock, builds the opening range (the first 15 minutes, 9:15 to 9:30 AM IST,
  by default) and calls the entry on the first completed bar that CLOSES above
  the range high, or above a level you give it (like a 20-day high from the
  scanner), with an optional volume check. Says waiting, triggered, expired or
  no data, in India time, knows NSE holidays and the 9:30 to 14:30 entry
  window, and can watch until it triggers. Long side only. Use when the user
  says "has it triggered", "watch RELIANCE", "tell me when to enter", "entry
  kab lun", "breakout hua kya", "time the entry", or after /trader-scanner.
argument-hint: "[SYMBOL] [--setup orb|level] [--level PRICE]"
---

# trader-entry

The Entry Timer turns "this chart looks ready" into one exact moment: the
close of the first bar that breaks out. Until that bar has closed, the answer
is "waiting". A wick above the level is not a trigger, and a bar that is
still forming does not count. It never places an order.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE                    # opening-range breakout, 5-minute bars
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE --write            # also save trader/entry.json
python3 "${CLAUDE_SKILL_DIR}/entry.py" check INFY --setup level --level 1170.00
python3 "${CLAUDE_SKILL_DIR}/entry.py" watch RELIANCE --until 14:30      # one line per closed bar
python3 "${CLAUDE_SKILL_DIR}/entry.py" watchlist                         # every hit in trader/watchlist.json
```

Other flags: `--or-minutes 15`, `--interval 5m|1m`, `--min-volume-x X` (the
trigger bar's volume against the range bars' average), `--now "2026-11-11
10:00"` (India time), `--offline PATH`, `--json`. Exit code 0 only when the
setup has triggered.

## What it reads and writes

| file | what |
| --- | --- |
| Yahoo chart (`SYMBOL.NS`, 1 day of 5-minute bars) | free, unofficial, can lag a few minutes; a bar counts only once it is complete |
| `trader/config.json` | `no_entries_before` (09:30) and `no_entries_after` (14:30), India time |
| `trader/watchlist.json` | the scanner's hits, for `watchlist` |
| `trader/entry.json` | written on `--write` or by `watch` on a trigger: symbol, status, time, bar, price, level, opening range |

## The rule

- **orb**: the range is the high and low of the 9:15, 9:20 and 9:25 bars. The
  trigger is the first completed bar after 9:30 that closes above the range
  high. Its time is that bar's close (the 9:30 bar closes at 9:35 AM), its
  price is that close.
- **level**: the first completed bar that closes above `--level`.
- **Window**: no trigger before 09:30 or after 14:30. After 14:30 an
  untriggered setup is `expired`: brokers square off intraday positions from
  about 3:20 PM, so a late entry has no room.
- **Volume check**: Yahoo's 9:15 bar for NSE often shows zero volume, which
  makes the range average low. Use `--min-volume-x` with care on free data.

## Steps

1. Get the symbol from the user, or run `entry.py watchlist` after
   `/trader-scanner`. Check `/trader-news` for it first.
2. Run `entry.py check SYMBOL`. Tell the user the status in one line:
   waiting and how far, triggered at what time and price, or expired.
3. To wait for it, run `entry.py watch SYMBOL --until 14:30` in the
   background, or `entry.py check SYMBOL --write` on a `/loop` every 5
   minutes. `watch` wakes just after each bar closes and exits 0 on the
   trigger (it writes `trader/entry.json`). Keep the computer awake.
4. When it triggers, say the time and the price, and that nothing was placed.
   If the trigger is more than a bar old, say that too: a late entry is a
   different trade.
5. Next: `/trader-exit` sets the stop and the target before any buy.

## Example: Reliance, Wednesday 11 November 2026, real data

```
RELIANCE  Wed 2026-11-11 09:36 IST  opening-range breakout (15-minute range) on 5-minute bars (Yahoo, free, can lag)
Opening range 9:15-9:30: high ₹1340.90, low ₹1330.60 (3 of 3 bars).
TRIGGERED 9:35 AM at ₹1342.80: the 9:30 bar (bar 3) closed above the range high ₹1340.90 (+0.14%).
This is the moment to get in, if you take the trade. Nothing was placed.
```

At 9:32 the same command said WAITING: the 9:30 bar was still forming.

## What it never does

- Never places, sizes or approves an order, and never runs `/trader-broker`
  from a background watch: nobody is there to say yes.
- Never calls an entry on a bar that has not closed.
- Never plans a short. v2 is long only.

## Safety

- Education and tooling, not financial advice. A trigger is a rule being met,
  not a recommendation.
- Nothing here places an order. Orders go only through trader-broker, after
  trader-risk passes them and you say yes; paper trading is the default.
