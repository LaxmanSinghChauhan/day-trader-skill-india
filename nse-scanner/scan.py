#!/usr/bin/env python3
"""Stocks-in-Play scanner for NSE: universe, candle fetch, and the 09:20 opening-range scan.

  scan.py universe [--file ind_nifty500list.csv]        # Nifty 500, EQ series → intraday/universe.json
  scan.py fetch --source kite|yahoo [--symbols A,B] [--days 25]   # 5-minute bars → intraday/candles/
  scan.py sip [--now "2026-10-29 09:21"] [--json]       # stocks in play today → intraday/watchlist.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time as systime
import urllib.request
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import candles as cd  # noqa: E402
from nse_core import clock, sip, state  # noqa: E402
from nse_core.net import urlopen  # noqa: E402

NIFTY500_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"


def cmd_universe(a) -> int:
    if a.file:
        text = Path(a.file).read_text()
        source = a.file
    else:
        req = urllib.request.Request(NIFTY500_URL, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(req, timeout=20) as resp:
                text = resp.read().decode("utf-8-sig")
        except Exception as e:
            print(f"Couldn't download the Nifty 500 list ({e}). Download it from niftyindices.com and pass --file.")
            return 1
        source = NIFTY500_URL
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    members = [{"symbol": r["Symbol"].strip(), "name": r["Company Name"].strip(), "industry": r.get("Industry", "").strip()}
               for r in rows if r.get("Series", "EQ").strip() == "EQ" and r.get("Symbol")]
    if len(members) < 100:
        print(f"Only {len(members)} rows look like Nifty 500 members: is this the right file?")
        return 1
    state.write_json("universe.json", {"index": "NIFTY 500", "source": source,
                                       "as_of": clock.now_ist().isoformat(timespec="minutes"), "members": members})
    print(f"Universe: {len(members)} Nifty 500 stocks (EQ series) → {state.path('universe.json')}")
    return 0


def _symbols(a) -> list[str]:
    if a.symbols:
        return [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    uni = state.read_json("universe.json")
    if not uni:
        raise SystemExit("No universe yet: run `scan.py universe` or pass --symbols")
    return [m["symbol"] for m in uni["members"]]


def cmd_fetch(a) -> int:
    symbols = _symbols(a)
    out_dir = state.path("candles")
    ok, failed = 0, []
    if a.source == "kite":
        from nse_core.kite import Kite, KiteError
        try:
            kite = Kite()
            dump = list(csv.DictReader(io.StringIO(kite.instruments("NSE"))))
        except KiteError as e:
            print(e)
            return 1
        by_symbol = {r["tradingsymbol"]: r for r in dump if r["segment"] == "NSE" and r["instrument_type"] == "EQ"}
        end = clock.now_ist()
        start = end - timedelta(days=min(a.days * 7 // 5 + 3, 99))
        for s in symbols:
            inst = by_symbol.get(s)
            if not inst:
                failed.append(s)
                continue
            try:
                rows = kite.historical(int(inst["instrument_token"]), "5minute",
                                       start.strftime("%Y-%m-%d 09:00:00"), end.strftime("%Y-%m-%d %H:%M:%S"))
                cd.save(out_dir / f"{s}.json", s, "5minute", "kite", rows, float(inst["tick_size"]))
                ok += 1
            except KiteError as e:
                failed.append(f"{s} ({e})")
            systime.sleep(0.35)     # historical API: 3 requests a second
    else:
        from nse_core import yahoo
        for s in symbols:
            try:
                rows = yahoo.chart(s, "5m", "60d")
                cd.save(out_dir / f"{s}.json", s, "5minute", "yahoo", rows)
                ok += 1
            except Exception as e:
                failed.append(f"{s} ({e})")
            systime.sleep(0.3)
    print(f"Fetched 5-minute bars for {ok} of {len(symbols)} symbols from {a.source} → {out_dir}/")
    if failed:
        print(f"Failed {len(failed)}: {', '.join(failed[:10])}{' …' if len(failed) > 10 else ''}")
    return 0 if ok else 1


def cmd_sip(a) -> int:
    cfg = state.load_config()
    now = clock.parse_now(a.now)
    extra = cfg["extra_holidays"]
    if not clock.is_trading_day(now.date(), extra):
        print(f"{now:%a %d %b %Y} is not a trading day ({clock.holiday_name(now.date(), extra) or 'weekend'}).")
        return 1
    window = max(cfg["orb_minutes"], cfg["rvol_minutes"])
    ready = (datetime.combine(now.date(), time(9, 15)) + timedelta(minutes=window)).time()
    if now.time() < ready:
        print(f"Too early: the opening range and its volume window complete at {ready:%H:%M} IST.")
        return 1
    files = sorted(state.path("candles").glob("*.json"))
    if not files:
        print("No candles yet: run `scan.py fetch` first (or put files in intraday/candles/).")
        return 1
    blocked = {s.upper() for s in cfg["blocked"]}
    results = []
    for f in files:
        if f.stem.upper() in blocked:
            continue
        data = cd.load(f)
        results.append(sip.measure(data["symbol"], cd.sessions(data["bars"]), now.date(), cfg,
                                   data.get("tick_size"), data.get("source")))
    measured = [r for r in results if "rvol" in r]
    skipped = [r for r in results if "rvol" not in r]
    tradable, in_play = sip.rank(measured, cfg)
    top = in_play[:cfg["top_n"]]
    out = {"as_of": now.isoformat(timespec="minutes"), "rule": f"5-min ORB, RVOL ≥ {cfg['rvol_min']}×, top {cfg['top_n']}",
           "scanned": len(results), "usable": len(measured), "in_play": len(in_play),
           "hits": tradable, "doji_or_off": [r["symbol"] for r in top if "trigger" not in r],
           "skipped": {r["symbol"]: r["skip"] for r in skipped}}
    if not a.no_write:
        state.write_json("watchlist.json", out)
    if a.json:
        print(json.dumps(out, indent=2))
        return 0 if tradable else 1
    print(f"{now:%d %b %H:%M} IST · scanned {out['scanned']}, usable {out['usable']}, "
          f"in play (RVOL ≥ {cfg['rvol_min']}×) {out['in_play']}, listed {len(tradable)}")
    for r in tradable:
        arrow = "above" if r["side"] == "LONG" else "below"
        print(f"  {r['symbol']:<12} {r['side']:<5} RVOL {r['rvol']:>5.1f}×  range ₹{r['range_low']:,.2f}–₹{r['range_high']:,.2f}"
              f"  trigger {arrow} ₹{r['trigger']:,.2f}  ATR ₹{r['atr']:.2f}")
    if out["doji_or_off"]:
        print(f"  in play but no trade (doji or shorts off): {', '.join(out['doji_or_off'])}")
    if skipped:
        print(f"  {len(skipped)} skipped for missing data or the price floor (reasons in watchlist.json)")
        empty = [r for r in skipped if r["skip"].startswith("no volume in the opening")]
        if empty:
            print(f"  {len(empty)} had no volume in the 09:15 bar: Yahoo leaves it empty for NSE. Use --source kite,"
                  f" or set \"rvol_minutes\": 10 in intraday/config.json and scan after 09:25.")
    return 0 if tradable else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("universe")
    u.add_argument("--file")
    f = sub.add_parser("fetch")
    f.add_argument("--source", choices=["kite", "yahoo"], default="kite")
    f.add_argument("--symbols")
    f.add_argument("--days", type=int, default=25)
    s = sub.add_parser("sip")
    s.add_argument("--now")
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-write", action="store_true")
    a = p.parse_args(argv)
    return {"universe": cmd_universe, "fetch": cmd_fetch, "sip": cmd_sip}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
