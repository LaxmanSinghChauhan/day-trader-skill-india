#!/usr/bin/env python3
"""News monitor for trader-news (India). Standard library only.

Watches headlines and NSE corporate filings for the stocks you watch or hold
and prints only what is new since the last check, newest first, with how far
each stock has moved today and a flag on anything that touches your stocks.

    python3 news.py                                  # watchlist + plan + portfolio symbols
    python3 news.py --tickers RELIANCE INFY SBIN
    python3 news.py --tickers RELIANCE --all --hours 72  # everything in the last 3 days, seen or not
    python3 news.py --no-filings                     # headlines only
    python3 news.py --no-moves                       # skip the price line per stock

Your stocks, when --tickers is not given: every hit in trader/watchlist.json
(trader-scanner), the symbol in trader/plan.json (trader-exit) and the
positions in trader/portfolio.json.

Sources:
  - Headlines: Google News RSS, one search per stock on the company's name
    (India edition, the last few days):
    https://news.google.com/rss/search?q="<Company name>"+when:2d&hl=en-IN&gl=IN&ceid=IN:en
  - Filings: NSE's own RSS feed of corporate announcements, one request for
    every company (results, board-meeting outcomes, director changes, deals,
    orders, the exchange asking about a price move):
    https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml
  - Board meetings: NSE's RSS feed of board-meeting notices, one request.
    Results come out of board meetings, so a meeting today or tomorrow is the
    Indian "earnings date":
    https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml
  - Company names: trader/universe.txt (trader-scanner writes it), else NSE's
    equity list, fetched once and remembered:
    https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv
  - The move: Yahoo Finance's chart endpoint (unofficial, can lag), the last
    price against yesterday's close:
    https://query2.finance.yahoo.com/v8/finance/chart/<SYMBOL>.NS?range=1d&interval=5m

NSE's feeds hold about a day of filings: check at least once a day. Times
print in India time (IST). State: trader/state/news.json remembers what you
have seen (30 days), so an item shows once. Offline: --offline DIR reads
gnews-<SYMBOL>.xml, chart-<SYMBOL>.json, nse-announcements.xml,
nse-board-meetings.xml and EQUITY_L.csv from DIR. The tests use it.

Headlines are leads, not facts: open the story before acting, and treat
nothing here as advice.
"""

import argparse
import csv
import datetime as _dt
import email.utils
import gzip
import hashlib
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

GNEWS = "https://news.google.com/rss/search?q=%s&hl=en-IN&gl=IN&ceid=IN:en"
CHART = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=5m"
NSE_ANNOUNCEMENTS = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"
NSE_BOARD_MEETINGS = "https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml"
NSE_LIST = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
UA = "day-trader-skill-india/2.0"
KEEP_DAYS = 30
MOVE_PCT = 3.0  # a stock this far from yesterday's close is flagged as moving
IST = _dt.timedelta(hours=5, minutes=30)

# What an NSE filing is about, from its SUBJECT line. First match wins.
SUBJECTS = [
    ("results", r"financial result|outcome of board meeting|integrated filing"),
    ("board meeting", r"board meeting"),
    ("director or officer change", r"change in director|change in management|resignation|appointment|cessation|kmp"),
    ("auditor change", r"auditor"),
    ("deal", r"acquisition|amalgamation|merger|demerger|scheme of arrangement|open offer|takeover|"
             r"sale or disposal|joint venture"),
    ("order win", r"bagging|receiving of orders|award of order|contract"),
    ("fund raising", r"fund rais|alteration of capital|preferential|qualified institution|rights issue|"
                     r"allotment|debenture|commercial paper"),
    ("dividend or buyback", r"dividend|buy ?back|bonus|split|sub-?division|record date|corporate action"),
    ("exchange query", r"spurt in volume|price movement|clarification"),
    ("credit rating", r"credit rating"),
    ("insolvency or default", r"insolvency|cirp|default|liquidation|winding"),
    ("legal or regulatory", r"litigation|dispute|regulatory|penalt|order passed|sebi|show cause|search"),
    ("pledge", r"pledge|encumbrance"),
    ("investor meet", r"analyst|investor meet|con\. ?call|earnings call|presentation"),
    ("press release", r"press release|media release"),
    ("shareholder meeting", r"shareholders? meeting|agm|egm|postal ballot|voting"),
]
IMPORTANT = {"results", "board meeting", "director or officer change", "auditor change", "deal",
             "exchange query", "insolvency or default", "legal or regulatory", "pledge"}
