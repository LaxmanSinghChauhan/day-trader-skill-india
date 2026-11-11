---
name: trader-broker
description: >-
  Order Executor for Indian stocks. Sends approved orders to your broker,
  paper trading by default, never without your yes. Shows each order as a
  plain ticket (the entry, the stop-loss order that goes to the exchange, the
  target, the max loss at the stop and the charges on top) plus the exact JSON
  for Zerodha's place_order tool (Kite MCP), records your yes word for word,
  then on a live account Claude's own Allow once / Deny card asks again. On
  paper it records the simulated fill itself: Zerodha has no paper account.
  Builds the sell ticket that closes a day trade by your flat-by time, records
  fills, and logs each trade's max loss so trader-risk can hold the daily
  limit. Covers setting up Zerodha's Kite MCP server (hosted for reading,
  your own copy for orders), SEBI's static-IP rule for API orders, and setting
  order tools to "Needs approval". Use when the user says "place the order",
  "buy it", "order laga do", "execute", "close my position", "square off",
  "flatten", "connect Zerodha", "set up paper trading", or after /trader-risk
  passes.
argument-hint: "[order number]"
---

# trader-broker

The Order Executor is the only skill in this pack that can lead to a real
order, so it is the strictest. On a live account an order reaches the market
only after three separate gates, every time, for every order:

1. **trader-risk passed this exact order today** (matched by fingerprint).
2. **The user typed an explicit yes for this one order** in the chat.
3. **The user clicked Allow once** on Claude's own permission card, which
   appears because the order tool is set to "Needs approval".

Two yeses from the user, one PASS from the rules. No yes, no order. On a
**paper** account (the default) gates 1 and 2 are the same and nothing goes
to any broker: the fill is written to a file.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                     # every ticket, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" paper --index 1 --price 1343.10      # PAPER: the simulated fill
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status placed --broker-id ID --filled-qty 27 --filled-price 1343.10
python3 "${CLAUDE_SKILL_DIR}/ticket.py" fill --symbol RELIANCE --side sell --qty 27 --price 1349.90
python3 "${CLAUDE_SKILL_DIR}/ticket.py" flatten --symbol RELIANCE --qty 27 --price 1346.00
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

`ticket.py` never talks to a broker. It renders tickets, checks that a reply
is a real yes for that order, builds the flatten ticket, and keeps the log in
`trader/state/broker.json`. `--now "2026-11-11 10:00"` pins the clock (India time).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-budget writes it; `flatten` replaces it) |
| `trader/state/risk.json` | trader-risk's verdicts; only a PASS from today is READY |
| `trader/state/broker.json` | every yes, no, placed, failed and filled, with each entry's max loss |
| `trader/portfolio.json` | cash and shares, updated by `paper`, `fill` and `result --filled-qty`; each leg's charges come out of the cash |
| `trader/plan.json` | the flat-by time for `flatten` |

## How a bracket becomes Indian orders

NSE has no single bracket order for an intraday (MIS) trade, so the ticket
shows the legs:

- **Entry**: a LIMIT buy. A "market" order goes to Kite as a limit 0.10 %
  through the price, on the tick grid (`limit_buffer_pct` in the config):
  Kite's API wants price protection on market orders, and the limit caps the
  slippage. If the price has run past it, it does not fill. That is correct:
  a late entry is a different trade.
- **Stop-loss**: an SL-M sell at the stop, placed as soon as the entry has
  filled. It sits at the exchange and works even if your computer is off.
- **Target**: an alert, not an order. A second sell order resting at the
  exchange could fill after the stop already sold your shares and leave you
  short. trader-alerts rings at the target and at flat-by; then `flatten`.

## Setup A: paper (the default, nothing to install)

`"paper": true` in `trader/config.json`. Zerodha has no paper-trading
account, so the paper trade lives in two files here: your yes is recorded,
`ticket.py paper` writes the fill at the latest price you give it (from
`/trader-alerts`: `alerts.py quote SYMBOL`), and the charges of each leg are
taken from the paper cash so the result is honest.

## Setup B: read your Zerodha account (hosted Kite MCP, no orders)

Zerodha runs an official MCP server at `https://mcp.kite.trade/mcp`
(github.com/zerodha/kite-mcp-server, read 11 Nov 2026 at commit 5e044dc). Add
it as a connector, or in Claude Desktop's config (also in
`claude_desktop_config.example.json` here):

```json
{"mcpServers": {"kite": {"command": "npx", "args": ["mcp-remote", "https://mcp.kite.trade/mcp"]}}}
```

You log in on Zerodha's own page (password and TOTP typed by you, never in
the chat). The hosted server can read: `get_profile`, `get_margins`,
`get_positions`, `get_holdings`, `get_orders`, `get_quotes`, `get_ltp`. Per
Zerodha's README it **leaves out the order tools** for safety. So it is right
for checking a position before a flatten, and it cannot place anything.

## Setup C: live orders (your own Kite MCP server)

Only when the user decides to go live, and sets `"paper": false` themselves.

