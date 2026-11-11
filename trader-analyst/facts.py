#!/usr/bin/env python3
"""Earnings reader for trader-analyst (India). Standard library only.

Pulls an NSE company's reported numbers and lays out what changed, quarter by
quarter: revenue, gross, operating and net margins, net profit, diluted EPS,
and growth against the same quarter a year earlier. It also finds the
company's latest results filing and its next board meeting on NSE (results
come out of board meetings).

    python3 facts.py RELIANCE
    python3 facts.py RELIANCE INFY --quarters 8
    python3 facts.py RELIANCE --json
    python3 facts.py RELIANCE HDFCBANK ICICIBANK INFY ITC --metrics trader/metrics.json

Sources:
  https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/<SYMBOL>.NS
        quarterly and annual revenue, cost of revenue, gross profit, operating
        income, net income and diluted EPS, in rupees. Free and unofficial:
        Yahoo takes them from the company's filed (usually consolidated)
        results through a data vendor.
  https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml   today's filings
  https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml         board-meeting notices
  https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv          symbol -> company name

India has no free official numbers API like the SEC's: NSE publishes each
result as an XBRL file but not as one feed of numbers. So the table is Yahoo's
copy, and the filing itself (the NSE link) is the source to check before you
rely on a number.

How the quarters are built:
  - A quarter is a value Yahoo marks as a three-month period. Yahoo keeps
    about five quarters and sometimes skips one: a gap is shown as a gap,
    never filled in, and a quarter whose year-ago quarter is missing has no
    growth figure.
  - "Last 4 quarters" is shown only when the four latest quarters are
    consecutive. Otherwise the tool shows the last full fiscal year instead
    (April to March for most Indian companies).
  - Banks and insurers report revenue differently; margins for them can be blank.

--metrics FILE merges one row per symbol into a JSON file (for notes or a
sheet). Offline: --offline DIR reads fundamentals-<SYMBOL>.json,
nse-announcements.xml, nse-board-meetings.xml and EQUITY_L.csv from DIR.

Numbers only: this tool never says whether a stock is a buy.
"""

import argparse
import csv
import datetime as _dt
import gzip
import html
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

FUND_URL = ("https://%s.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/%s"
            "?type=%s&period1=%d&period2=%d")
NSE_ANNOUNCEMENTS = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"
NSE_BOARD_MEETINGS = "https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml"
NSE_LIST = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
UA = "day-trader-skill-india/2.0"
CRORE = 1e7
IST = _dt.timedelta(hours=5, minutes=30)

# our name -> Yahoo's field (after "quarterly" / "annual"), first one with data wins
FIELDS = {
    "revenue": ["TotalRevenue", "OperatingRevenue"],
    "cost_of_revenue": ["CostOfRevenue"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncome"],
    "net_income": ["NetIncome", "NetIncomeCommonStockholders"],
    "eps_diluted": ["DilutedEPS", "BasicEPS"],
}
RESULTS_RX = re.compile(r"financial result|outcome of board meeting|integrated filing", re.I)


class FactsError(Exception):
    pass


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


class Fetcher(object):
    def __init__(self, offline=None, pause=0.3):
        self.offline, self.pause, self._last = offline, pause, 0.0

    def raw(self, url, name):
        if self.offline:
            path = os.path.join(self.offline, name)
            if not os.path.isfile(path):
                raise FactsError("offline: no file %s" % path)
            with open(path, "rb") as fh:
                return fh.read()
        gap = time.time() - self._last
        if gap < self.pause:
            time.sleep(self.pause - gap)
        self._last = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=ssl_context()) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as exc:
            raise FactsError("HTTP %s for %s" % (exc.code, url.split("?")[0]))
        except urllib.error.URLError as exc:
            raise FactsError("could not reach %s: %s" % (url.split("?")[0], exc.reason))
        except OSError as exc:
            raise FactsError("could not read %s: %s" % (url.split("?")[0], exc))

    def json(self, url, name):
        try:
            return json.loads(self.raw(url, name).decode("utf-8"))
        except ValueError:
            raise FactsError("%s did not answer with JSON" % url.split("?")[0])


