---
name: nse-charges
description: >-
  Charges Calculator for Indian intraday equity on Zerodha (NSE or BSE, MIS): brokerage (0.03 % or ₹20),
  STT, exchange transaction charge, SEBI fee, stamp duty and GST, exact to the paisa, the real
  break-even exit on the tick grid, and the charges gate (net at 1R must be at least 3 × the trade's
  charges). Use when the user asks "how much are the charges", "brokerage on this trade", "STT",
  "break-even price", "is this trade worth it after charges", "net profit after charges", "kitna charge
  lagega", or before sizing any intraday trade.
argument-hint: "[trade | breakeven | gate] --entry … --stop … --qty …"
---

# nse-charges

In Indian intraday trading, charges are often bigger than the edge. 12 shares of an ₹808 stock bought and
sold the same day with a ₹2.00 stop pay about 0.40R in charges per round trip, so a strategy that earns +0.08R
on average before costs loses money after them. This skill puts the real number on every trade.

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/charges.py" trade --buy 808.05 --sell 830 --qty 12
python3 "${CLAUDE_SKILL_DIR}/charges.py" breakeven --side LONG --entry 808.05 --qty 12
python3 "${CLAUDE_SKILL_DIR}/charges.py" gate --side LONG --entry 808.05 --stop 804.80 --qty 12
python3 "${CLAUDE_SKILL_DIR}/charges.py" gate --side SHORT --entry 512.30 --stop 514.40 --qty 19 --json
```

`gate` exits 0 on PASS and 1 on FAIL. The tick comes from NSE's price slabs unless you pass `--tick`.

## The formula
Rates and rounding follow Zerodha's own brokerage calculator (`cal_intra` in zerodha.com's
`brokerage.js`), verified against 184 calculator results. Brokerage per order is the lower of 0.03 % and
₹20; STT 0.025 % of the sell value (rounded to the rupee); NSE transaction 0.00297 % plus 0.0001 % IPFT
(BSE 0.00375 %); SEBI ₹10 per crore; stamp 0.003 % of the buy value (rounded to the rupee); GST 18 % on
brokerage + transaction + SEBI. For a short, the sell happens first; the charges are the same.

## Example
An ₹808 stock (illustration; tick ₹0.05), long 12 shares, entry ₹808.05, stop ₹804.80 (R = ₹39.00):
charges ≈ ₹9.60, i.e. 0.25R; real break-even ₹808.85; net at the stop −₹48.58; net at 1R ₹29.39 against
3 × ₹9.61 = ₹28.83, so the gate passes, just. Above ₹1,000 the NSE tick is ₹0.10: prices like ₹1,008.05
aren't valid there, and the tool says so.

## Rules
- Always quote the net after charges, never only the gross.
- Say that the contract note is final; this is the calculator's estimate.
- If Zerodha changes rates, the numbers here go stale: say so when the user's contract note disagrees.

## Never
Never sizes, checks or places an order. Never calls a trade good because it passes the gate: the gate
only says the trade can pay for itself if it reaches 1R.

## Safety
Education and tooling, not financial advice. Paper trading is the default for the whole pack; only
nse-kite can lead to an order, after nse-risk passes that exact order and the user types yes for it.
