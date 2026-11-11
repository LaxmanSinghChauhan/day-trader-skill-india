---
name: trader-scanner
description: >-
  Chart Scanner for Indian stocks. Scans thousands of NSE charts for setups:
  opening-range breakouts, flags, oversold bounces. Builds the list of NSE
  shares you can day trade from NSE's own equity list (series EQ, about 2,400
  stocks, or only the Nifty 500), runs a pre-market scan of daily closes
  (20-day closing-high breakout, bull flag, reclaimed the 20-day average,
  oversold, oversold bounce) and an opening-range breakout scan on 5-minute
  bars after 9:35 AM IST, most traded first. Free Yahoo data with .NS symbols,
  NSE holidays, rupees. Use when the user says "scan the market", "find
  setups", "what is breaking out", "opening range breakout", "ORB scan",
  "kaunse stocks breakout de rahe hain", "aaj kya chal raha hai", "scan Nifty
  500", or starts a trading day.
argument-hint: "[universe | daily | orb] [--index nifty500] [--at HH:MM]"
---

# trader-scanner

The Chart Scanner is the first step of a day trade. It reads thousands of
free charts and lists the ones that match a rule. That is all it does. A scan
is a list of charts that match a rule, not a list of stocks to buy, and a
setup on a chart is not a prediction. Most people who day trade lose money
(SEBI's FY23 study: 7 in 10 individual intraday traders lost); the scanner
does not change that. It only saves you from flipping through 2,400 charts
by hand.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                          # NSE's list -> trader/universe.txt
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe --index nifty500         # only the Nifty 500 (faster)
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                             # before the open -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --symbols RELIANCE,TCS,INFY # or --watchlist FILE, --limit 200
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb                               # after 9:35 AM IST -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --at 10:00                    # cut the clock at 10:00 AM IST
```

Flags: `--min-price 50` (rupees), `--min-turnover 20` (crore rupees traded,
daily scan), `--min-volume` (shares, off by default), `--or-minutes 15`,
`--max-confirm 200` (orb stage 2), `--now "2026-11-11 10:00"` (India time) to
pin the clock, `--offline PATH` to read saved files, `--no-write`, `--show N`,
`--json`. Exit code 0 when the scan found something, 1 when it found nothing
or could not run (the reason is one plain line).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/universe.txt` | written by `universe`: one `SYMBOL\|Name` a line, read by `daily` and `orb` (and by trader-news for company names) |
| `trader/watchlist.json` | written by `daily` and `orb`: `mode`, `as_of`, `universe`, `scanned`, `failed`, `hits[]`. trader-news and trader-entry read `hits[].symbol` |
| `trader/config.json` | read by `orb`: `no_entries_after` (default 14:30) |

## The universe

`universe` downloads `EQUITY_L.csv` from nsearchives.nseindia.com (NSE's list
of every listed share) and keeps a row when it has a symbol and a name and its
series is **EQ**: normal rolling settlement, so intraday trading is allowed.
BE and BZ are trade-for-trade (you must take delivery), SM and ST are SME
lots: out. On 11 Nov 2026 that was 2,397 of 2,633 rows. `--index nifty500`
also downloads `ind_nifty500list.csv` and keeps only the 495 that are in the
Nifty 500: the liquid end, and a scan five times faster.

Symbols are NSE symbols as NSE writes them: `RELIANCE`, `M&M`, `BAJAJ-AUTO`.
Yahoo calls them `RELIANCE.NS`; the tool adds and removes the `.NS`.

## The scans

- **daily** (before 9:15): 3 months of daily closes per stock, 20 symbols a
  request. Liquidity: price at least ₹50 and at least ₹20 crore traded
  (price x volume). Setups from closes only: `breakout_20d`, `bull_flag`,
  `reclaim_ma20`, `oversold` (RSI 14 under 30), `oversold_bounce`. Today's
  bar is ignored until the 3:30 PM close.
- **orb** (after 9:35): the opening range is the first 15 minutes, 9:15 to
  9:30. A hit is the first completed 5-minute bar after it that CLOSES above
  the range high. Stage 1 checks closes for every symbol; stage 2 fetches the
  real highs and lows of the 200 most traded candidates. A chart with a
  missing bar is left out. Nothing after `no_entries_after` (14:30).

## Steps

1. `universe` once (weekly is plenty). Ask "all of NSE or the Nifty 500?";
   the Nifty 500 is the sane default for a first scan.
2. Before the open: `daily`. After 9:35 AM: `orb` (or `orb --at HH:MM` to
   replay an earlier moment of today).
3. Say how many charts were scanned, how many matched, and show the list as
   the tool printed it, most traded first. Say if the result is PARTIAL.
4. The user picks ONE chart. Then `/trader-news SYMBOL`, then `/trader-entry SYMBOL`.

## Example: Wednesday 11 November 2026, real data

```
Opening-range breakout scan, Wed 2026-11-11 10:00 AM IST: 15-minute range (9:15 to 9:30 AM), 5-minute bars, Yahoo.
Fetched 50 of 50 charts; 50 usable; 30 candidates, 30 confirmed with real highs and lows.
18 of 50 charts closed above their opening-range high by 10:00 AM:
   9:35 AM  RELIANCE       ₹1,342.80  range 1,330.60 to 1,340.90  +0.14% over
   9:45 AM  SBIN           ₹1,065.65  range 1,055.05 to 1,065.00  +0.06% over
```

That is the Nifty 50 that morning (the test fixture). 18 charts matched the
rule; it does not say which of them kept going.

## What it never does

- Never says "buy". It lists charts that match a rule.
- Never hides a partial scan: failed fetches and unchecked candidates are counted.
- Never treats Yahoo as a live feed: free bars can lag by minutes and its
  9:15 bar for NSE often has no volume.

## Safety

- Education and tooling, not financial advice. A setup is a pattern, not a promise.
- Nothing here places an order. Orders go only through trader-broker, after
  trader-risk passes them and you say yes; paper trading is the default.