def nse_symbol(sym):
    return re.sub(r"\.(NS|BO)$", "", str(sym).strip().upper())


def fundamentals_url(sym, now=None, host="query2"):
    now = now or _dt.datetime.now(_dt.timezone.utc)
    types = []
    for names in FIELDS.values():
        for n in names:
            types += ["quarterly" + n, "annual" + n]
    end = int(now.timestamp()) + 86400
    start = end - 6 * 366 * 86400
    return FUND_URL % (host, urllib.parse.quote(nse_symbol(sym) + ".NS", safe=""), ",".join(types), start, end)


def fetch_fundamentals(fetcher, sym, now=None):
    name = "fundamentals-%s.json" % sym
    try:
        return fetcher.json(fundamentals_url(sym, now), name)
    except FactsError as exc:
        if fetcher.offline or not re.search(r"HTTP (429|5\d\d)", str(exc)):
            raise
        return fetcher.json(fundamentals_url(sym, now, "query1"), name)


# ---------------------------------------------------------------- facts

def _date(s):
    return _dt.date.fromisoformat(s)


def raw_series(doc):
    """Yahoo's timeseries answer -> {"quarterlyTotalRevenue": {"2026-09-30": value}, ...} and the currency."""
    try:
        results = doc["timeseries"]["result"]
    except (KeyError, TypeError):
        raise FactsError("Yahoo's answer is not the shape this tool knows")
    out, currency = {}, None
    for r in results or []:
        types = (r.get("meta") or {}).get("type") or []
        if not types:
            continue
        t = types[0]
        vals = {}
        for row in r.get(t) or []:
            if not row or not row.get("asOfDate"):
                continue
            rv = (row.get("reportedValue") or {}).get("raw")
            if rv is None:
                continue
            vals[row["asOfDate"]] = float(rv)
            currency = currency or row.get("currencyCode")
        if vals:
            out[t] = vals
    return out, currency


def series(raw, key, prefix="quarterly"):
    """One metric's {period end: value}, from the first Yahoo field that has data, and that field's name."""
    for name in FIELDS[key]:
        vals = raw.get(prefix + name)
        if vals:
            return dict(vals), prefix + name
    return {}, None


def _yoy_match(series_, end, days=365, slack=10):
    target = _date(end) - _dt.timedelta(days=days)
    best = None
    for e in series_:
        gap = abs((_date(e) - target).days)
        if gap <= slack and (best is None or gap < best[0]):
            best = (gap, e)
    return series_[best[1]] if best else None


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round(100.0 * (a - b) / abs(b), 1)


def margin(part, whole):
    if part is None or not whole:
        return None
    return round(100.0 * part / whole, 1)


def fiscal_label(end):
    """An Indian fiscal quarter for a period end: 2026-09-30 -> 'Q2 FY27' (the year runs April to March)."""
    d = _date(end)
    q = {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3, 1: 4, 2: 4, 3: 4}[d.month]
    fy = d.year + 1 if d.month >= 4 else d.year
    return "Q%d FY%02d" % (q, fy % 100)


def consecutive(ends):
    """Are these period ends (oldest first) back-to-back quarters?"""
    return all(75 <= (_date(b) - _date(a)).days <= 100 for a, b in zip(ends, ends[1:]))


