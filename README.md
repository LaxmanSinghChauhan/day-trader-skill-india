# Day Trader skill — India edition

12 Claude skills for **intraday trading on the Indian stock market**: NSE/BSE cash equity, MIS, on
Zerodha Kite Connect. A pre-market briefing, a Stocks-in-Play opening-range scanner, an entry timer, an exit
planner, **Zerodha charges to the paisa**, a replay after charges, a position sizer, a risk manager, an
order executor (paper by default, never without your yes), news, bulk/block deals and a journal.

Plain Python (3.9+, standard library only), MIT. Inspired by the idea of
[Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill), a US pack. This one
is written from scratch for India: NSE's clock and holidays, slab tick sizes, Zerodha's charges and MIS
rules, SEBI's static-IP rule for API orders, NSE/BSE filings, and Indian tax. See
[docs/DESIGN.md](docs/DESIGN.md) for what changed and why.

> **Most intraday traders lose money.** SEBI's FY23 study: 7 in 10 individual intraday traders in equity
> cash lost money, and frequent traders lost more often. This pack doesn't change that. It makes every
> trade's costs and risks visible, and it never places an order you didn't approve.

## Install

As a Claude Code plugin:
```
/plugin marketplace add LaxmanSinghChauhan/day-trader-skill-india
/plugin install day-trader-skill-india@day-trader-skill-india
```
Skills then appear as `/day-trader-skill-india:nse-scanner` and so on. To get plain `/nse-scanner`, copy
the folders instead (keep `nse_core/` next to them; every script imports it):
```bash
git clone https://github.com/LaxmanSinghChauhan/day-trader-skill-india.git
cp -r day-trader-skill-india/nse-* day-trader-skill-india/nse_core ~/.claude/skills/
```
Then `mkdir intraday && cp config.example.json intraday/config.json` in your project, and edit the limits.

## The twelve

| Command | Job | What it does |
| --- | --- | --- |
| `/nse-briefing` | Morning briefing | Is NSE open, the session clock, expiry, your limits and weekly room; GIFT Nifty, VIX, FII/DII, events with sources |
| `/nse-scanner` | Stocks-in-Play scanner | Nifty 500; at 09:20 the stocks whose 09:15 candle drew ≥ 3× usual volume, top 10, long/short from the candle, trigger one tick beyond the range |
| `/nse-entry` | Entry timer | Waiting / triggered / too far / expired / skipped; IOC limit capped 0.05 % past the trigger; circuit-limit room |
| `/nse-exit` | Exit planner | Stop = max(10 % ATR, 0.4 %), widened if charges would eat > 25 % of R; hard exit 15:10 (Zerodha squares off at 15:25) |
| `/nse-charges` | Charges | Brokerage, STT, exchange, SEBI, stamp, GST exactly as Zerodha's calculator; real break-even; the 3 × charges gate |
| `/nse-replay` | Replay | The exact rule over past sessions after charges; win rate and expectancy with honest 95 % ranges |
| `/nse-size` | Position sizer | Per-stock cap, MIS margin, net loss at the stop ≤ your risk; writes the order ticket |
| `/nse-risk` | Risk manager | PASS / BLOCK: market hours, NSE holidays, entry window, events, results day, stop, loss, charges, daily and weekly caps |
| `/nse-kite` | Order executor | Daily login (you type the password), tickets with confirm codes, IOC entry + exchange SL-M stop, exits, sync |
| `/nse-news` | News & events | NSE/BSE announcements tagged; results-day and event-window blocks for the risk manager |
| `/nse-deals` | Deals & disclosures | Bulk/block deal files summarised; how to read PIT insider, SAST and pledge filings |
| `/nse-journal` | Journal | Daily/weekly P&L after charges, expectancy, long vs short, a yearly CSV for ITR-3 |

## A trading day
```
08:45  /nse-briefing      open? events? room left this week?
09:00  /nse-news          results / board meetings today → avoid list
09:20  /nse-scanner sip   stocks in play (after fetching today's first candle)
       /nse-entry         triggered? → /nse-exit → /nse-size → /nse-risk → /nse-kite show → your yes → place
15:10  /nse-kite exits    close anything still open
15:45  /nse-journal day   what happened, after charges
weekly /nse-replay        is the rule still holding up on recorded data?
```

## The strategy, briefly
A published study (Zarattini, Barbon & Aziz, 2024, [SSRN 4729284](https://ssrn.com/abstract=4729284)) found a
5-minute opening-range breakout worked only on "stocks in play" (unusual opening volume). Indian charges
are much higher than in that US study: with a 10 %-of-ATR stop they eat about 0.40R per trade, more than
the average edge the study measured. So the India edition is stricter (≥ 3× volume, top 10, a 0.4 %
minimum stop, a charges gate). **It is a hypothesis to test, not a proven system.**

A first look at real data (10 large caps, Yahoo 5-minute bars, Aug–Oct 2026, run on 29 Oct 2026): the strict
rule fired 12 times, 2 winners, expectancy −0.70R after charges (95 % range −1.26R to −0.12R). Ten stocks
and 60 days is far too little to judge the rule (the scan is meant for the Nifty 500, on Kite data), but it
is exactly why the replay and paper trading come before any real order.

## Safety
- **Paper by default.** Live needs `"paper": false` (only you change it), a PASS from `/nse-risk` for that
  exact order in the last 5 minutes, and that order's confirm code, which Claude only gets after you say yes
  to it in the chat.
- **An exit is never blocked by a limit.** The stop goes to the exchange right after the fill; if Zerodha
  rejects the stop, the position is closed at once.
- **Your keys stay yours.** API key and secret in environment variables; today's token in
  `~/.config/nse-trader/kite.json` (mode 0600). Never in the chat, the repo or `intraday/`. The Zerodha
  login (password, TOTP) is always typed by you on Zerodha's page.
- **SEBI static IP rule (from 1 Apr 2026):** API orders are rejected unless they come from a static IP
  registered in your Kite developer profile. Home broadband won't do; use a VPS or an ISP static IP.

## Data
- **Kite Connect** (₹500/month Connect app): instruments, quotes with circuit limits, historical candles.
  The free Personal app can place orders but has no market data.
- **Yahoo Finance** (free, unofficial): 5-minute bars for ~60 days. Its NSE 09:15 bar has no volume, so
  set `"rvol_minutes": 10` with it. For learning, not for money.
- **Nifty Indices** constituents CSV for the universe; **NSE/BSE** pages for announcements and deals.

## Tests
```bash
python3 -m unittest discover -s tests -v
```
Offline. Charges are checked against 184 results from Zerodha's own calculator; the rest runs the whole
chain on synthetic sessions (round numbers you can check by hand). Real market data is never committed.

## Fine print
Not financial advice. Software that does arithmetic on data you give it; it can't see the future. Intraday
equity profit is speculative business income in India (slab rate, ITR-3). Check rules, charges and holidays
against Zerodha, NSE and SEBI before relying on them: they change.

MIT · [Laxman Singh Chauhan](https://github.com/LaxmanSinghChauhan)
