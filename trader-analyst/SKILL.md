---
name: trader-analyst
description: >-
  The Earnings Analyst for Indian companies. Reads an NSE company's reported
  numbers and sums up what changed: revenue, gross, operating and net
  margins, net profit and diluted EPS, quarter by quarter in rupees crore with
  Indian fiscal quarters (Q2 FY27), each against the same quarter a year
  earlier, with the last four quarters or the last full year, plus the
  company's latest results filing and next board meeting on NSE. Says plainly
  when the free data has a gap, is stale or is in dollars. Numbers only: it
  never says whether a stock is a buy. Use when the user says "how were the
  results", "results kaise rahe", "read the earnings", "quarterly numbers for
  INFY", "revenue growth", "margins", "EPS", "when are the results", or wants
  the fundamentals behind a stock on the watchlist.
argument-hint: "[SYMBOL ...] [--quarters 6]"
---

# trader-analyst

The Earnings Analyst reads a company's results so you know what you are
looking at before a results day, or when a stock moves on its numbers. It
lays the quarters side by side and says what changed. It does not forecast,
and it does not rate the stock.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE INFY --quarters 8
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE --json
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE HDFCBANK ICICIBANK INFY ITC --metrics trader/metrics.json
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE --no-filings
```

Exit code 0 when every symbol had numbers, 1 when some did, 2 when none did.

## Where the numbers come from, and how far to trust them

India has no free official numbers API like the US SEC's. NSE publishes each
company's results as a filing (PDF and XBRL), one company and one quarter at
a time, not as a feed of numbers. So:

| source | what | trust |
| --- | --- | --- |
| Yahoo Finance fundamentals (`SYMBOL.NS`) | quarterly and annual revenue, cost of revenue, gross profit, operating income, net income, diluted EPS | An unofficial copy of the filed (usually consolidated) results, through a data vendor. About five quarters, sometimes with one missing, sometimes months behind |
| NSE's announcements feed | today's results filing for the company, if there is one | The company's own filing |
| NSE's board-meetings feed | the next board meeting and its date | The company's own notice |
| NSE's `EQUITY_L.csv` or `trader/universe.txt` | symbol to company name | Official |

**The filing is the source. Yahoo is the convenience.** Before anyone relies
on a number, open the filing: the report prints the NSE link.

## What the report says, and the three warnings

- The table: one row per quarter, newest first, in ₹ crore, with the Indian
  fiscal quarter (the year runs April to March: the quarter ending 30
  September 2026 is Q2 FY27).
- Growth is against the same quarter a year earlier. If Yahoo does not have
  that quarter, the cell is `-`. It is never guessed.
- **Gap**: "a quarter is missing before this one". No sum across a gap.
- **Stale**: "Yahoo's quarters for X stop at ..." when the newest quarter is
  more than five months old. Newer results exist: read them on NSE.
- **Dollars**: a few companies (Infosys, Wipro, Dr. Reddy's) also file in the
  US, and Yahoo carries their figures in USD. The report says so and shows
  USD million, not crore.
- "Last 4 quarters" only when the four newest quarters are back to back;
  otherwise the last full fiscal year.
- Banks and insurers report revenue differently: margins can be blank.

## Steps

1. Run it for the stock. Read the first "What changed" line as it is.
2. Say any warning the report printed (gap, stale, dollars) before any number.
3. Point at what stands out: a margin that moved several points, profit above
   operating income (other income or a tax item), a quarter-on-quarter swing
   in a seasonal business.
4. If a board meeting is listed, say its date: results are likely that day,
   and a day trade should not be open across it (`/trader-news` watches it).
5. Never turn the numbers into "so it is a buy". If asked, say what the
   numbers show and that the decision is theirs.

## Example: Reliance, as Yahoo carried it on 11 November 2026

```
Reliance Industries Limited (RELIANCE). ₹ crore except EPS. Source: Yahoo Finance fundamentals (unofficial copy of the filed results).

quarter end fiscal       revenue  rev yoy   gross    oper     net net profit  EPS dil EPS yoy
2026-09-30  Q2 FY27     3,30,601        -   27.1%   12.5%    7.7%     25,548    18.88       -
2026-06-30  Q1 FY27     3,09,468   +27.0%   26.8%   10.5%    6.8%     20,946    15.48  -22.4%
2025-12-31  Q3 FY26     2,64,905        -   29.7%   11.9%    7.0%     18,645    13.78       -  (a quarter is missing before this one)

Last 4 quarters: revenue ₹11,99,033 crore, net profit ₹82,110 crore, diluted EPS ₹60.68.
```

Then: "Yahoo has no September 2025 quarter, so there is no year-on-year
figure for the latest one. Check these against Reliance's filing on NSE
before you quote them."

## What it never does

- Never rates a stock, sets a target price or predicts results.
- Never fills a missing quarter or invents a growth figure.
- Never scrapes a site that blocks robots or needs a login.

## Safety

- Education and tooling, not financial advice. These are reported numbers, and a copy of them at that.
- Nothing here places an order. Orders go only through trader-broker, after
  trader-risk passes them and you say yes.