KEYWORDS = [
    ("earnings", r"\bearnings\b|\bresults\b|\bQ[1-4]\b|\bnet profit\b|\bPAT\b|\bguidance\b|\bforecast\b"),
    ("analyst", r"\bupgrade[sd]?\b|\bdowngrade[sd]?\b|target price|price target|\boutperform\b|\bunderperform\b|"
                r"\bbrokerage[s]?\b"),
    ("legal", r"\blawsuit\b|\bsued\b|\bprobe\b|\binvestigation\b|\bSEBI order\b|\bED\b|\bCBI\b|\bcourt\b|\bNCLT\b"),
    ("deal", r"\bacqui(?:re|res|red|sition)\b|\bmerger\b|\bdemerger\b|\bbuyout\b|\btakeover\b|\bstake sale\b|"
             r"\bblock deal\b|\bbulk deal\b|\bdeal\b"),
    ("order", r"\bbags?\b|\border win\b|\bwins? order\b|\bcontract\b"),
    ("capital", r"\bdividend\b|\bbuyback\b|\bbonus\b|\bstock split\b|\bQIP\b|\brights issue\b|\bOFS\b|\bIPO\b"),
    ("people", r"\bCEO\b|\bCFO\b|\bMD\b|\bchairman\b|\bresign|\bsteps down\b|\bappoint"),
    ("risk", r"\brecall\b|\bbankrupt|\binsolvency\b|\bdefault\b|\bdelist|\bhack|\bbreach\b|\boutage\b|\bfraud\b"),
    ("halt", r"\bupper circuit\b|\blower circuit\b|\bcircuit\b|\btrading (?:halt|suspen)|\bsuspended\b"),
    ("regulatory", r"\bSEBI\b|\bRBI\b|\bUSFDA\b|\bFDA\b|\bCCI\b|\bapproval\b|\bapproves\b|\blicen[cs]e\b"),
    ("macro", r"\bRBI\b|\brepo rate\b|\bMPC\b|\bCPI\b|\binflation\b|\bGST\b|\bBudget\b|\bFII[s]?\b|\btariffs?\b|"
              r"\bNifty\b|\bSensex\b|\bcrude\b|\brupee\b"),
]


class NewsError(Exception):
    pass


# ---------------------------------------------------------------- time

def to_ist(utc):
    """Aware or naive UTC -> naive India wall-clock time."""
    if utc.tzinfo is not None:
        utc = utc.astimezone(_dt.timezone.utc)
    return utc.replace(tzinfo=None) + IST


# ---------------------------------------------------------------- inputs

