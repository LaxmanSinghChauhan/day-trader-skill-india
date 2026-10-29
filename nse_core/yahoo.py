"""Free fallback candles from Yahoo Finance's chart endpoint (NSE symbols end in .NS, BSE in .BO).

Unofficial: no key, can lag, change or rate-limit, and Indian intraday volumes there are not always
complete. Fine for learning and rough replays; use Kite's historical API (Connect app) for anything you
act on. Yahoo keeps 5-minute bars for about 60 days and 1-minute bars for about 7.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime

from .clock import IST
from .net import urlopen

URL = "https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={rng}"


def chart(symbol: str, interval: str = "5m", rng: str = "60d", exchange: str = "NSE") -> list[list]:
    sym = symbol + (".NS" if exchange == "NSE" else ".BO")
    req = urllib.request.Request(URL.format(sym=sym, interval=interval, rng=rng),
                                 headers={"User-Agent": "Mozilla/5.0 (nse-intraday-skills)"})
    for attempt in range(2):
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(5)
                continue
            raise
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo has no chart for {sym}")
    q = result["indicators"]["quote"][0]
    rows = []
    for i, ts in enumerate(result.get("timestamp", [])):
        o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c):
            continue
        t = datetime.fromtimestamp(ts, IST)
        if t.minute % 5 and interval == "5m":
            continue    # the live, still-forming bar
        rows.append([t.isoformat(), round(o, 2), round(h, 2), round(l, 2), round(c, 2), v or 0])
    return rows
