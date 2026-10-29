---
name: nse-deals
description: >-
  Bulk deals, block deals and insider disclosures for Indian stocks: summarises NSE/BSE bulk and block
  deal files per stock (net buy or sell in ₹ crore, average prices, clients on both sides), and guides
  reading SEBI insider-trading (PIT) disclosures, takeover (SAST) filings and promoter pledges on NSE/BSE.
  All public and published after the trades: context for why a stock is in play, never a signal and never
  inside information. Use when the user says "bulk deal", "block deal", "who bought", "FII ne kharida
  kya", "promoter selling", "insider trading disclosure", "pledge", or when a watchlist stock is in play
  without news.
argument-hint: "summary FILE.csv [FILE.csv …] [--watchlist]"
---

# nse-deals

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/deals.py" summary ~/Downloads/bulk.csv ~/Downloads/block.csv
python3 "${CLAUDE_SKILL_DIR}/deals.py" summary ~/Downloads/bulk.csv --watchlist --json
```

## What each one is
| Disclosure | What it shows | When it appears | Where |
| --- | --- | --- | --- |
| Bulk deal | One client traded more than 0.5 % of a company's shares in a day | Same evening | NSE Market Data → Bulk Deals; BSE Bulk Deals |
| Block deal | A large negotiated trade, at least ₹25 crore (SEBI, from Dec 2025; ₹10 crore before), within ±3 % of the reference price, in the block windows | Same day | NSE / BSE Block Deals |
| PIT (insider) disclosure | Promoters, directors and designated people trading their own company's shares (over ₹10 lakh in a quarter) | They tell the company within 2 trading days; the company tells the exchange within 2 more | NSE Corporate Filings → Insider Trading; BSE |
| SAST | Holdings crossing takeover thresholds (5 %, then each 2 %) | Within 2 working days | NSE/BSE SAST disclosures |
| Pledge / encumbrance | Promoter shares pledged or released | Within 7 working days | NSE/BSE encumbrance disclosures |

## Steps
1. The user downloads the CSV (or you fetch the official page with your web tools and save it).
2. `summary`, then report the biggest net buyers and sellers for the stocks the user cares about, with
   the date of the data.
3. For PIT, SAST and pledges, read the filings for that stock and summarise: who, how many shares, at
   what price, on which date, filed when.

## Rules
- Say "a client bought", not "smart money bought". Names are as filed.
- A client on both sides of the same stock in a day is usually churn: say so.
- Always say how old the data is. Yesterday's bulk deal is not today's order flow.

## Never
Never calls a disclosure a reason to buy or sell, never suggests anyone has inside information.

## Safety
Education and tooling, not financial advice. Paper trading is the default; only nse-kite can lead to an
order, after nse-risk passes that exact order and the user types yes for it.