def load_json(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def nse_symbol(sym):
    return re.sub(r"\.(NS|BO)$", "", str(sym).strip().upper())


def watch_from_files(portfolio="trader/portfolio.json", watchlist="trader/watchlist.json",
                     plan="trader/plan.json"):
    """{symbol: name or None}: the scanner's hits, the planned trade and your holdings."""
    out = {}
    wl = load_json(watchlist) or {}
    for h in wl.get("hits", []):
        sym = h.get("symbol") or h.get("ticker")
        if sym:
            out[nse_symbol(sym)] = h.get("name")
    pl = load_json(plan) or {}
    if pl.get("symbol"):
        out.setdefault(nse_symbol(pl["symbol"]), pl.get("name"))
    pf = load_json(portfolio) or {}
    for p in pf.get("positions", []):
        sym = p.get("ticker") or p.get("symbol")
        if sym:
            out[nse_symbol(sym)] = p.get("name") or out.get(nse_symbol(sym))
    return out


def names_from_universe(path="trader/universe.txt"):
    """trader-scanner's universe file, one SYMBOL|Name a line -> {symbol: name}."""
    out = {}
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                if "|" in ln:
                    sym, name = ln.rstrip("\n").split("|", 1)
                    out[sym.strip().upper()] = name.strip()
    return out


def short_name(name):
    """'Reliance Industries Limited' -> 'Reliance Industries': how headlines write it."""
    return re.sub(r"[\s,]+(limited|ltd\.?)\s*$", "", (name or "").strip(), flags=re.I)


def name_key(name):
    """A company name boiled down for matching: no Limited / Ltd / The, no punctuation."""
    n = html.unescape(name or "").lower()
    n = re.sub(r"\b(limited|ltd\.?|the)\b", " ", n)
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


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


class Fetcher(object):
    def __init__(self, offline=None, pause=0.3):
        self.offline = offline
        self.pause = pause
        self._last = 0.0

    def get(self, url, name):
        if self.offline:
            path = os.path.join(self.offline, name)
            if not os.path.isfile(path):
                raise NewsError("offline: no file %s" % path)
            with open(path, "rb") as fh:
                return fh.read()
        gap = time.time() - self._last
        if gap < self.pause:
            time.sleep(self.pause - gap)
        self._last = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl_context()) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as exc:
            raise NewsError("HTTP %s for %s" % (exc.code, url))
        except urllib.error.URLError as exc:
            raise NewsError("could not reach %s: %s" % (url, exc.reason))
        except OSError as exc:
            raise NewsError("could not read %s: %s" % (url, exc))


def yahoo_symbol(sym):
    return urllib.parse.quote(nse_symbol(sym) + ".NS", safe="")   # M&M -> M%26M.NS


def company_names(fetcher, state, watch, universe="trader/universe.txt"):
    """Fill in the company name of every watched symbol: what you gave, then
    trader/universe.txt, then NSE's equity list (remembered in the state)."""
    cached = state.setdefault("names", {})
    known = names_from_universe(universe)
    for sym in watch:
        if not watch[sym]:
            watch[sym] = known.get(sym) or cached.get(sym)
    missing = [s for s in watch if not watch[s]]
    if missing:
        text = fetcher.get(NSE_LIST, "EQUITY_L.csv").decode("utf-8", "replace")
        rows = csv.reader(io.StringIO(text.replace("\r", "")))
        for row in rows:
            if len(row) > 1 and row[0].strip().upper() in watch:
                cached[row[0].strip().upper()] = row[1].strip()
        for sym in missing:
            watch[sym] = cached.get(sym)
    for sym, name in watch.items():
        if name:
            cached[sym] = name
    return watch


# ---------------------------------------------------------------- parsing

def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _text(el, name):
    for c in el.iter():
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def parse_time(value):
    """RFC 822 (RSS) or ISO 8601 -> aware UTC datetime, or None."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        d = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        d = None
    if d is None:
        try:
            d = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.astimezone(_dt.timezone.utc)


def parse_nse_time(value):
    """NSE's feed time, India time: '11-Nov-2026 20:26:24' or '11-Nov-2026 20:26' -> aware UTC."""
    value = (value or "").strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            local = _dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
        return (local - IST).replace(tzinfo=_dt.timezone.utc)
    return None


