#!/usr/bin/env python3
"""Big-money trade tracker for trader-bigbull (India). Standard library only.

Reads NSE's public bulk-deal and block-deal files: the trades big investors
and promoters must show by name, the evening of the day they trade.

    python3 deals.py index                              # today's bulk and block deals, biggest first
    python3 deals.py index --client kacholia            # deals by an investor (part of the name)
    python3 deals.py index --symbol CPPLUS --kind block # deals in a stock
    python3 deals.py index --min-cr 25                  # only deals worth 25 crore rupees or more
    python3 deals.py new --client kedia --client "mukul"  # only what is new since the last check
    python3 deals.py new --watch trader/bigbulls.txt    # the investors you follow, one name a line
    python3 deals.py summary                            # per stock: who bought, who sold, net crore
    python3 deals.py parse Bulk-Deals-01-10-2026-to-31-10-2026.csv --client kacholia

Where the data comes from:
  - Bulk deals: https://nsearchives.nseindia.com/content/equities/bulk.csv
    A bulk deal is one client buying or selling more than 0.5 % of a
    company's listed shares in a day. The broker must report it, and the
    exchange publishes the client's name, the quantity and the average price
    the same day.
  - Block deals: https://nsearchives.nseindia.com/content/equities/block.csv
    A block deal is one large trade done in the exchange's separate block
    window, at a price close to the market. Both sides are published.
  - The two files hold the latest trading day only. For older days download
    a date range from nseindia.com (Market Data > Large deals) and read it
    with `parse`.

What a bulk or block deal is, and is not:
  - It is a PUBLIC disclosure, out after the market has closed. The trade is
    done; the price you would pay tomorrow is a different price.
  - The client name is as the broker typed it: one investor can show up under
    a family member's name, a company or a fund, and spellings vary.
  - A buyer has a seller. A famous name buying says nothing about why the
    other side sold.
  - Reading them fast is not inside information. There is none here.

State: `new` remembers which deals it has shown in trader/state/bigbull.json,
so each deal alerts once. It flags deals in the stocks you hold or watch
(trader/portfolio.json, trader/watchlist.json, trader/plan.json). Offline:
--offline DIR reads bulk.csv and block.csv from DIR. The tests use it.
"""

import argparse
import csv
import datetime as _dt
import hashlib
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

FILES = {
    "bulk": ("bulk.csv", "https://nsearchives.nseindia.com/content/equities/bulk.csv"),
    "block": ("block.csv", "https://nsearchives.nseindia.com/content/equities/block.csv"),
}
UA = "day-trader-skill-india/2.0"
CRORE = 1e7
KEEP_DAYS = 120
MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
                                      "NOV", "DEC"), 1)}
NOTE = ("Public disclosures, out after the trade is done. The price has moved on, a buyer always has a seller, "
        "and this is not advice.")


class DealsError(Exception):
    pass


# ---------------------------------------------------------------- fetching

def ssl_context():
    """HTTPS certificate checks are always on. Python from python.org on macOS ships without CA
    certificates: use certifi if it is installed, else the system bundle."""
    paths = ssl.get_default_verify_paths()
    if paths.cafile or paths.capath:
        return ssl.create_default_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for p in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if os.path.exists(p):
            return ssl.create_default_context(cafile=p)
    return ssl.create_default_context()


def fetch(kind, offline=None, timeout=30):
    """The text of today's bulk or block file, from NSE or from a folder."""
    fname, url = FILES[kind]
    if offline:
        path = os.path.join(offline, fname) if os.path.isdir(offline) else offline
        if not os.path.isfile(path):
            raise DealsError("offline: no file %s" % path)
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise DealsError("nsearchives.nseindia.com answered HTTP %s for %s" % (exc.code, fname))
    except urllib.error.URLError as exc:
        raise DealsError("could not reach nsearchives.nseindia.com: %s" % exc.reason)
    except OSError as exc:
        raise DealsError("could not read %s: %s" % (fname, exc))


# ---------------------------------------------------------------- parsing