def analyse(doc, quarters=6, name=None, symbol=None):
    """Every number in the report, as a dict."""
    raw, currency = raw_series(doc)
    s, fields = {}, {}
    for key in FIELDS:
        s[key], fields[key] = series(raw, key)
    rev = s["revenue"]
    if not rev and not s["net_income"]:
        raise FactsError("no quarterly revenue or net profit in Yahoo's data (is it an NSE company with results?)")
    ends = sorted(set(rev) | set(s["net_income"]), reverse=True)[:quarters]
    rows = []
    for i, end in enumerate(ends):
        r = rev.get(end)
        gp = s["gross_profit"].get(end)
        if gp is None and r is not None and end in s["cost_of_revenue"]:
            gp = r - s["cost_of_revenue"][end]
        oi = s["operating_income"].get(end)
        ni = s["net_income"].get(end)
        eps = s["eps_diluted"].get(end)
        prior = {k: _yoy_match(s[k], end) for k in ("revenue", "net_income", "eps_diluted")}
        older = ends[i + 1] if i + 1 < len(ends) else None
        rows.append({
            "end": end, "fiscal": fiscal_label(end),
            "gap_before": bool(older and not consecutive([older, end])),
            "revenue": r, "gross_profit": gp, "operating_income": oi, "net_income": ni,
            "eps_diluted": round(eps, 2) if eps is not None else None,
            "gross_margin": margin(gp, r), "operating_margin": margin(oi, r),
            "net_margin": margin(ni, r),
            "revenue_yoy": pct(r, prior["revenue"]),
            "net_income_yoy": pct(ni, prior["net_income"]),
            "eps_yoy": pct(eps, prior["eps_diluted"]),
        })
    ttm = {}
    for key in ("revenue", "net_income", "eps_diluted"):
        last4 = sorted(s[key])[-4:]
        if len(last4) == 4 and consecutive(last4):
            ttm[key] = sum(s[key][e] for e in last4)
    if "eps_diluted" in ttm:
        ttm["eps_diluted"] = round(ttm["eps_diluted"], 2)
    annual = {}
    a_rev, _ = series(raw, "revenue", "annual")
    a_ni, _ = series(raw, "net_income", "annual")
    a_eps, _ = series(raw, "eps_diluted", "annual")
    a_ends = sorted(set(a_rev) | set(a_ni))
    if a_ends:
        e = a_ends[-1]
        prev = a_ends[-2] if len(a_ends) > 1 else None
        annual = {"end": e, "revenue": a_rev.get(e), "net_income": a_ni.get(e),
                  "eps_diluted": round(a_eps[e], 2) if e in a_eps else None,
                  "revenue_yoy": pct(a_rev.get(e), a_rev.get(prev)) if prev else None,
                  "net_income_yoy": pct(a_ni.get(e), a_ni.get(prev)) if prev else None}
    return {"entity": name or symbol, "symbol": symbol, "currency": currency or "INR",
            "rows": rows, "ttm": ttm, "annual": annual, "fields": fields}


def unit(currency):
    """(sign, word, divisor) for the report: rupees are shown in crore, any other currency
    in millions. A few Indian companies (Infosys, Wipro, Dr. Reddy's) file in US dollars too,
    and Yahoo carries those figures."""
    cur = (currency or "INR").upper()
    if cur == "INR":
        return "₹", "crore", CRORE
    return cur + " ", "million", 1e6


def crore(v, currency="INR"):
    """A money value in the report's unit: rupees -> crore with Indian digit grouping
    (3306010000000 -> 3,30,601); another currency -> millions (5140000000 -> 5,140)."""
    if v is None:
        return "-"
    _, _, div = unit(currency)
    n = int(round(abs(v) / div))
    s = str(n)
    if (currency or "INR").upper() != "INR":
        s = "{:,}".format(n)
    elif len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if v < 0 else "") + s


def stale_note(result, today=None):
    """A note when Yahoo's quarters stop long before today: newer results are out."""
    rows = result.get("rows") or []
    if not rows:
        return None
    today = today or (_dt.datetime.now(_dt.timezone.utc) + IST).date()
    latest = rows[0]["end"]
    if (today - _date(latest)).days > 150:
        return ("Yahoo's quarters for %s stop at %s (%s). Newer results have been filed since: read them on NSE "
                "before you use these numbers." % (result.get("symbol") or result.get("entity"), latest,
                                                   rows[0]["fiscal"]))
    return None