def parse_rss(data, ticker):
    """Google News search RSS -> items."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise NewsError("RSS for %s is not valid XML: %s" % (ticker, exc))
    out = []
    for it in root.iter("item"):
        title = html.unescape(_text(it, "title"))
        link = _text(it, "link")
        guid = _text(it, "guid") or link
        publisher = _text(it, "source")
        summary = re.sub(r"<[^>]+>", " ", html.unescape(_text(it, "description")))
        out.append({"id": "rss:" + guid, "source": publisher or "Google News", "kind": "headline",
                    "ticker": ticker, "title": title, "summary": " ".join(summary.split()),
                    "link": link, "time": parse_time(_text(it, "pubDate"))})
    return out


def subject_label(subject):
    s = (subject or "").lower()
    for label, rx in SUBJECTS:
        if re.search(rx, s):
            return label
    return ""


def parse_nse_feed(data, by_name, kind="filing"):
    """NSE's announcements or board-meetings RSS -> items for the companies in
    by_name ({name_key: symbol}). The feed lists every company; the rest is skipped."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise NewsError("NSE's feed is not valid XML: %s" % exc)
    out = []
    for it in root.iter("item"):
        company = " ".join(html.unescape(_text(it, "title")).split())
        sym = by_name.get(name_key(company))
        if not sym:
            continue
        desc = html.unescape(_text(it, "description"))
        link = _text(it, "link")
        when = parse_nse_time(_text(it, "pubDate"))
        if kind == "board meeting":
            m = re.search(r"Meeting Date:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", desc)
            date = m.group(1) if m else ""
            title = "%s: board meeting%s" % (company, (" on " + date) if date else "")
            out.append({"id": "nse-bm:%s|%s" % (sym, date or link), "source": "NSE", "kind": "board meeting",
                        "ticker": sym, "title": title, "summary": desc, "subject": "board meeting",
                        "label": "board meeting", "meeting_date": date, "important": True,
                        "link": link, "time": when})
            continue
        m = re.search(r"\|\s*SUBJECT:\s*(.*)$", desc)
        subject = (m.group(1) if m else "").strip()
        label = subject_label(subject)
        title = "%s filed with NSE: %s" % (company, subject or "an announcement")
        out.append({"id": "nse:" + (link or "%s|%s|%s" % (sym, subject, _text(it, "pubDate"))), "source": "NSE",
                    "kind": "filing", "ticker": sym, "title": title, "summary": desc.split("|")[0].strip(),
                    "subject": subject, "label": label, "important": label in IMPORTANT,
                    "link": link, "time": when})
    return out


