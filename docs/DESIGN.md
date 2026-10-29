# Design: an intraday skill pack for the Indian stock market

This pack takes its *idea* from [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) (MIT): a chain of small Claude skills, one job each, that hand work to each other through files, use plain Python for the arithmetic, and never place an order without an explicit yes. Nothing here is copied from it. The US pack can't be used in India: its data (Yahoo US symbols, SEC EDGAR, the House Clerk), clock (New York), rules (FINRA pattern-day-trader, STOCK Act) and broker (Alpaca) are all American.

This version is built for **NSE/BSE cash equity, intraday (MIS), on Zerodha Kite Connect**, around one strategy with published evidence, and around the one thing that decides most Indian intraday trades: **charges**.

## What changes for India

| Topic | US pack | This pack |
| --- | --- | --- |
| Session | 9:30–16:00 ET | Pre-open 09:00–09:15, normal 09:15–15:30 IST; NSE holiday calendar; Muhurat session |
| Universe | ~5,900 US listings | Nifty 500 (Nifty Indices constituents CSV), EQ series, price ≥ ₹50 |
| Setup | 15-min opening-range breakout, any stock | **Stocks-in-Play ORB**: 5-min range (09:15–09:20), only stocks with ≥ 3× normal opening volume, top 10, direction from the first candle |
| Tick size | 1 cent | NSE slab ticks: ₹0.01 below ₹250, ₹0.05 to ₹1,000, ₹0.10 to ₹5,000, ₹0.50, ₹1, ₹5 above ₹20,000 |
| Costs | ~zero commissions | **Zerodha intraday charges** (brokerage, STT, exchange, SEBI, stamp, GST), exact to the paisa; a trade must clear 3× its charges at 1R |
| Day-trading rule | FINRA pattern-day-trader | None; MIS margin instead; broker auto square-off at 15:25 (₹50 + GST) |
| Exit | flat by 15:55 | Stop at the exchange, or a hard exit at **15:10** |
| Broker | Alpaca MCP | Zerodha Kite Connect REST (paper by default); SEBI static-IP rule for API orders |
| News | Yahoo RSS, SEC 8-K | NSE/BSE corporate announcements, results and board-meeting calendar |
| "Who is trading" | Congress PTRs (STOCK Act) | NSE/BSE bulk and block deals, SEBI PIT insider disclosures, promoter pledges |
| Replay | 10,000 simulated rest-of-day paths | Replay of the exact rule over past sessions **after charges**, then a bootstrap of the per-trade results for a confidence range on expectancy |
| Tax | short-term gains, wash sales | Intraday equity = speculative business income, slab rate, ITR-3 |

## The strategy, and why this one
Zarattini, Barbon & Aziz (2024), *A Profitable Day Trading Strategy for the U.S. Equity Market* ([SSRN 4729284](https://ssrn.com/abstract=4729284)): a 5-minute opening-range breakout made 3.2 %/year on all stocks but 41.6 %/year (Sharpe 2.81) when restricted to the top 20 "stocks in play" by opening relative volume. Average result per trade was +0.08R for relative volume above 1, and +0.38R above 30×.

With Zerodha's charges, a 10 %-of-ATR stop (₹2.00) on 12 shares of an ₹808 stock makes charges about **0.40R per trade**, more than the paper's +0.08R average edge. So the India edition is stricter: relative volume ≥ 3×, top 10, a minimum stop distance of 0.4 % of price (charges ≈ 0.25R), price-capped IOC entries, and a charges gate. Whether that is enough is exactly what `nse-replay` and weeks of paper trading must show. **Nothing here assumes it works.**

## The chain
```
nse-briefing (08:45)  →  nse-scanner (09:20)  →  nse-entry  →  nse-exit  →  nse-charges
      →  nse-replay  →  nse-size  →  nse-risk (PASS/BLOCK)  →  nse-kite (your yes)  →  nse-journal (15:45)
nse-news, nse-deals: before the open and on demand
```
Every skill reads and writes files in `intraday/` in your project:

| File | Written by | Read by |
| --- | --- | --- |
| `intraday/config.json` | you (from `config.example.json`) | all |
| `intraday/universe.json` | nse-scanner `universe` | nse-scanner |
| `intraday/candles/*.json` | nse-scanner `fetch` (Kite or Yahoo) or you | scanner, entry, replay |
| `intraday/watchlist.json` | nse-scanner | nse-entry, nse-exit |
| `intraday/plan.json` | nse-exit | nse-size, nse-replay |
| `intraday/orders.json` | nse-size | nse-risk, nse-kite |
| `intraday/state/risk.json` | nse-risk | nse-kite |
| `intraday/state/ledger.json` | nse-kite | nse-risk, nse-journal |
| `intraday/events.json` | nse-news | nse-risk |

## Safety, in one place
- Paper trading is the default. Live needs `"paper": false` **and** a per-order confirmation code that only `ticket.py show` prints, for that exact order.
- `nse-risk` must PASS the exact order today; a changed order has a different fingerprint and must be checked again.
- Exits (stop, square-off, cancel) are never blocked by a day limit.
- Kite keys and today's access token live in environment variables or a `0600` file under `~/.config`, never in the chat, the repo or the `intraday/` folder.
- The Zerodha login (password, TOTP) is always done by you in the browser. Nothing automates it.
- API orders must come from a static IP registered in the Kite developer profile (SEBI rule, from 1 Apr 2026).

## Sources
See [SOURCES.md](SOURCES.md).