def parse_date(text):
    """'11-NOV-2026' or '11-Nov-2026' or '11/11/2026' -> date, or None."""
    t = (text or "").strip()
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$", t)
    if m and m.group(2).upper() in MONTHS:
        return _dt.date(int(m.group(3)), MONTHS[m.group(2).upper()], int(m.group(1)))
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", t)
    if m:
        return _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _num(text):
    try:
        return float(str(text).replace(",", "").strip())
    except ValueError:
        return None


def _col(hdr, *wants):
    """The index of the first header that contains every word of one of the wanted names."""
    for want in wants:
        words = want.split()
        for i, h in enumerate(hdr):
            if all(w in h for w in words):
                return i
    return None


def parse_deals(text, kind):
    """NSE's bulk or block CSV -> deals. Header: Date, Symbol, Security Name, Client Name,
    Buy/Sell, Quantity Traded, Trade Price / Wght. Avg. Price (, Remarks). The files NSE lets
    you download for a date range space the header differently: both are read."""
    rows = list(csv.reader(io.StringIO((text or "").replace("\r", "").lstrip("﻿"))))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    hdr = [" ".join(h.lower().replace("/", " ").split()) for h in rows[0]]
    idx = {"date": _col(hdr, "date"), "symbol": _col(hdr, "symbol"), "name": _col(hdr, "security name"),
           "client": _col(hdr, "client name"), "side": _col(hdr, "buy sell"),
           "qty": _col(hdr, "quantity"), "price": _col(hdr, "price"), "remarks": _col(hdr, "remarks")}
    need = [k for k in ("date", "symbol", "client", "side", "qty", "price") if idx[k] is None]
    if need:
        if len(rows) == 1 and "no records" in rows[0][0].lower():
            return []
        raise DealsError("not an NSE %s-deal file (no %s column; header %s)" % (kind, need[0], ",".join(rows[0])[:70]))
    out = []
    for r in rows[1:]:
        def cell(k):
            i = idx[k]
            return r[i].strip() if i is not None and i < len(r) else ""
        if "no records" in " ".join(r).lower():
            continue
        day, qty, price = parse_date(cell("date")), _num(cell("qty")), _num(cell("price"))
        side = cell("side").upper()
        if not day or qty is None or price is None or side not in ("BUY", "SELL") or not cell("symbol"):
            continue
        remark = cell("remarks")
        out.append({"kind": kind, "date": day.isoformat(), "symbol": cell("symbol").upper(),
                    "name": " ".join(cell("name").split()), "client": " ".join(cell("client").split()),
                    "side": side.lower(), "qty": int(qty) if qty == int(qty) else qty, "price": price,
                    "value": round(qty * price, 2), "remarks": "" if remark in ("-", "") else remark})
    return out


