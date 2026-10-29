---
name: nse-news
description: >-
  News and events monitor for NSE intraday: reads today's corporate announcements for the watchlist from
  NSE and BSE (results, board meetings, dividends, splits and bonuses, fund raising, order wins, pledges,
  ratings, regulatory action, management changes, mergers), tags them, and writes the list of stocks to
  avoid today (results day, board meeting, merger, regulatory or fund-raising news) for nse-risk; also
  sets event windows (RBI policy, Budget) when no new entries are allowed. News warns and blocks; it never
  triggers a trade. Use when the user says "any news on", "results kab hain", "corporate announcements",
  "why is this stock moving", "aaj koi event hai", or before the open.
argument-hint: "[add SYMBOL 'title' | classify | window --from … --to … --why … | show]"
---

# nse-news

Retail traders get news after the price has moved. So here news has one job: keep you **out** of stocks
and minutes where a headline can blow through a stop, and tell you why a stock is in play.

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/events.py" add LT "Outcome of Board Meeting - Financial Results" --time "2026-10-29 08:10" --url https://…
python3 "${CLAUDE_SKILL_DIR}/events.py" classify          # → intraday/events.json (nse-risk reads it)
python3 "${CLAUDE_SKILL_DIR}/events.py" window --from "2026-12-04 09:55" --to "2026-12-04 10:20" --why "RBI policy"
python3 "${CLAUDE_SKILL_DIR}/events.py" show
```

## Where to read (official first)
| What | Source |
| --- | --- |
| Corporate announcements | nseindia.com → Companies → Corporate filings → Announcements; bseindia.com → Corporates → Announcements |
| Results and board-meeting calendar | NSE "Board Meetings" / "Financial Results" pages; BSE "Forthcoming results" |
| Corporate actions (dividend, split, bonus, record dates) | NSE "Corporate Actions" |
| RBI policy, Budget, data releases | rbi.org.in, indiabudget.gov.in, mospi.gov.in |
| Surveillance (ASM/GSM, trade-for-trade) | NSE surveillance pages: skip those stocks |

Use your web tools to read these pages; add each relevant item with `add` (symbol, the exact title, time,
URL), then `classify`. NSE pages often need a browser; if one can't be read, say "not checked".

## Steps
1. Before 09:15: announcements since yesterday's close for the watchlist and today's in-play names.
2. `classify`, then tell the user: avoid list with reasons, other flags, event windows today.
3. During the day, on "why is X moving": read X's latest announcements and summarise in two lines, with
   the time it was filed. Say if the move started before the filing.

## Never
Never treats a headline as a buy or sell signal, never invents a reason for a move, never paraphrases a
filing as more certain than it is (say "the company says").

## Safety
Education and tooling, not financial advice. Paper trading is the default; only nse-kite can lead to an
order, after nse-risk passes that exact order and the user types yes for it.
