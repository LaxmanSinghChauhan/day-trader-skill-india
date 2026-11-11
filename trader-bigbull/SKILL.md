---
name: trader-bigbull
description: >-
  The Big Bull Tracker: the Pelosi Tracker's Indian twin. Watches the trades
  big investors, funds and promoters must show by name: reads NSE's public
  bulk-deal and block-deal files the evening they are published, alerts once
  per new deal, and turns each into a clean row (who, stock, buy or sell, how
  many shares, at what price, how many crore). Follows the investors you name,
  sums up each stock (who bought, who sold, net crore) and flags deals in
  stocks you hold or watch. India has no law that makes politicians report
  each trade, so this is the closest public record of who is trading. Use
  when the user says "who is buying", "kisne khareeda", "bulk deals today",
  "block deals", "what did Kacholia buy", "track big investors", "promoter
  selling", "FII ne kya liya", "alert me when X trades", or "run the big bull
  skill".
argument-hint: "[investor name] [--symbol SYMBOL]"
---

# trader-bigbull

In the US pack this skill is the Pelosi Tracker: members of Congress must
report each stock trade within 45 days, and the skill reads those reports.
India has no such rule. MPs declare their assets, not their trades. What
India does have is stricter and faster for the market itself: when one client
buys or sells more than 0.5 % of a company's shares in a day (a **bulk
deal**), or trades a large block in the exchange's block window (a **block
deal**), the exchange publishes the client's name, the quantity and the
price the same evening. That is where well-known investors, mutual funds and
promoters show up by name.

It is fast. It is not early. By the time anyone can read it the trade is
done and the price has moved on. There is no inside information here: only
public files, read quickly. Say that every time.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/deals.py" index                           # today's deals, biggest first
python3 "${CLAUDE_SKILL_DIR}/deals.py" index --client kacholia         # an investor (part of the name)
python3 "${CLAUDE_SKILL_DIR}/deals.py" index --symbol CPPLUS --kind block
python3 "${CLAUDE_SKILL_DIR}/deals.py" index --min-cr 25               # only deals of 25 crore rupees or more
python3 "${CLAUDE_SKILL_DIR}/deals.py" new --watch trader/bigbulls.txt # only what is new since the last check
python3 "${CLAUDE_SKILL_DIR}/deals.py" summary                         # per stock: buyers, sellers, net
python3 "${CLAUDE_SKILL_DIR}/deals.py" parse downloaded.csv --client kedia
```

`--client` takes a name or part of one and repeats. `new` exits 1 when
nothing is new. `--json` on every command.

## What it reads and writes

- Reads `https://nsearchives.nseindia.com/content/equities/bulk.csv` and
  `.../block.csv`: the latest trading day's deals, filled in after the close.
- Writes `trader/state/bigbull.json` (the deals already shown, so each alerts
  once; 120 days).
- Reads `trader/portfolio.json`, `trader/watchlist.json` and
  `trader/plan.json` (if they exist) to flag deals in what you hold or watch.
- Reads a watch file you keep, one investor name a line
  (`bigbulls.example.txt` here shows the shape).

## The rules

- **Quote the exchange file, not a tracker.** Every row comes from NSE's own
  file. Websites that follow "ace investors" are fine for browsing but can be
  late or wrong. The file wins.
- **The name is as the broker typed it.** One investor can trade through a
  family member, a company, an LLP or a fund, and spellings vary. A match on
  "kacholia" finds one spelling of one account. Say "a client named ...",
  not "he bought".
- **A buyer has a seller.** A famous name buying says nothing about why the
  other side sold. `summary` shows both sides.
- **A bulk file is one-sided.** It lists only clients above the 0.5 % line,
  so "bought" and "sold" for a stock need not match.
- **A block that is big enough is printed in both files.** The tool counts it once.
- **Say the size in crore** and the price, never "a big stake".

## Step 1: what was traded today

`deals.py index` after about 6 PM on a trading day. Biggest first. Narrow it
with `--client`, `--symbol`, `--kind`, `--min-cr`.

## Step 2: watch for new ones

```bash
python3 "${CLAUDE_SKILL_DIR}/deals.py" new --watch trader/bigbulls.txt --tickers RELIANCE
```

Shows only deals not seen at the last check and records them. Once every
evening is enough: a scheduled task at 7 PM, or `/loop` on trading days. The
files hold one day, so a day you do not run it is a day you miss.

## Step 3: an older day

NSE's files are today's only. For older deals download a date range from
nseindia.com (Market Data, Large deals), then `deals.py parse FILE.csv`.

**Insider trades and pledges** (the closer cousin of a politician's report):
company insiders must disclose trades above ₹10 lakh in a quarter under
SEBI's insider-trading rules, and promoters must disclose pledges and big
stake changes. Those sit on each company's NSE page under Corporate Filings
(Insider Trading, SAST, Pledge). NSE's public feed of them was not being
updated when this was written (11 Nov 2026), so the tool does not read it:
open the page for the stock. `/trader-news` shows the day's filings.

## Example: real alerts, Wednesday 11 November 2026

```
NEW block deal, 2026-11-11: MOTILAL OSWAL MUTUAL FUND bought 8,42,977 shares of CPPLUS (Aditya Infotech Limited) at ₹4,140.00, ₹349 crore
CPPLUS      Aditya Infotech Limited: bought ₹582 crore, sold ₹582 crore, bought = sold (4 deals)
            buyers:  MOTILAL OSWAL MUTUAL FUND; KOTAK MAHINDRA MUTUAL FUND
            sellers: DIXON TECHNOLOGIES (INDIA) LIMITED
```

Then: "This was published after the market closed. Two mutual funds bought
what Dixon sold, at ₹4,140. It says what changed hands today, not what the
price will do tomorrow."

## What it never does

- Never calls a deal a signal, and never says "follow" anyone.
- Never guesses who is behind a client name.
- Never uses anything but the exchange's public files.

## Safety

- Education and tooling, not financial advice. A disclosure is history, not a tip.
- Nothing here places an order. Orders go only through trader-broker, after
  trader-risk passes them and you say yes; paper trading is the default.
