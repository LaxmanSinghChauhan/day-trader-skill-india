# The Day Trader skill, India edition

11 Claude skills for day trading Indian stocks: scan thousands of NSE charts, track breaking news, time every entry and exit, and replay every outcome before you risk a rupee.

This is the Indian twin of [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill)
(MIT), skill for skill: the same eleven jobs, the same files, the same
"nothing goes through until you say yes". What changed is everything that is
American: New York time became India time, the SEC became NSE, dollars became
rupees with Zerodha's charges, Alpaca became Zerodha Kite, and the Pelosi
Tracker became the Big Bull Tracker. The tools are plain Python that read
free public data: Yahoo Finance charts (`.NS` symbols), NSE's own lists,
feeds and deal files, and Google News.

One scans NSE's 2,400 charts for setups. Another tracks news and company
filings on every stock you watch. One watches a setup bar by bar and tells
you the moment to get in, and another sets your stop and your target before
you do, on NSE's tick grid. And the Time Machine: before you risk a rupee, it
replays the rest of the session 10,000 times from the stock's own recent
bars, plus every past day the same setup fired, and tells you the honest odds.

And no trade goes through until you say yes. Nothing in this pack can place
an order on its own. Paper trading is the default.

> **Most intraday traders lose money.** SEBI's study of FY23 found that 7 in
> 10 individual intraday traders in the cash market lost money, and those who
> traded more often lost more often. This pack does not change that. It makes
> the rule, the odds and the charges visible before the trade.

## Install

Paste this into Claude:

```
https://github.com/LaxmanSinghChauhan/day-trader-skill-india

install skill
```

Or as a plugin, in Claude Code:

```
/plugin marketplace add LaxmanSinghChauhan/day-trader-skill-india
/plugin install day-trader-skill-india@day-trader-skill-india
```

Claude Code namespaces plugin skills, so installed as a plugin they show up as
`/day-trader-skill-india:trader-scanner` and so on. Copy the folders instead if
you want plain `/trader-scanner`:

```bash
git clone https://github.com/LaxmanSinghChauhan/day-trader-skill-india.git
cp -r day-trader-skill-india/trader-* ~/.claude/skills/
```

Project-local instead of global: copy the same folders into your repo's
`.claude/skills/`. The tools need Python 3.8 or newer. Nothing to pip
install, no API key, no signup. Then set your limits once:

```bash
mkdir -p trader && cp ~/.claude/skills/trader-budget/config.example.json trader/config.json
```

## The eleven

| command | job | what it does |
| --- | --- | --- |
| `/trader-scanner` | Chart Scanner | Scans NSE charts for setups: opening-range breakouts, flags, oversold bounces. All of NSE's EQ series, or the Nifty 500. |
| `/trader-news` | News Monitor | Headlines, NSE filings and board-meeting dates for every stock you watch, and how far it has moved today. |
| `/trader-entry` | Entry Timer | Watches a setup bar by bar and tells you the moment to get in. |
| `/trader-exit` | Exit Planner | Sets your stop and your target before you enter, on NSE's tick grid, flat by 15:10. |
| `/trader-timemachine` | Time Machine | Replays every possible outcome of a trade before you risk a rupee: 10,000 simulated sessions plus every past time the setup fired. |
| `/trader-risk` | Risk Manager | Checks every trade against your limits and stops anything over them. |
| `/trader-budget` | Budget Manager | Sizes every position to your budget and your max loss, and shows what Zerodha's charges make of it. |
| `/trader-broker` | Order Executor | Sends approved orders to Zerodha, paper trading by default, never without your yes. |
| `/trader-alerts` | Price Alerts | Rings when a price, a stop or the opening bell hits. Knows NSE's hours and holidays. |
| `/trader-analyst` | Earnings Analyst | Reads a company's quarterly results and sums up what changed, in crore. |
| `/trader-bigbull` | Big Bull Tracker | Reads NSE's bulk and block deals the evening they are published: who bought, who sold, by name. |

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads
what the last one wrote:

```
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker   (one trade)
alerts: stop, target, flat by 15:10                                           (while it is open)
news / analyst / bigbull                                                      (on a schedule)
```

An example, with real data: Reliance, Wednesday 11 November 2026.

1. **`/trader-scanner`** at 10:00 AM IST: of the Nifty 50's charts, 18 had
   closed above their 15-minute opening range. RELIANCE is one: range
   1,330.60 to 1,340.90, the 9:30 candle closed at 1,342.80, 0.14 % over the top.
2. **`/trader-news`**: that day's Reliance headlines, in India time, and the
   move against yesterday's close. NSE's feeds carried no Reliance filing and
   no board-meeting notice that day, so no results date sat inside the trade.
