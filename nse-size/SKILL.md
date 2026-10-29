---
name: nse-size
description: >-
  Position Sizer for NSE intraday (MIS). Picks the largest quantity that stays inside three limits: the
  per-stock cap (₹10,000 by default), your MIS margin × leverage, and a net loss at the stop of at most
  your risk per trade (₹500 by default) with charges included. Writes the order ticket to
  intraday/orders.json: a LIMIT IOC entry plus the stop-loss (SL-M with market protection) that goes to
  the exchange right after the fill. Use when the user says "how many shares", "position size", "kitne
  share lun", "size this trade", "make the order", or after /nse-exit.
argument-hint: "[--margin ₹ | --margin kite]"
---

# nse-size

`${CLAUDE_SKILL_DIR}` is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py" --margin 12000
python3 "${CLAUDE_SKILL_DIR}/size.py" --margin kite          # live margin from Kite (any IP, Personal app ok)
```

## The rule
qty = the smallest of
- per-stock cap: floor(`max_per_stock` ÷ entry)
- margin: floor(margin × `mis_leverage` ÷ entry), when the margin is known
- risk: floor(`risk_per_trade` ÷ risk per share), then one less while the **net** loss at the stop
  (charges included) is still over `risk_per_trade`

It says which limit set the size. With a ₹10,000 cap and a 0.4 % stop, the cap usually binds and the
real risk is well under ₹500: that's expected.

## The ticket
| Field | Value |
| --- | --- |
| Entry | LIMIT, IOC, at the capped price from nse-entry, product MIS |
| Stop | SL-M at the stop price, market protection on (Kite rejects unprotected market orders) |
| Exit | Everything still open at 15:10 |
| Tag | `sip` + 10 characters, unique per order (Kite's limit is 20) |

## Never
Never checks limits (that's nse-risk), never places anything, never sizes above the per-stock cap.

## Safety
Education and tooling, not financial advice. Paper trading is the default; only nse-kite can lead to an
order, after nse-risk passes that exact order and the user types yes for it.
