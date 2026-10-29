# Sources

✅ official or primary · 🔎 secondary (broker blog, forum, news) · checked dates in brackets.

## Market rules and the clock
| Source | Used for | |
| --- | --- | --- |
| [Zerodha market holiday calendar](https://zerodha.com/marketintel/holiday-calendar/) (29 Oct 2026), following NSE circulars NSE/CMTR/71775 and the 15 Jan addition | `nse_core/clock.py` holidays 2026, Muhurat 8 Nov | 🔎 check NSE's circular |
| [Zerodha bulletin: tick size revision from 15 Apr 2025](https://zerodha.com/marketintel/bulletin/408151/revision-in-tick-size-for-nse-derivatives-and-cash-segment-from-april-15-2025) (NSE/CMTR/67133) | `nse_core/ticks.py` slabs; monthly review | 🔎 |
| [Zerodha: changes to auto square-off timings](https://zerodha.com/z-connect/updates/changes-to-the-auto-square-off-timings-for-equity-and-fo) (Dec 2025) | MIS equity square-off 15:25, ₹50 + GST | ✅ broker |
| [SEBI block deal framework, circular of 8 Oct 2025](https://www.scconline.com/blog/post/2025/10/09/sebi-notifies-revised-block-deal-framework-compliance-update-scc-times/) | ₹25 crore minimum, ±3 % | 🔎 summary of the circular |
| SEBI PIT Regulations 2015 (reg. 7), SAST Regulations 2011 (reg. 29, 31) | Disclosure timings in nse-deals | ✅ regulation |

## Zerodha Kite Connect
| Source | Used for | |
| --- | --- | --- |
| [Kite Connect v3 docs](https://kite.trade/docs/connect/v3/) (orders, market quotes, historical, user, login flow) | `nse_core/kite.py`, `nse-kite/` | ✅ |
| [Zerodha support: static IP](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/static-ip), [Kite Connect FAQ](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/kite-connect-api-faqs) (23 Oct 2026) | Static IP from 1 Apr 2026, 2 IPs, one change a week; Personal app has orders; market protection; 10 orders/s | ✅ |
| Zerodha brokerage calculator, `cal_intra` in zerodha.com/static/js/brokerage.js (18 Oct 2026), and 184 calculator results captured that day | `nse_core/charges.py`, `tests/fixtures/zerodha-calculator-intraday.csv` | ✅ |

## Strategy and evidence
| Source | Used for | |
| --- | --- | --- |
| Zarattini, Barbon & Aziz (2024), *A Profitable Day Trading Strategy for the U.S. Equity Market*, [SSRN 4729284](https://ssrn.com/abstract=4729284) | 5-min ORB on Stocks in Play; RVOL buckets; 10 % ATR stop | ✅ paper, read in full |
| [QuantConnect replication](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/) | Independent check of the same idea | 🔎 |
| [Business Standard on SEBI's FY23 intraday study](https://www.business-standard.com/amp/markets/news/over-70-intra-day-traders-incur-losses-during-fy23-reveals-sebi-study-124072401110_1.html) | 71 % of individual intraday traders lost money | 🔎 |

## Data
| Source | Used for | |
| --- | --- | --- |
| [Nifty Indices: Nifty 500 constituents CSV](https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv) | Universe | ✅ |
| Yahoo Finance chart endpoint (unofficial) | Free 5-minute bars; checked 29 Oct 2026 that NSE 09:15 bars carry zero volume | 🔎 |

## Idea
| Source | Used for | |
| --- | --- | --- |
| [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) (MIT) | The idea of a chain of small skills with a risk gate and an explicit yes; no code or text reused | – |
