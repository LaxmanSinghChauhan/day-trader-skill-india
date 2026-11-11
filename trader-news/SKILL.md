---
name: trader-news
description: >-
  News Monitor for Indian stocks. Tracks breaking news on every NSE stock you
  watch and flags what moves it: Google News headlines per company, each
  company's filings on NSE (results, board-meeting outcomes, director changes,
  deals, order wins, the exchange asking about a price move), upcoming board
  meetings (the Indian results date) and how far each stock is from
  yesterday's close. Shows only what is new since the last check, newest
  first, in India time, tags each item (earnings, deal, order, legal, people,
  halt, regulatory, macro) and marks the filings that matter. Use when the
  user says "any news on RELIANCE", "why is it moving", "results kab hain",
  "koi khabar hai", "check the news", "corporate announcements", "is there a
  board meeting", or before /trader-entry.
argument-hint: "[SYMBOL ...] [--hours 48] [--all]"
---

# trader-news

The News Monitor answers one question before a trade: is there a story on
this stock that changes the picture? A results announcement inside the trade,
a board meeting today, an exchange query about the price move, a deal. It
reads headlines and filings quickly. It does not judge them, and a headline
alone is never a reason to trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                                # watchlist + plan + portfolio symbols
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE INFY SBIN
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE --all --hours 72   # everything, seen or not
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-filings                   # headlines only
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-moves --json
```

Exit code 0 when something new was shown, 1 when nothing is new, 2 when
there are no symbols to check.

## What it reads and writes

| source or file | what |
| --- | --- |
| Google News RSS | one search per stock on the company's name, India edition, the last few days |
| `nsearchives.nseindia.com/content/RSS/Online_announcements.xml` | NSE's feed of corporate announcements: one request covers every company |
| `nsearchives.nseindia.com/content/RSS/Board_Meetings.xml` | NSE's feed of board-meeting notices, with the meeting date |
| Yahoo chart (`SYMBOL.NS`) | the last price against yesterday's close; 3 % or more is flagged MOVING |
| `trader/universe.txt`, else NSE's `EQUITY_L.csv` | symbol to company name (filings are matched by name) |
| `trader/watchlist.json`, `trader/plan.json`, `trader/portfolio.json` | your symbols when `--tickers` is not given (the first 40) |
| `trader/state/news.json` | what you have seen (30 days), so an item shows once |

NSE's feeds hold about one day of filings. Check at least once a day or you
miss some. There is no free official feed of older filings; for those open
the company's page on nseindia.com.

## The rules

- **Filings beat headlines.** An item from NSE is the company's own filing.
  A headline is somebody's summary: open it before you repeat it.
- **Results come out of board meetings.** A board meeting today or tomorrow
  is the results date. A day trade should not be open across it.
- **Marked `!`**: results, board meetings, director or auditor changes,
  deals, an exchange query (spurt in volume, price movement), insolvency,
  legal or regulatory news, pledges.
- **Say the time in IST** and how old the item is.

## Steps

1. Run it for the stock the user picked (or for the scanner's hits).
2. Lead with the price line: the move against yesterday's close.
3. Then the `!` items, then the rest, newest first. One line each on why it
   matters to the setup (for example "board meeting on 14-Nov: results can
   gap the stock past any stop").
4. If a story changes the picture, say so before `/trader-entry` and
   `/trader-exit`: a results date inside the trade, a trading halt, a fund
   raise. Never act on a headline alone.

During the session: `/loop 15m /trader-news`, or a scheduled task each
morning before the open.

## Example: real items, Wednesday 11 November 2026

```
M&M         3,465.00 +5.30% vs yesterday's close 3,290.60 at 15:29 IST  MOVING
RELIANCE    1,335.40 +0.83% vs yesterday's close 1,324.40 at 15:29 IST

! 2026-11-11 20:13 IST  HIMATSEIDE  NSE   Himatsingka Seide Limited: board meeting on 14-Nov-2026
  2026-11-11 19:00 IST  SBIN        NSE   State Bank of India filed with NSE: Analysts/Institutional Investor Meet/Con. Call Updates
```

Then: "Himatsingka's board meets on the 14th: results are likely that day,
so it is not a stock to hold across. Nothing on Reliance that changes the
setup."

## What it never does

- Never trades, never calls a headline a fact, never predicts a reaction.
- Never hides a source that failed: it prints a `note:` line.
- Never uses a login, a paid feed or a scraper that pretends to be a
  browser: only public RSS feeds and files.

## Safety

- Education and tooling, not financial advice. Headlines are leads, not facts.
- Nothing here places an order. Orders go only through trader-broker, after
  trader-risk passes them and you say yes.