def changes(result):
    """Plain sentences: what changed in the latest quarter."""
    rows = result["rows"]
    if not rows:
        return []
    cur = rows[0]
    prev = rows[1] if len(rows) > 1 and not cur["gap_before"] else None
    out = []
    sign, word, _ = unit(result.get("currency"))

    def money(v):
        return "n/a" if v is None else "%s%s %s" % (sign, crore(v, result.get("currency")), word)

    line = "Quarter ending %s (%s): revenue %s" % (cur["end"], cur["fiscal"], money(cur["revenue"]))
    if cur["revenue_yoy"] is not None:
        line += " (%+.1f%% vs a year earlier)" % cur["revenue_yoy"]
    line += ", net profit %s" % money(cur["net_income"])
    if cur["net_income_yoy"] is not None:
        line += " (%+.1f%%)" % cur["net_income_yoy"]
    if cur["eps_diluted"] is not None:
        line += ", diluted EPS %s%.2f" % (sign, cur["eps_diluted"])
        if cur["eps_yoy"] is not None:
            line += " (%+.1f%%)" % cur["eps_yoy"]
    out.append(line + ".")
    if cur["revenue_yoy"] is None and cur["net_income_yoy"] is None:
        out.append("No growth figures: Yahoo's data has no quarter a year before %s to compare with." % cur["end"])
    for key, name in (("gross_margin", "Gross margin"), ("operating_margin", "Operating margin"),
                      ("net_margin", "Net margin")):
        if cur[key] is None:
            continue
        s = "%s %.1f%%" % (name, cur[key])
        if prev and prev[key] is not None:
            s += " (%+.1f points vs the quarter before)" % (cur[key] - prev[key])
        out.append(s + ".")
    if cur["net_income"] is not None and cur["operating_income"] is not None \
            and cur["net_income"] > cur["operating_income"]:
        out.append("Net profit is above operating income: it includes gains outside the "
                   "business (other income, tax items). Check the filing before reading it as growth.")
    if prev and cur["revenue"] is not None and prev["revenue"]:
        out.append("Revenue %+.1f%% vs the quarter before (many businesses are seasonal: "
                   "compare with a year earlier first)." % pct(cur["revenue"], prev["revenue"]))
    return out


# ---------------------------------------------------------------- filings (NSE's RSS feeds)

def name_key(name):
    """A company name boiled down for matching: no Limited / Ltd / The, no punctuation."""
    n = html.unescape(name or "").lower()
    n = re.sub(r"\b(limited|ltd\.?|the)\b", " ", n)
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def company_names(fetcher, symbols, universe="trader/universe.txt"):
    """{symbol: company name}: trader/universe.txt first, then NSE's equity list."""
    out = {}
    if universe and os.path.isfile(universe):
        with open(universe, encoding="utf-8") as fh:
            for ln in fh:
                if "|" in ln:
                    sym, name = ln.rstrip("\n").split("|", 1)
                    if sym.strip().upper() in symbols:
                        out[sym.strip().upper()] = name.strip()
    if any(s not in out for s in symbols):
        text = fetcher.raw(NSE_LIST, "EQUITY_L.csv").decode("utf-8", "replace")
        for row in csv.reader(io.StringIO(text.replace("\r", ""))):
            if len(row) > 1 and row[0].strip().upper() in symbols:
                out.setdefault(row[0].strip().upper(), row[1].strip())
    return out


