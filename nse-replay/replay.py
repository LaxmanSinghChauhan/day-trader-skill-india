#!/usr/bin/env python3
"""Replay the Stocks-in-Play ORB rule over past sessions, after Zerodha charges, and say how sure we can be.

  replay.py [--symbols A,B] [--from 2026-08-01] [--to 2026-10-28] [--seed 7] [--boot 5000] [--json] [--no-write]
Reads intraday/candles/*.json, writes intraday/replay.json.

Each day it does what you would have done: rank that day's stocks by opening relative volume, take the
top N with a direction, enter at the trigger (or the open if it gapped past, never beyond the IOC cap),
plus slippage, stop by the same rule as nse-exit, exit at the stop or 15:10. When one 5-minute bar holds
both the entry and the stop, it assumes the stop hit (the worst case). Then it resamples whole trading
days (a day-block bootstrap: trades on the same day move together) for a range on the expectancy.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import candles as cd  # noqa: E402
from nse_core import charges as ch  # noqa: E402
from nse_core import clock, sip, state  # noqa: E402
from nse_core import plan as pl  # noqa: E402
from nse_core.ticks import to_tick  # noqa: E402

SLIPPAGE_TICKS = 1


def simulate(hit: dict, bars: list, cfg: dict) -> dict | None:
    side, trig, tick = hit["side"], hit["trigger"], hit["tick"]
    long = side == "LONG"
    window = max(cfg["orb_minutes"], cfg["rvol_minutes"])          # nothing is known before both windows close
    or_end = (datetime.combine(date.today(), time(9, 15)) + timedelta(minutes=window)).time()
    until, hard = clock.hhmm(cfg["entries_until"]), clock.hhmm(cfg["hard_exit"])
    cap = float(to_tick(trig * (1 + cfg["entry_cap_pct"]), tick, "down")) if long else float(to_tick(trig * (1 - cfg["entry_cap_pct"]), tick, "up"))
    later = [b for b in bars if b.t.time() >= or_end]
    for i, b in enumerate(later):
        if b.t.time() >= until:
            return None
        if (long and b.h >= trig) or (not long and b.l <= trig):
            base = (max(trig, b.o) if long else min(trig, b.o))
            fill = base + SLIPPAGE_TICKS * tick if long else base - SLIPPAGE_TICKS * tick
            if (long and fill > cap) or (not long and fill < cap):
                if (long and base > cap) or (not long and base < cap):
                    return {"skip": "gapped past the IOC cap"}
                fill = cap
            fill = round(fill, 2)
            stop, _ = pl.base_stop(side, fill, hit["atr"], tick, cfg)
            stop, qty, widened = pl.fit_stop_to_charges(side, fill, stop, tick, cfg, None, cfg["exchange"])
            if qty <= 0:
                return {"skip": "no quantity fits"}
            exit_px, reason, exit_t = None, None, None
            best = worst = fill
            for j, x in enumerate(later[i:]):
                if j > 0 and x.t.time() >= hard:
                    exit_px, reason, exit_t = x.o, "time", x.t
                    break
                hit_stop = x.l <= stop if long else x.h >= stop
                if hit_stop:
                    gap_px = min(stop, x.o) if long else max(stop, x.o)
                    px = (gap_px if j > 0 else stop)
                    exit_px = px - SLIPPAGE_TICKS * tick if long else px + SLIPPAGE_TICKS * tick
                    reason, exit_t = "stop", x.t
                    worst = min(worst, x.l) if long else max(worst, x.h)
                    break
                best = max(best, x.h) if long else min(best, x.l)
                worst = min(worst, x.l) if long else max(worst, x.h)
            if exit_px is None:
                exit_px, reason, exit_t = later[-1].c, "end of data", later[-1].t
            exit_px = round(exit_px, 2)
            rt = ch.round_trip(side, fill, exit_px, qty, cfg["exchange"])
            risk = abs(fill - stop)
            return {"symbol": hit["symbol"], "date": hit["date"], "side": side, "rvol": hit["rvol"],
                    "entry_at": b.t.strftime("%H:%M"), "entry": fill, "stop": stop, "widened": widened, "qty": qty,
                    "exit": exit_px, "exit_at": exit_t.strftime("%H:%M"), "reason": reason, "gross": rt.gross,
                    "charges": rt.total, "net": rt.net, "r": round(rt.net / (risk * qty), 3),
                    "mfe_r": round(abs(best - fill) / risk, 2), "mae_r": round(abs(fill - worst) / risk, 2)}
    return None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(centre - half, 3), round(centre + half, 3)


def stats(trades: list[dict], boot: int, seed: int) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    wins = sum(1 for t in trades if t["net"] > 0)
    net = [t["net"] for t in trades]
    rs = [t["r"] for t in trades]
    gains, losses = sum(x for x in net if x > 0), -sum(x for x in net if x < 0)
    peak = cum = dd = 0.0
    for x in net:
        cum += x
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    by_day: dict[str, list[float]] = {}
    for t in trades:
        by_day.setdefault(t["date"], []).append(t["r"])
    days = list(by_day.values())
    rng = random.Random(seed)
    means = []
    for _ in range(boot):
        sample = [days[rng.randrange(len(days))] for _ in days]
        k = sum(len(d) for d in sample)
        means.append(sum(sum(d) for d in sample) / k)
    means.sort()
    lo, hi = means[int(0.025 * boot)], means[int(0.975 * boot) - 1]
    split = {}
    for side in ("LONG", "SHORT"):
        s = [t["r"] for t in trades if t["side"] == side]
        split[side] = {"trades": len(s), "expectancy_r": round(sum(s) / len(s), 3) if s else None}
    return {"trades": n, "days": len(days), "wins": wins, "win_rate": round(wins / n, 3), "win_rate_95": wilson(wins, n),
            "net_total": round(sum(net), 2), "charges_total": round(sum(t["charges"] for t in trades), 2),
            "gross_total": round(sum(t["gross"] for t in trades), 2), "avg_net": round(sum(net) / n, 2),
            "expectancy_r": round(sum(rs) / n, 3), "expectancy_r_95": [round(lo, 3), round(hi, 3)],
            "p_expectancy_above_0": round(sum(1 for m in means if m > 0) / boot, 3),
            "profit_factor": round(gains / losses, 2) if losses else None, "max_drawdown": round(dd, 2),
            "by_side": split, "exits": {r: sum(1 for t in trades if t["reason"] == r) for r in ("stop", "time", "end of data")}}


def verdict(s: dict) -> str:
    if s["trades"] == 0:
        return "No trades: the rule never fired on this data."
    lo, hi = s["expectancy_r_95"]
    base = f"{s['trades']} trades over {s['days']} days: expectancy after charges {s['expectancy_r']:+.3f}R (95% range {lo:+.3f}R to {hi:+.3f}R)."
    if lo > 0:
        return base + " Positive on this sample. Still a replay, not a promise: confirm with weeks of paper trading."
    if hi < 0:
        return base + " Negative after charges on this sample. Don't trade it as is."
    return base + f" Can't tell it apart from zero yet: {s['trades']} trades is not enough. Keep recording and paper trading."


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols")
    p.add_argument("--from", dest="start")
    p.add_argument("--to", dest="end")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--boot", type=int, default=5000)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-write", action="store_true")
    a = p.parse_args(argv)
    cfg = state.load_config()
    files = sorted(state.path("candles").glob("*.json"))
    want = {s.strip().upper() for s in a.symbols.split(",")} if a.symbols else None
    data = {}
    for f in files:
        d = cd.load(f)
        if want is None or d["symbol"] in want:
            data[d["symbol"]] = (cd.sessions(d["bars"]), d.get("tick_size"))
    if not data:
        print("No candles: run /nse-scanner fetch first.")
        return 1
    days = sorted({d for by_day, _ in data.values() for d in by_day})
    days = [d for d in days if (not a.start or d.isoformat() >= a.start) and (not a.end or d.isoformat() <= a.end)]
    trades, skips = [], {}
    for d in days:
        measured = [sip.measure(sym, by_day, d, cfg, tick) for sym, (by_day, tick) in data.items() if d in by_day]
        tradable, _ = sip.rank(measured, cfg)
        for hit in tradable:
            res = simulate(hit, data[hit["symbol"]][0][d], cfg)
            if res is None:
                skips["no trigger before the cut-off"] = skips.get("no trigger before the cut-off", 0) + 1
            elif "skip" in res:
                skips[res["skip"]] = skips.get(res["skip"], 0) + 1
            else:
                trades.append(res)
    s = stats(trades, a.boot, a.seed)
    out = {"rule": f"SIP-ORB: {cfg['orb_minutes']}-min range, RVOL ≥ {cfg['rvol_min']}×, top {cfg['top_n']}, exit stop or {cfg['hard_exit']}",
           "symbols": len(data), "sessions": len(days), "seed": a.seed, "stats": s, "skips": skips,
           "verdict": verdict(s), "trades": trades}
    if not a.no_write:
        state.write_json("replay.json", out)
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    print(out["rule"])
    print(f"{len(data)} symbols, {len(days)} sessions, seed {a.seed}")
    if s["trades"]:
        print(f"  trades {s['trades']} · wins {s['wins']} ({s['win_rate']:.0%}, 95% {s['win_rate_95'][0]:.0%}–{s['win_rate_95'][1]:.0%})"
              f" · exits {s['exits']}")
        print(f"  gross ₹{s['gross_total']:,.2f} − charges ₹{s['charges_total']:,.2f} = net ₹{s['net_total']:,.2f}"
              f" · max drawdown ₹{s['max_drawdown']:,.2f} · profit factor {s['profit_factor']}")
        print(f"  long {s['by_side']['LONG']} · short {s['by_side']['SHORT']}")
    if skips:
        print(f"  not traded: {skips}")
    print(out["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
