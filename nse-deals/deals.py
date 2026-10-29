#!/usr/bin/env python3
"""Who bought and sold in size: NSE/BSE bulk and block deal files, summarised per stock.

  deals.py summary bulk.csv [block.csv …] [--watchlist] [--json]
The files are the CSV downloads from NSE (Market Data → Bulk/Block Deals) or BSE. Columns are found by
name, so both exchanges' layouts work. Public data, published after the trades: context, not a signal.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import state  # noqa: E402

WANT = {
    "symbol": ("symbol", "scrip code", "security code"),
    "name": ("security name", "scrip name", "company"),
    "client": ("client name", "client"),
    "side": ("buy/sell", "buy / sell", "deal type", "transaction type"),
    "qty": ("quantity traded", "quantity", "qty"),
    "price": ("trade price", "wght. avg. price", "price"),
    "date": ("date", "deal date"),
}


def columns(header: list[str]) -> dict:
    found = {}
    low = [h.strip().lower() for h in header]
    for key, names in WANT.items():
        for i, h in enumerate(low):
            if any(n in h for n in names) and key not in found:
                found[key] = i
    missing = {"symbol", "client", "side", "qty", "price"} - set(found)
    if missing:
        raise ValueError(f"can't find columns {sorted(missing)} in {header}")
    return found


def num(text: str) -> float:
    return float(str(text).replace(",", "").strip() or 0)


def read(path: Path, kind: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    col = columns(rows[0])
    out = []
    for r in rows[1:]:
        if len(r) < len(rows[0]) or not r[col["symbol"]].strip():
            continue
        side = r[col["side"]].strip().upper()
        out.append({"kind": kind, "date": r[col["date"]].strip() if "date" in col else "",
                    "symbol": r[col["symbol"]].strip().upper(), "client": r[col["client"]].strip(),
                    "side": "BUY" if side.startswith("B") or side == "P" else "SELL",
                    "qty": num(r[col["qty"]]), "price": num(r[col["price"]])})
    return out


def summarise(deals: list[dict]) -> dict:
    by = {}
    for d in deals:
        s = by.setdefault(d["symbol"], {"buy_qty": 0.0, "sell_qty": 0.0, "buy_value": 0.0, "sell_value": 0.0, "clients": {}})
        k = "buy" if d["side"] == "BUY" else "sell"
        s[f"{k}_qty"] += d["qty"]
        s[f"{k}_value"] += d["qty"] * d["price"]
        c = s["clients"].setdefault(d["client"], {"buy": 0.0, "sell": 0.0, "kind": d["kind"]})
        c[k] += d["qty"]
    for s in by.values():
        s["net_qty"] = s["buy_qty"] - s["sell_qty"]
        s["net_value_cr"] = round((s["buy_value"] - s["sell_value"]) / 1e7, 2)
        s["buy_avg"] = round(s["buy_value"] / s["buy_qty"], 2) if s["buy_qty"] else None
        s["sell_avg"] = round(s["sell_value"] / s["sell_qty"], 2) if s["sell_qty"] else None
        s["same_client_both_sides"] = sorted(n for n, c in s["clients"].items() if c["buy"] and c["sell"])
    return by


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["summary"])
    p.add_argument("files", nargs="+")
    p.add_argument("--watchlist", action="store_true", help="only stocks on today's watchlist")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    deals = []
    for f in a.files:
        kind = "block" if "block" in Path(f).name.lower() else "bulk"
        try:
            deals += read(Path(f), kind)
        except (ValueError, OSError) as e:
            print(f"{f}: {e}")
            return 1
    by = summarise(deals)
    if a.watchlist:
        wl = {h["symbol"] for h in (state.read_json("watchlist.json") or {}).get("hits", [])}
        by = {k: v for k, v in by.items() if k in wl}
    if a.json:
        print(json.dumps(by, indent=2))
        return 0
    print(f"{len(deals)} deals in {len(a.files)} file(s), {len(by)} stocks")
    for sym, s in sorted(by.items(), key=lambda kv: -abs(kv[1]["net_value_cr"])):
        print(f"  {sym:<12} net ₹{s['net_value_cr']:+,.2f} cr · bought {s['buy_qty']:,.0f} @ {s['buy_avg']} · sold {s['sell_qty']:,.0f} @ {s['sell_avg']}")
        if s["same_client_both_sides"]:
            print(f"     same client on both sides: {', '.join(s['same_client_both_sides'][:3])} (often a day trader or a churn, not a view)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