3. **`/trader-entry`** watched RELIANCE bar by bar. At 9:32 it said waiting
   (the 9:30 bar was still forming). At 9:35 it said triggered: the first
   5-minute close above the range, 1,342.80.
4. **`/trader-exit`** set the plan before the entry: stop at the range's
   midpoint, 1,335.75, rounded down to NSE's 10-paise tick: 1,335.70. So
   ₹7.10 a share at risk; target one times that risk, 1,349.90; flat by
   15:10 either way.
5. **`/trader-timemachine`** replayed the rest of the day 10,000 times, each
   5-minute candle drawn from Reliance's own candles at that time of day over
   the previous 58 full sessions (seed 19, so anyone can repeat it): target
   first 48.2 %, stop first 48.9 %, still open at 3:10 PM 3.0 %. It also
   re-ran the same rule on those 58 real sessions: it fired 30 times, 13 hit
   the target, 11 the stop, 6 neither. Its verdict: close to a coin flip.
6. **`/trader-budget`** with a ₹50,000 account: 27 shares (₹36,255.60), the
   position cap decides. If the stop fills at 1,335.70 the loss is ₹191.70,
   and Zerodha's charges add about ₹38.31: ₹230.01. At the target the trade
   makes ₹191.70 minus ₹38.45: ₹153.25. It writes one bracket order: buy 27
   RELIANCE, stop-loss 1,335.70, take-profit 1,349.90.
7. **`/trader-risk`** checks it against your limits: the max loss, the daily
   loss limit, trades per day, reward to risk, the entry window, position
   size and cash. PASS or BLOCK, with the reason.
8. **`/trader-broker`** shows you the ticket in plain words. You type yes for
   that exact order. On paper (the default) the fill is recorded in a file
   and nothing goes anywhere. On a live account Claude calls Zerodha's
   `place_order` (Kite MCP), and Claude's own "Allow once / Deny" card asks
   you one more time.
9. **`/trader-alerts`** rings on the stop, the target and at 15:10 to flatten
   whatever is still open.

What happened that day: the stop came first, at 11:10. A coin flip that
costs ₹230 when it loses and pays ₹153 when it wins is a losing bet, and the
pack shows you that before the trade, not after.

## The tools

All standard-library Python. The data tools read public endpoints and are
polite about it.

```bash
python3 trader-scanner/scan.py universe --index nifty500               # NSE's list, the Nifty 500
python3 trader-scanner/scan.py daily                                   # pre-market setups
python3 trader-scanner/scan.py orb --at 10:00                          # opening-range breakouts so far
python3 trader-news/news.py --tickers RELIANCE --hours 24              # headlines, NSE filings, today's move
python3 trader-entry/entry.py check RELIANCE --setup orb               # waiting / triggered / expired
python3 trader-entry/entry.py watch RELIANCE --every 30                # bar by bar until it triggers
python3 trader-exit/exit.py plan --stop or-mid --target 1R --write     # -> trader/plan.json
python3 trader-timemachine/timemachine.py run --write                  # 10,000 replays + the history
python3 trader-budget/size.py --write                                  # -> trader/orders.json
python3 trader-risk/check.py                                           # PASS / BLOCK per order
python3 trader-broker/ticket.py show                                   # the tickets, READY or not
python3 trader-alerts/alerts.py add --from-plan                        # stop, target, flat by 15:10
python3 trader-alerts/alerts.py check                                  # rings what hit, once
python3 trader-analyst/facts.py RELIANCE                               # quarters, growth, EPS
python3 trader-bigbull/deals.py index --min-cr 25                      # today's big deals, by name
```

```bash
python3 -m unittest discover -s tests -v
```

The tests run offline, on fixtures cut from real data of 11 November 2026:
NSE's equity list and Nifty 500 list, the Nifty 50's 5-minute bars and daily
closes, Reliance's 5-minute bars for the 60 days before, NSE's announcement
and board-meeting feeds, and the day's bulk and block deals. They reproduce
every number in the example above.

## What changed for India