def parse_chart(data, ticker):
    """Yahoo chart JSON -> {"ticker", "price", "prev_close", "pct", "time"} or raise."""
    try:
        doc = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        meta = doc["chart"]["result"][0]["meta"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise NewsError("chart for %s is not usable" % ticker)
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if not price or not prev:
        raise NewsError("chart for %s has no price" % ticker)
    when = meta.get("regularMarketTime")
    return {"ticker": ticker, "price": round(float(price), 2), "prev_close": round(float(prev), 2),
            "pct": round((float(price) / float(prev) - 1) * 100, 2),
            "time": _dt.datetime.fromtimestamp(when, _dt.timezone.utc) if when else None}


def collect_moves(fetcher, watch, errors=None):
    errors = [] if errors is None else errors
    out = []
    for t in sorted(watch):
        name = "chart-%s.json" % t
        try:
            try:
                data = fetcher.get(CHART % ("query2", yahoo_symbol(t)), name)
            except NewsError as exc:
                if fetcher.offline or not re.search(r"HTTP (429|5\d\d)", str(exc)):
                    raise
                data = fetcher.get(CHART % ("query1", yahoo_symbol(t)), name)
            out.append(parse_chart(data, t))
        except NewsError as exc:
            if not (fetcher.offline and "no file" in str(exc)):
                errors.append("price for %s: %s" % (t, exc))
    return out


def mention_patterns(watch):
    pats = {}
    for t, name in watch.items():
        alts = [r"\(%s\)" % re.escape(t), r"\b(?:NSE|BSE)\s*:\s*%s\b" % re.escape(t)]
        short = short_name(name)
        if short and len(short) >= 4:
            alts.append(r"\b%s\b" % re.escape(short).replace(r"\ ", r"[\s-]"))
        pats[t] = re.compile("|".join(alts), re.I)
    return pats


def tag(items, watch):
    """Which of your stocks each item touches, and why it matters."""
    pats = mention_patterns(watch)
    for it in items:
        hay = "%s %s" % (it["title"], it.get("summary") or "")
        touches = {it["ticker"]} if it["ticker"] in watch else set()
        for t, rx in pats.items():
            if rx.search(hay):
                touches.add(t)
        it["touches"] = sorted(touches)
        it["tags"] = [label for label, rx in KEYWORDS if re.search(rx, hay, re.I)]
        if it["kind"] != "headline":
            if it.get("label") and it["label"] not in it["tags"]:
                it["tags"].insert(0, it["label"])
            if it.get("label") in ("results", "board meeting") and "earnings" not in it["tags"]:
                it["tags"].insert(0, "earnings")
    return items


def dedupe(items):
    """One item per story: same id, or same link, or same title the same day."""
    seen, out = {}, []
    for it in items:
        keys = [it["id"], it["link"],
                "%s|%s" % (re.sub(r"\W+", " ", it["title"].lower()).strip(),
                           it["time"].date() if it["time"] else "")]
        hit = next((seen[k] for k in keys if k and k in seen), None)
        if hit is not None:
            for t in it.get("touches", []):
                if t not in hit["touches"]:
                    hit["touches"].append(t)
            hit["touches"].sort()
            continue
        for k in keys:
            if k:
                seen[k] = it
        out.append(it)
    return out


def fingerprint(it):
    return hashlib.sha1(it["id"].encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- the check

def search_url(sym, name, hours):
    days = max(1, min(7, int((hours + 23.999) // 24)))
    what = '"%s"' % short_name(name) if name else '"%s" share NSE' % sym
    return GNEWS % urllib.parse.quote_plus("%s when:%dd" % (what, days))


def collect(fetcher, watch, state, filings=True, hours=48, errors=None):
    errors = [] if errors is None else errors
    items = []
    try:
        company_names(fetcher, state, watch)
    except NewsError as exc:
        errors.append("company names: %s" % exc)
    for t in sorted(watch):
        try:
            items += parse_rss(fetcher.get(search_url(t, watch[t], hours), "gnews-%s.xml" % t), t)
        except NewsError as exc:
            if not (fetcher.offline and "no file" in str(exc)):
                errors.append("headlines for %s: %s" % (t, exc))
    if filings:
        by_name = {name_key(n): s for s, n in watch.items() if n}
        nameless = sorted(s for s, n in watch.items() if not n)
        if nameless:
            errors.append("no company name for %s: NSE filings cannot be matched to it" % ", ".join(nameless))
        if by_name:
            for url, fname, kind in ((NSE_ANNOUNCEMENTS, "nse-announcements.xml", "filing"),
                                     (NSE_BOARD_MEETINGS, "nse-board-meetings.xml", "board meeting")):
                try:
                    items += parse_nse_feed(fetcher.get(url, fname), by_name, kind)
                except NewsError as exc:
                    if not (fetcher.offline and "no file" in str(exc)):
                        errors.append("NSE %ss: %s" % (kind, exc))
    return items


def select(items, state, now, hours=48, show_all=False):
    """Items within the window; only unseen ones unless show_all."""
    seen = state.setdefault("seen", {})
    cutoff = now - _dt.timedelta(hours=hours)
    ahead = now + _dt.timedelta(minutes=10)  # a pinned --now: nothing from after it
    out = []
    for it in items:
        if it["time"] is not None and (it["time"] < cutoff or it["time"] > ahead):
            continue
        fp = fingerprint(it)
        it["new"] = fp not in seen
        if it["new"] or show_all:
            out.append(it)
    out.sort(key=lambda i: (i["time"] or now), reverse=True)
    return out


def remember(items, state, now):
    seen = state.setdefault("seen", {})
    stamp = now.isoformat()
    for it in items:
        seen.setdefault(fingerprint(it), stamp)
    cutoff = (now - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
    state["last_check"] = stamp


def _grouped(x):
    """Indian digit grouping with two decimals: 1234567.5 -> 12,34,567.50."""
    whole, frac = ("%.2f" % abs(x)).split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return ("-" if x < 0 else "") + whole + "." + frac


def render_moves(moves, move_pct=MOVE_PCT):
    out = []
    for m in moves:
        flag = "MOVING" if abs(m["pct"]) >= move_pct else ""
        when = (" at %s IST" % to_ist(m["time"]).strftime("%H:%M")) if m.get("time") else ""
        out.append("%-11s %s %+.2f%% vs yesterday's close %s%s  %s" % (
            m["ticker"], _grouped(m["price"]), m["pct"], _grouped(m["prev_close"]), when, flag))
    return out


def render(items, errors, now, moves=None, move_pct=MOVE_PCT):
    out = render_moves(moves or [], move_pct)
    if out:
        out.append("")
    if not items:
        out.append("Nothing new.")
    for it in items:
        when = to_ist(it["time"]).strftime("%Y-%m-%d %H:%M IST") if it["time"] else "time unknown"
        mark = "!" if it.get("important") else " "
        who = ",".join(it["touches"]) or it["ticker"]
        out.append("%s %s  %-11s %-13s %s" % (mark, when, who, it["source"][:13], it["title"]))
        extra = []
        if it["tags"]:
            extra.append("tags: " + ", ".join(it["tags"]))
        extra.append(it["link"])
        out.append("      " + "  ".join(extra))
    for e in errors:
        out.append("note: %s" % e)
    out.append("Checked %s. Headlines are leads, not facts; open the story before acting. "
               "Not financial advice." % to_ist(now).strftime("%Y-%m-%d %H:%M IST"))
    return "\n".join(out) + "\n"


def _json_ready(items):
    out = []
    for it in items:
        d = dict(it)
        d["time"] = it["time"].isoformat() if it["time"] else None
        out.append(d)
    return out


def parse_now(text):
    """--now: an ISO time. Without an offset it is India time."""
    try:
        d = _dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        raise NewsError('--now wants a time like "2026-11-11 10:00" (India time) or ...Z (UTC)')
    if d.tzinfo is None:
        return (d - IST).replace(tzinfo=_dt.timezone.utc)
    return d.astimezone(_dt.timezone.utc)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tickers", nargs="*", help="NSE symbols; default: watchlist + plan + portfolio")
    ap.add_argument("--portfolio", default="trader/portfolio.json")
    ap.add_argument("--watchlist", default="trader/watchlist.json")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--state", default="trader/state/news.json")
    ap.add_argument("--hours", type=float, default=48, help="ignore items older than this")
    ap.add_argument("--all", action="store_true", help="show seen items too")
    ap.add_argument("--no-filings", action="store_true", help="headlines only, no NSE feeds")
    ap.add_argument("--no-moves", action="store_true", help="skip the price line per stock")
    ap.add_argument("--move-pct", type=float, default=MOVE_PCT, help="flag a move this big (percent)")
    ap.add_argument("--max", type=int, default=40, help="most symbols to check when --tickers is not given")
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--now", help="ISO time (no offset = India time), for reproducible runs")
    ap.add_argument("--dry-run", action="store_true", help="do not update the state file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    errors = []
    if args.tickers:
        watch = {nse_symbol(t): None for t in args.tickers}
        known = watch_from_files(args.portfolio, args.watchlist, args.plan)
        watch.update({t: known[t] for t in watch if known.get(t)})
    else:
        watch = watch_from_files(args.portfolio, args.watchlist, args.plan)
        if len(watch) > args.max:
            keep = list(watch)[:args.max]
            errors.append("%d symbols in your files: checked the first %d (one search each). Name the ones you "
                          "want with --tickers, or raise --max" % (len(watch), args.max))
            watch = {t: watch[t] for t in keep}
    if not watch:
        print("news: no symbols. Pass --tickers, or run /trader-scanner first (it writes "
              "trader/watchlist.json).", file=sys.stderr)
        return 2
    try:
        now = parse_now(args.now) if args.now else _dt.datetime.now(_dt.timezone.utc)
    except NewsError as exc:
        print("news: %s" % exc, file=sys.stderr)
        return 2
    state = load_json(args.state) or {}
    fetcher = Fetcher(offline=args.offline)
    items = collect(fetcher, watch, state, filings=not args.no_filings, hours=args.hours, errors=errors)
    items = dedupe(tag(items, watch))
    shown = select(items, state, now, hours=args.hours, show_all=args.all)
    moves = [] if args.no_moves else collect_moves(fetcher, watch, errors)
    if args.json:
        mv = [dict(m, time=m["time"].isoformat() if m.get("time") else None,
                   moving=abs(m["pct"]) >= args.move_pct) for m in moves]
        print(json.dumps({"checked": now.isoformat(), "moves": mv, "items": _json_ready(shown),
                          "notes": errors}, indent=2))
    else:
        sys.stdout.write(render(shown, errors, now, moves, args.move_pct))
    if not args.dry_run:
        remember(items, state, now)
        folder = os.path.dirname(args.state)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(args.state, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
    return 0 if any(i["new"] for i in shown) else 1


if __name__ == "__main__":
    sys.exit(main())