def deal_id(d):
    blob = "|".join(str(d[k]) for k in ("kind", "date", "symbol", "client", "side", "qty", "price"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def load_deals(kinds, offline=None, errors=None):
    """Every deal in today's files for the wanted kinds, biggest first."""
    out = []
    for i, kind in enumerate(kinds):
        if i and not offline:
            time.sleep(0.3)
        try:
            out += parse_deals(fetch(kind, offline), kind)
        except DealsError as exc:
            if errors is None:
                raise
            errors.append(str(exc))
    out = drop_repeats(out)
    out.sort(key=lambda d: (-d["value"], d["symbol"], d["client"]))
    return out


def drop_repeats(deals):
    """A block deal big enough to be a bulk deal is printed in both files. Keep the block
    row and drop its copy from the bulk rows (two equal rows in ONE file are two trades: kept)."""
    def key(d):
        return (d["date"], d["symbol"], d["client"], d["side"], d["qty"], d["price"])
    in_block = {}
    for d in deals:
        if d["kind"] == "block":
            in_block[key(d)] = in_block.get(key(d), 0) + 1
    out = []
    for d in deals:
        if d["kind"] == "bulk" and in_block.get(key(d), 0) > 0:
            in_block[key(d)] -= 1
            continue
        out.append(d)
    return out


# ---------------------------------------------------------------- filters

def norm(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def matches_client(deal, wanted):
    """wanted: names or parts of names. Every word of one wanted name must be in the client's name."""
    if not wanted:
        return True
    have = norm(deal["client"]).split()
    for w in wanted:
        words = norm(w).split()
        if words and all(any(h == x or h.startswith(x) for h in have) for x in words):
            return True
    return False


def select(deals, clients=None, symbols=None, min_cr=0.0, since=None):
    syms = {s.upper() for s in (symbols or [])}
    out = []
    for d in deals:
        if syms and d["symbol"] not in syms:
            continue
        if not matches_client(d, clients):
            continue
        if min_cr and d["value"] < min_cr * CRORE:
            continue
        if since and d["date"] < since:
            continue
        out.append(d)
    return out


def read_watch(path):
    """A file of investors to follow, one name (or part of a name) a line; # starts a comment."""
    if not path:
        return []
    if not os.path.isfile(path):
        raise DealsError("no watch file at %s (one investor name a line)" % path)
    with open(path, encoding="utf-8") as fh:
        return [ln.split("#")[0].strip() for ln in fh if ln.split("#")[0].strip()]


def your_symbols(portfolio="trader/portfolio.json", watchlist="trader/watchlist.json", plan="trader/plan.json",
                 extra=None):
    """{symbol: why}: what you hold, plan to trade or watch."""
    out = {}

    def load(p):
        if p and os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    return json.load(fh)
            except ValueError:
                return None
        return None
    for h in (load(watchlist) or {}).get("hits", []) if isinstance(load(watchlist), dict) else []:
        if h.get("symbol"):
            out[str(h["symbol"]).upper()] = "on your watchlist"
    pl = load(plan)
    if isinstance(pl, dict) and pl.get("symbol"):
        out[str(pl["symbol"]).upper()] = "in your plan"
    pf = load(portfolio)
    for p in (pf or {}).get("positions", []) if isinstance(pf, dict) else []:
        sym = p.get("ticker") or p.get("symbol")
        if sym:
            out[str(sym).upper()] = "you hold it"
    for s in extra or []:
        out.setdefault(s.upper(), "named by you")
    return out


# ---------------------------------------------------------------- words

def group(n):
    """Indian digit grouping: 842977 -> 8,42,977."""
    s = str(int(abs(n)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + s


def rupees(x):
    whole, frac = ("%.2f" % abs(x)).split(".")
    return ("-" if x < 0 else "") + "₹" + group(int(whole)) + "." + frac


def crore(value):
    c = value / CRORE
    return "₹%.2f crore" % c if abs(c) < 100 else "₹%s crore" % group(round(c))


def line(d, flags=None):
    flag = (flags or {}).get(d["symbol"])
    return "%s  %-5s %-11s %-4s %12s at %11s = %-17s %s%s%s" % (
        d["date"], d["kind"], d["symbol"], d["side"].upper(), group(d["qty"]), rupees(d["price"]),
        crore(d["value"]), d["client"], (" [%s]" % d["remarks"]) if d["remarks"] else "",
        ("  <- " + flag) if flag else "")


def alert(d, flags=None):
    flag = (flags or {}).get(d["symbol"])
    return ("NEW %s deal, %s: %s %s %s shares of %s (%s) at %s, %s%s"
            % (d["kind"], d["date"], d["client"], "bought" if d["side"] == "buy" else "sold", group(d["qty"]),
               d["symbol"], d["name"] or "name not given", rupees(d["price"]), crore(d["value"]),
               (". " + flag[:1].upper() + flag[1:]) if flag else ""))


def summarise(deals):
    """Per stock: bought and sold value, net, and the names on each side, biggest turnover first."""
    by = {}
    for d in deals:
        s = by.setdefault(d["symbol"], {"symbol": d["symbol"], "name": d["name"], "buy": 0.0, "sell": 0.0,
                                        "buyers": [], "sellers": [], "deals": 0})
        s[d["side"]] += d["value"]
        s["deals"] += 1
        side = s["buyers"] if d["side"] == "buy" else s["sellers"]
        if d["client"] not in side:
            side.append(d["client"])
    out = sorted(by.values(), key=lambda s: -(s["buy"] + s["sell"]))
    for s in out:
        s["net"] = round(s["buy"] - s["sell"], 2)
        s["buy"], s["sell"] = round(s["buy"], 2), round(s["sell"], 2)
    return out


# ---------------------------------------------------------------- commands

def _kinds(a):
    return ["bulk", "block"] if a.kind == "all" else [a.kind]


def _clients(a):
    return list(a.client or []) + read_watch(getattr(a, "watch", None))


def _print_list(deals, limit, flags=None):
    for d in deals[:limit]:
        print(line(d, flags))
    if len(deals) > limit:
        print("... and %d more (--limit N for more)." % (len(deals) - limit))


def cmd_index(a):
    errors = []
    deals = select(load_deals(_kinds(a), a.offline, errors), _clients(a), a.symbol, a.min_cr, a.since)
    if a.json:
        print(json.dumps({"deals": deals[:a.limit], "count": len(deals), "notes": errors}, indent=2))
        return 0 if deals else 1
    if deals:
        days = sorted({d["date"] for d in deals})
        print("%d deal%s, %s, biggest first:" % (len(deals), "" if len(deals) == 1 else "s",
                                                days[0] if len(days) == 1 else "%s to %s" % (days[0], days[-1])))
        _print_list(deals, a.limit, your_symbols(a.portfolio, a.watchlist, a.plan, a.tickers))
    else:
        print("No deals match.%s" % (" (NSE's files hold the latest trading day only, and are filled in the evening.)"
                                      if not a.offline else ""))
    for e in errors:
        print("note: " + e)
    print(NOTE)
    return 0 if deals else 1


def cmd_new(a):
    errors = []
    today = a.today or (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=5, minutes=30)).date().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        raise DealsError("--today wants a date like 2026-11-11")
    state = {}
    if os.path.isfile(a.state):
        try:
            with open(a.state, encoding="utf-8") as fh:
                state = json.load(fh)
        except ValueError as exc:
            raise DealsError("%s is not valid JSON: %s" % (a.state, exc))
    seen = state.setdefault("seen", {})
    deals = select(load_deals(_kinds(a), a.offline, errors), _clients(a), a.symbol, a.min_cr)
    fresh = [d for d in deals if deal_id(d) not in seen]
    flags = your_symbols(a.portfolio, a.watchlist, a.plan, a.tickers)
    if a.json:
        print(json.dumps({"new": [dict(d, yours=flags.get(d["symbol"])) for d in fresh], "notes": errors}, indent=2))
    else:
        for d in fresh[:a.limit]:
            print(alert(d, flags))
        if len(fresh) > a.limit:
            print("... and %d more new deals (--limit N for more)." % (len(fresh) - a.limit))
        if not fresh:
            print("Nothing new%s." % (" for the investors and stocks you named" if (_clients(a) or a.symbol) else ""))
        for e in errors:
            print("note: " + e)
        print(NOTE)
    if not a.dry_run:
        for d in deals:
            seen.setdefault(deal_id(d), d["date"])
        cutoff = (_dt.date.fromisoformat(today) - _dt.timedelta(days=KEEP_DAYS)).isoformat()
        state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
        state["last_check"] = today
        folder = os.path.dirname(a.state)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(a.state, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
    return 0 if fresh else 1


def cmd_summary(a):
    errors = []
    deals = select(load_deals(_kinds(a), a.offline, errors), _clients(a), a.symbol, a.min_cr)
    rows = summarise(deals)
    if a.json:
        print(json.dumps({"stocks": rows[:a.limit], "notes": errors}, indent=2))
        return 0 if rows else 1
    flags = your_symbols(a.portfolio, a.watchlist, a.plan, a.tickers)
    for s in rows[:a.limit]:
        net = "net bought %s" % crore(s["net"]) if s["net"] > 0 else "net sold %s" % crore(-s["net"]) \
            if s["net"] < 0 else "bought = sold"
        print("%-11s %s: bought %s, sold %s, %s (%d deal%s)%s" % (
            s["symbol"], s["name"], crore(s["buy"]), crore(s["sell"]), net, s["deals"],
            "" if s["deals"] == 1 else "s", ("  <- " + flags[s["symbol"]]) if s["symbol"] in flags else ""))
        if s["buyers"]:
            print("            buyers:  " + "; ".join(s["buyers"][:6]) + (" ..." if len(s["buyers"]) > 6 else ""))
        if s["sellers"]:
            print("            sellers: " + "; ".join(s["sellers"][:6]) + (" ..." if len(s["sellers"]) > 6 else ""))
    if not rows:
        print("No deals match.")
    for e in errors:
        print("note: " + e)
    print("A bulk-deal file shows only the clients above the 0.5 % line, so bought and sold need not match. " + NOTE)
    return 0 if rows else 1


def cmd_parse(a):
    if not os.path.isfile(a.csv_file):
        raise DealsError("no file at %s" % a.csv_file)
    with open(a.csv_file, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    kind = a.kind if a.kind != "all" else ("block" if "block" in os.path.basename(a.csv_file).lower() else "bulk")
    deals = parse_deals(text, kind)
    deals.sort(key=lambda d: (d["date"], -d["value"]), reverse=False)
    deals = select(deals, _clients(a), a.symbol, a.min_cr, a.since)
    if a.json:
        print(json.dumps({"deals": deals[:a.limit], "count": len(deals)}, indent=2))
        return 0 if deals else 1
    if deals:
        print("%d deal%s in %s:" % (len(deals), "" if len(deals) == 1 else "s", os.path.basename(a.csv_file)))
        _print_list(deals, a.limit, your_symbols(a.portfolio, a.watchlist, a.plan, a.tickers))
    else:
        print("No deals match in %s." % os.path.basename(a.csv_file))
    print(NOTE)
    return 0 if deals else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Big-money trade tracker (trader-bigbull): NSE bulk and block deals.")
    sub = ap.add_subparsers(dest="cmd")

    def common(p, net=True):
        p.add_argument("--client", action="append", metavar="NAME",
                       help="an investor's name or part of it (repeat for more)")
        p.add_argument("--watch", metavar="FILE", help="a file of investors to follow, one name a line")
        p.add_argument("--symbol", action="append", metavar="SYMBOL", help="only deals in this NSE symbol (repeat)")
        p.add_argument("--kind", choices=["all", "bulk", "block"], default="all")
        p.add_argument("--min-cr", type=float, default=0.0, metavar="CRORE", help="only deals worth this much")
        p.add_argument("--limit", type=int, default=50)
        p.add_argument("--tickers", nargs="*", help="flag deals in these symbols too")
        p.add_argument("--portfolio", default="trader/portfolio.json")
        p.add_argument("--watchlist", default="trader/watchlist.json")
        p.add_argument("--plan", default="trader/plan.json")
        p.add_argument("--json", action="store_true")
        if net:
            p.add_argument("--offline", metavar="DIR", help="a folder with bulk.csv and block.csv, no network")

    p = sub.add_parser("index", help="list the latest day's bulk and block deals")
    common(p)
    p.add_argument("--since", help="only deals on or after YYYY-MM-DD")
    p = sub.add_parser("new", help="deals not seen at the last check")
    common(p)
    p.add_argument("--state", default="trader/state/bigbull.json")
    p.add_argument("--today", help="YYYY-MM-DD, for reproducible runs")
    p.add_argument("--dry-run", action="store_true", help="do not update the state file")
    p = sub.add_parser("summary", help="per stock: who bought, who sold, net value")
    common(p)
    p = sub.add_parser("parse", help="read a bulk or block deal CSV you downloaded from NSE")
    p.add_argument("csv_file")
    common(p, net=False)
    p.add_argument("--since", help="only deals on or after YYYY-MM-DD")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"index": cmd_index, "new": cmd_new, "summary": cmd_summary, "parse": cmd_parse}[a.cmd](a)
    except DealsError as exc:
        print("deals.py: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