def _items(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise FactsError("NSE's feed is not valid XML: %s" % exc)
    for it in root.iter("item"):
        yield {c.tag.rsplit("}", 1)[-1]: (c.text or "").strip() for c in it}


def latest_filings(fetcher, name):
    """Today's results filing and the next board meeting of one company, from NSE's feeds.
    {"results": {...} or None, "board_meeting": {...} or None}. The feeds hold about a day."""
    out = {"results": None, "board_meeting": None}
    key = name_key(name)
    if not key:
        return out
    try:
        for it in _items(fetcher.raw(NSE_ANNOUNCEMENTS, "nse-announcements.xml")):
            if name_key(" ".join((it.get("title") or "").split())) != key:
                continue
            desc = html.unescape(it.get("description") or "")
            m = re.search(r"\|\s*SUBJECT:\s*(.*)$", desc)
            subject = (m.group(1) if m else "").strip()
            if RESULTS_RX.search(subject) and out["results"] is None:
                out["results"] = {"subject": subject, "filed": it.get("pubDate"), "url": it.get("link")}
    except FactsError as exc:
        if not (fetcher.offline and "no file" in str(exc)):
            out["note"] = str(exc)
    try:
        for it in _items(fetcher.raw(NSE_BOARD_MEETINGS, "nse-board-meetings.xml")):
            if name_key(" ".join((it.get("title") or "").split())) != key:
                continue
            desc = html.unescape(it.get("description") or "")
            m = re.search(r"Meeting Date:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", desc)
            if out["board_meeting"] is None:
                out["board_meeting"] = {"date": m.group(1) if m else None, "filed": it.get("pubDate"),
                                        "url": it.get("link")}
    except FactsError as exc:
        if not (fetcher.offline and "no file" in str(exc)):
            out["note"] = str(exc)
    return out


# ---------------------------------------------------------------- output

def _p(v):
    return "-" if v is None else "%+.1f%%" % v if v < 0 or v > 0 else "0.0%"


def _pm(v):
    return "-" if v is None else "%.1f%%" % v


def render(symbol, result, filings, today=None):
    cur = result.get("currency")
    sign, word, _ = unit(cur)

    def big(v):
        return ("%s%s %s" % (sign, crore(v, cur), word)) if v is not None else "-"

    out = ["%s (%s). %s%s except EPS. Source: Yahoo Finance fundamentals (unofficial copy of the "
           "filed results)." % (result["entity"], symbol, sign, word), ""]
    if (cur or "INR").upper() != "INR":
        out.insert(1, "Yahoo carries this company's figures in %s, not rupees (it also files abroad)." % cur.upper())
    out.append("%-11s %-8s %11s %8s %7s %7s %7s %10s %8s %7s" % (
        "quarter end", "fiscal", "revenue", "rev yoy", "gross", "oper", "net",
        "net profit", "EPS dil", "EPS yoy"))
    for r in result["rows"]:
        out.append("%-11s %-8s %11s %8s %7s %7s %7s %10s %8s %7s%s" % (
            r["end"], r["fiscal"], crore(r["revenue"], cur), _p(r["revenue_yoy"]),
            _pm(r["gross_margin"]), _pm(r["operating_margin"]), _pm(r["net_margin"]),
            crore(r["net_income"], cur), "-" if r["eps_diluted"] is None else "%.2f" % r["eps_diluted"],
            _p(r["eps_yoy"]), "  (a quarter is missing before this one)" if r["gap_before"] else ""))
    t, a = result["ttm"], result.get("annual") or {}
    out.append("")
    if t:
        out.append("Last 4 quarters: revenue %s, net profit %s, diluted EPS %s." % (
            big(t.get("revenue")), big(t.get("net_income")),
            ("%s%.2f" % (sign, t["eps_diluted"])) if t.get("eps_diluted") is not None else "-"))
    elif a:
        out.append("Last full year (to %s): revenue %s%s, net profit %s%s, diluted EPS %s." % (
            a["end"], big(a.get("revenue")),
            (" (%+.1f%%)" % a["revenue_yoy"]) if a.get("revenue_yoy") is not None else "",
            big(a.get("net_income")),
            (" (%+.1f%%)" % a["net_income_yoy"]) if a.get("net_income_yoy") is not None else "",
            ("%s%.2f" % (sign, a["eps_diluted"])) if a.get("eps_diluted") is not None else "-"))
        out.append("(The last four quarters are not all in Yahoo's data, so no trailing-twelve-month sum.)")
    note = stale_note(result, today)
    if note:
        out.append("")
        out.append("NOTE: " + note)
    out.append("")
    out.append("What changed:")
    for line in changes(result):
        out.append("  - " + line)
    if filings:
        res, bm = filings.get("results"), filings.get("board_meeting")
        if res or bm:
            out.append("")
        if res:
            out.append("Results filing on NSE (%s), %s  %s" % (res["subject"], res["filed"], res["url"]))
        if bm:
            out.append("Board meeting%s (results usually come out of one): notice of %s  %s" % (
                (" on " + bm["date"]) if bm.get("date") else "", bm["filed"], bm["url"]))
    out.append("")
    out.append("Check a number against the company's own filing before you rely on it: "
               "https://www.nseindia.com/companies-listing/corporate-filings-financial-results")
    return "\n".join(out) + "\n"


def metrics_row(symbol, result):
    rows = result["rows"]
    cur = rows[0] if rows else {}
    t = result["ttm"]
    return {"ticker": symbol, "name": result["entity"], "period_end": cur.get("end"),
            "fiscal": cur.get("fiscal"), "revenue_ttm": t.get("revenue"),
            "net_income_ttm": t.get("net_income"), "eps_ttm": t.get("eps_diluted"),
            "revenue_growth_yoy": cur.get("revenue_yoy"), "eps_growth_yoy": cur.get("eps_yoy"),
            "net_income_growth_yoy": cur.get("net_income_yoy"),
            "gross_margin": cur.get("gross_margin"), "operating_margin": cur.get("operating_margin"),
            "net_margin": cur.get("net_margin"), "currency": result.get("currency"),
            "source": "Yahoo Finance fundamentals"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tickers", nargs="*", help="NSE symbols, e.g. RELIANCE INFY")
    ap.add_argument("--quarters", type=int, default=6)
    ap.add_argument("--no-filings", action="store_true", help="skip NSE's filing and board-meeting feeds")
    ap.add_argument("--metrics", metavar="FILE", help="merge a row per symbol into this JSON")
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.tickers:
        ap.print_help()
        return 2
    fetcher = Fetcher(offline=args.offline)
    symbols = [nse_symbol(t) for t in args.tickers]
    try:
        names = company_names(fetcher, set(symbols))
    except FactsError as exc:
        names = {}
        print("facts: company names: %s" % exc, file=sys.stderr)
    results, rows, failed = [], [], 0
    for sym in symbols:
        try:
            doc = fetch_fundamentals(fetcher, sym)
            result = analyse(doc, quarters=args.quarters, name=names.get(sym), symbol=sym)
            filings = None
            if not args.no_filings and names.get(sym):
                filings = latest_filings(fetcher, names[sym])
        except FactsError as exc:
            print("facts: %s: %s" % (sym, exc), file=sys.stderr)
            failed += 1
            continue
        results.append({"ticker": sym, "result": result, "filings": filings, "changes": changes(result),
                        "note": stale_note(result)})
        rows.append(metrics_row(sym, result))
        if not args.json:
            sys.stdout.write(render(sym, result, filings))
            sys.stdout.write("\n")
    if args.json:
        print(json.dumps(results, indent=2))
    if args.metrics and rows:
        existing = {}
        if os.path.isfile(args.metrics):
            with open(args.metrics, encoding="utf-8") as fh:
                existing = {r["ticker"]: r for r in json.load(fh).get("companies", [])}
        for r in rows:
            existing[r["ticker"]] = r
        folder = os.path.dirname(args.metrics)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(args.metrics, "w", encoding="utf-8") as fh:
            json.dump({"as_of": (_dt.datetime.now(_dt.timezone.utc) + IST).date().isoformat(),
                       "companies": sorted(existing.values(), key=lambda r: r["ticker"])},
                      fh, indent=2)
            fh.write("\n")
        if not args.json:
            print("wrote %s (%d companies)" % (args.metrics, len(existing)))
    return 0 if results and not failed else (1 if results else 2)


if __name__ == "__main__":
    sys.exit(main())
