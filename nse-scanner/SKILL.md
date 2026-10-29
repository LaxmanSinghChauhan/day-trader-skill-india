---
name: nse-scanner
description: >-
  Stocks-in-Play Scanner for NSE intraday. Builds the Nifty 500 universe (EQ series), fetches 5-minute
  candles (Zerodha Kite historical API, or free unofficial Yahoo .NS bars), and at 09:20 IST lists the
  stocks "in play": the first 5-minute candle (09:15–09:20) traded at least 3 × its usual volume for that
  slot (last 14 sessions), ranked by that relative volume, top 10, long if the candle is green, short if
  red, no trade on a doji, with the breakout trigger one tick beyond the range. Writes
  intraday/watchlist.json for nse-entry and nse-exit. Use when the user says "scan the market", "stocks in
  play", "opening range breakout", "ORB scan", "which stocks are moving at the open", "aaj kaunse stocks
  chal rahe hain", "9:20 scan", or at the start of a trading day.
argument-hint: "[universe | fetch | sip] [--now 'YYYY-MM-DD HH:MM']"
---

# nse-scanner

The first step after the morning briefing. It doesn't pick stocks: it lists the ones whose opening
candle drew unusual volume, because that's where a published study found an opening-range breakout
worked, and everywhere else it didn't. A list is not a buy signal.

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                       # weekly: Nifty 500 → intraday/universe.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" fetch --source kite            # 5-min bars, ~25 sessions (Connect app)
python3 "${CLAUDE_SKILL_DIR}/scan.py" fetch --source yahoo --symbols LT,SBIN   # free, unofficial
python3 "${CLAUDE_SKILL_DIR}/scan.py" sip                            # after 09:20 IST → intraday/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" sip --now "2026-10-29 09:21" --json
```

Exit code 0 when something is listed, 1 when nothing is (or it couldn't run; the reason is one line).

## The rule (all numbers live in intraday/config.json)
| Step | Rule | Why |
| --- | --- | --- |
| Universe | Nifty 500, EQ series, previous close ≥ ₹50, not on your `blocked` list | Liquid enough to fill near the quote |
| Opening range | The 09:15 five-minute candle (`orb_minutes` 5) | The study found 5 minutes beat 15, 30 and 60 |
| In play | Its volume ÷ the average 09:15-candle volume of the last 14 sessions ≥ 3× (`rvol_min`) | The study's edge lived almost entirely in high relative volume; Indian charges need the strongest |
| Rank | By relative volume, keep the top 10 (`top_n`), then drop dojis | Same order as the study |
| Direction | Green → long only; red → short only; body under 10 % of the range → no trade | Trade with the opening push |
| Trigger | Range high + 1 tick (long) / range low − 1 tick (short) | NSE slab tick, or the tick from Kite's instrument dump |
| ATR(14) | From the previous 14 sessions' daily ranges | nse-exit uses it for the stop |
| Volume window | `rvol_minutes` 5 (the 09:15 bar); **10 with Yahoo** | Yahoo's NSE 09:15 bar has no volume (checked Oct 2026), so measure 09:15–09:25 the same way every day and scan after 09:25 |

## Data
- **Kite** (`--source kite`): needs the Connect app (₹500/month) and today's login (nse-kite `login.py`).
  Historical API, 3 requests a second; 500 symbols take about 3 minutes, so fetch before 09:15 and
  again right after 09:20 for today's first candle (`--symbols` the shortlist to be quick).
- **Yahoo** (`--source yahoo`): free and unofficial; can lag. Its 09:15 bar for NSE stocks carries **zero volume**
  on almost every day, so set `"rvol_minutes": 10` with Yahoo (the scanner tells you). Good for learning, not for money.
- Say how many symbols were scanned and usable, and the time of the data. Never round a partial scan up.

## Steps
1. Weekly: `universe`. Before the open: `fetch`.
2. At 09:20–09:25: `fetch` the shortlist again (today's bar), then `sip`.
3. Tell the user the counts and the list: symbol, side, RVOL, range, trigger. Stocks with news today are
   flagged by nse-news; results-day stocks should be skipped.
4. The user chooses. Hand the chosen one to `/nse-entry`, then `/nse-exit`. Never choose for them.

## Never
Never calls a stock a buy, never prints a profit figure, never sizes or places an order, never calls the
data real time.

## Safety
Education and tooling, not financial advice. Paper trading is the default; only nse-kite can lead to an
order, after nse-risk passes that exact order and the user types yes for it.