1. A Kite Connect app at developers.kite.trade gives an API key and secret.
   They go into the server's `.env` or the Claude Desktop config's `env`
   block. **Keys never go in the chat.** Never ask for them, never read that
   file back, and if the user pastes a key, tell them to delete the message
   and regenerate the key.
2. Build and run Zerodha's server yourself (`go build -o kite-mcp-server`,
   `APP_MODE=stdio`); the README has the config block. It then offers
   `place_order`, `modify_order`, `cancel_order`.
3. **SEBI's static-IP rule** (from 1 Apr 2026): Zerodha rejects API orders
   that do not come from a static IP registered in your Kite developer
   profile. Home broadband usually changes its IP; you need a static IP from
   your ISP or a small server. Reading works from anywhere.
4. **Set the tool permissions**: `place_order`, `modify_order`,
   `cancel_order` and the GTT tools: **Needs approval**. Never Always allow.
   Read-only tools may be Always allow. In Claude Code:
   `"permissions": {"ask": ["mcp__kite__place_order", "mcp__kite__modify_order", "mcp__kite__cancel_order"]}`.
5. The Kite session ends every day: log in again each morning with the
   `login` tool, on Zerodha's page.

## Steps: the entry

1. `ticket.py show`. Only READY tickets go to the user. A ticket that is NOT
   READY or BLOCKED goes back to `/trader-risk`.
2. Show ONE ticket and ask: "Place this order? Reply yes or no." One order
   per question. Never offer "yes to all".
3. `ticket.py approve --index N --reply "<the user's reply, word for word>"`.
   If it prints "Not recorded", the reply was not an explicit yes for this
   order ("sure", "ok", "yes to all", a yes that names another stock or
   amount). Ask again. Never turn a reply into a yes yourself.
4. **Paper**: get a fresh price, then `ticket.py paper --index N --price P`.
   **Live**: call `place_order` with exactly the JSON the ticket printed
   (Allow once / Deny), then `ticket.py result --index N --status placed
   --broker-id ID --filled-qty Q --filled-price P`, or `--status denied` /
   `failed --note`. A failed order is not retried without a new check and a
   new yes.
5. **Live, bracket**: when `get_orders` shows the entry COMPLETE, place the
   stop-loss with exactly the second JSON. If the entry did not fill, do not
   place the stop: a sell with no shares opens a short.

## Steps: while it is open, and out by the flat-by

- `/trader-alerts`: `alerts.py add --from-plan` watches the stop, the target
  and the flat-by time.
- When the stop or the target is hit, record the sell:
  `ticket.py fill --symbol RELIANCE --side sell --qty 27 --price 1335.70`.
- By `flat_by` (15:10 India time), anything still open gets closed:
  1. Live: `get_positions` for the real quantity. `get_ltp` for the price.
  2. `ticket.py flatten --symbol RELIANCE --qty 27 --price LAST` writes the sell.
  3. `/trader-risk` (an exit is never blocked by the limits or the window).
  4. `ticket.py show`, then the user's yes for that one order.
  5. Live: **cancel the open stop-loss order first** (`get_orders`, then
     `cancel_order`, Needs approval), then `place_order`. If you sell first,
     the stop can still fire later and leave you short. Paper: `ticket.py paper`.
- Brokers square off MIS positions on their own from about 3:20 PM (Zerodha
  from 3:25 PM, with a charge per order). Be out before that.

## Example: the ticket

```
ORDER 1 of 1, PAPER account, Zerodha (NSE MIS)
  BUY 27 RELIANCE, market, good for today
  stop-loss 1335.70
  take-profit 1349.90
  max loss about ₹191.70 if the stop fills at 1335.70 (it can fill worse in a fast market)
  charges about ₹38.31 on top if the stop fills (Zerodha intraday, an estimate)
  READY: trader-risk PASS, waiting for your yes
```

The user replies "yes". Paper: `Paper fill: BUY 27 RELIANCE at 1343.10.
Nothing went to a broker.` When the target was hit that afternoon in the
test, the paper cash ended at ₹50,145.13: ₹183.60 on the price, ₹38.47 in
charges.

## What it never does

- Never places an order without all the gates, and never two orders on one yes.
- Never places orders from a scheduled or background task: nobody is there to say yes.
- Never asks for, reads, stores or repeats API keys, passwords or TOTP codes.
- Never switches `"paper"` to live. The user does that themselves.
- Never places a target sell next to a live stop, never sells before the
  stop order is cancelled, never trades futures or options.
- Never promises a fill price: a stop and a limit fill at what the market gives.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Paper trading by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order except trader-broker, and on a live
  account only when all three hold: trader-risk passed that exact order
  today, the user typed an explicit yes for that one order in the chat, and
  the user clicked Allow once on Claude's own card because the order tool is
  set to "Needs approval". Never set an order tool to "Always allow".
- No futures, options, margin or short selling unless the config allows it and the user confirms.
- Broker keys live in environment variables or the server's own config, never in the chat.