| | US pack | India edition |
| --- | --- | --- |
| Market | NYSE and Nasdaq, 9:30 to 4:00 New York time | NSE, 9:15 to 3:30 India time, NSE's 2026 holidays, no daylight saving |
| Universe | about 5,900 US stocks (Nasdaq Trader) | 2,397 NSE stocks in series EQ, or the Nifty 500 (NSE's own lists) |
| Prices | cents | NSE's tick grid: 0.01, 0.05, 0.10, 0.50, 1, 5 by price slab |
| Day window | entries 9:45 to 15:30, flat by 15:55 | entries 9:30 to 14:30, flat by 15:10 (brokers square off MIS around 3:20) |
| Charges | not counted | Zerodha's intraday charges at the stop and the target, and taken from the paper cash |
| Time machine | 78 bars a day | 72 bars, 9:15 to 3:15: the window an intraday trade can live in |
| Broker | Alpaca MCP, with a paper account | Zerodha Kite MCP. No paper account exists, so paper fills are recorded here |
| Bracket order | one order at the broker | the entry, then an SL-M stop at the exchange; the target is an alert |
| Rules | FINRA pattern-day-trader guard | none in India: removed. SEBI's static-IP rule for API orders is explained |
| News | Yahoo headlines, SEC 8-K | Google News, NSE's announcement and board-meeting feeds |
| Earnings | SEC XBRL facts (official) | Yahoo's copy of the filed results (unofficial), gaps and stale data flagged |
| Who is trading | Congress's disclosures (Pelosi Tracker) | NSE's bulk and block deals (Big Bull Tracker) |

## Fine print

**Not financial advice.** This is software that reads public data and does
arithmetic. It does not know your situation and it cannot see the future.
Most people who day trade lose money. You can lose money. Decide for
yourself, and talk to a SEBI-registered adviser if you need advice.

**No trade goes through until you say yes.** Only `/trader-broker` can lead to
an order, and only after `/trader-risk` passes that exact order and you type
yes for it in the chat. On a live account, set Zerodha's order tools to
"Needs approval" in Claude, never "Always allow", so Claude's own "Allow once
/ Deny" card is a second check. No futures, options, margin, short selling or
leverage unless you turn them on.

**Paper first.** `"paper": true` is the default in `config.example.json`.
Zerodha has no paper-trading account, so a paper trade is two files in your
`trader/` folder, with the charges taken out. Going live needs your own Kite
Connect app and your own copy of Zerodha's MCP server (their hosted one reads
your account but leaves out the order tools), keys in environment variables
and never in the chat, and a static IP registered with Zerodha (SEBI's rule
for API orders since 1 April 2026).

**The Time Machine is a simulation, not a prediction.** It is built from the
stock's own last 60 days of 5-minute bars, each bar drawn on its own, so it
measures how far the stock usually moves, not whether a breakout follows
through. The future can do things those 60 days never did: results, a
circuit limit, a headline. And it does not count charges.

**Charges are an estimate.** They follow Zerodha's public calculator (rates
read 18 October 2026). Your contract note is final. Rates change.

**A stop is a plan, not a guarantee.** In a fast market or across a gap, a
stop order can fill well past its price. The max loss shown is the loss at
the stop price.

**The data is free and unofficial.** Yahoo Finance's chart endpoint is not an
official API: it can lag by minutes, change or rate-limit you, its 9:15 bar
for NSE often has no volume, and its copy of company results can be stale or
missing a quarter. NSE's feeds hold about one day. The tick size comes from
price slabs that NSE resets once a month. Check anything that matters
against your broker before you act on it.

**Holidays.** The NSE holiday list in the tools is for 2026. NSE publishes
the next year's list in December: until the tools are updated they say the
calendar is unknown for other years.

**Bulk and block deals are public, not inside information.** They are
published after the market has closed, and the name is as the broker typed it.

**Taxes.** In India, profit from intraday equity trades is speculative
business income, taxed at your slab rate. Nothing here is tax advice.

## Files

```
trader-scanner/     SKILL.md, scan.py
trader-news/        SKILL.md, news.py
trader-entry/       SKILL.md, entry.py
trader-exit/        SKILL.md, exit.py
trader-timemachine/ SKILL.md, timemachine.py
trader-risk/        SKILL.md, check.py
trader-budget/      SKILL.md, size.py, config.example.json, targets.example.json
trader-broker/      SKILL.md, ticket.py, claude_desktop_config.example.json
trader-alerts/      SKILL.md, alerts.py, alerts.example.json
trader-analyst/     SKILL.md, facts.py, metrics.example.json
trader-bigbull/     SKILL.md, deals.py, bigbulls.example.txt
tests/              unittest suite + offline fixtures
```

## Where the first India pack went

Before this, the repo held a different pack: 13 `nse-*` skills built around
one strategy (Stocks-in-Play opening-range breakout), with a morning
briefing, a replay after charges, a journal and a paper autopilot. It is kept
whole on the [`v1-original`](https://github.com/LaxmanSinghChauhan/day-trader-skill-india/tree/v1-original)
branch.

## Credits

MIT. The design, the eleven skills and most of the code are from
[The Day Trader skill](https://github.com/Jakeschincariol/day-trader-skill)
by [Jake Schincariol](https://opusjake.ai) (imported at commit `3d0f4ef`; the
git history shows every change made for India). India edition by
[the day-trader-skill-india contributors](https://github.com/LaxmanSinghChauhan/day-trader-skill-india).
