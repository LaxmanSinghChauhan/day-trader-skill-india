"""The Stocks-in-Play opening-range rule for one symbol on one day, shared by the scanner and the replay.

The price range is the first `orb_minutes` (09:15–09:20). Relative volume is measured over the first
`rvol_minutes` (default the same 5): Yahoo's NSE bars carry no volume at 09:15, so with Yahoo set it to 10
(09:15–09:25), and nothing can be decided until that window has closed.
"""
from __future__ import annotations

from datetime import date

from . import candles as cd
from .ticks import tick_size, to_tick


def measure(sym: str, by_day: dict, today: date, cfg: dict, tick: float | None = None, source: str | None = None) -> dict:
    """Opening range, relative volume, ATR, direction and trigger. A dict with "skip" when it can't trade."""
    if today not in by_day:
        return {"symbol": sym, "skip": "no bars today"}
    orng = cd.opening_range(by_day[today], cfg["orb_minutes"], cfg["bar_minutes"])
    if not orng:
        return {"symbol": sym, "skip": "opening bar missing"}
    past_days = sorted(d for d in by_day if d < today)
    history = [cd.opening_range(by_day[d], cfg["orb_minutes"], cfg["bar_minutes"]) for d in past_days[-cfg["rvol_lookback"]:]]
    history = [h for h in history if h]
    if len(history) < max(5, cfg["rvol_lookback"] // 2):
        return {"symbol": sym, "skip": f"only {len(history)} past sessions for the volume baseline"}
    vmin = cfg.get("rvol_minutes", cfg["orb_minutes"])
    vol_today = cd.window_volume(by_day[today], vmin, cfg["bar_minutes"])
    if not vol_today:
        return {"symbol": sym, "skip": "no volume in the opening bars (Yahoo leaves the 09:15 bar empty: "
                                       "use Kite, or set rvol_minutes to 10)"}
    vol_hist = [cd.window_volume(by_day[d], vmin, cfg["bar_minutes"]) for d in past_days[-cfg["rvol_lookback"]:]]
    rvol = cd.relative_volume(vol_today, vol_hist)
    daily = cd.daily_bars({d: by_day[d] for d in past_days[-(cfg["atr_days"] + 1):]})
    atr = cd.atr(daily, cfg["atr_days"])
    if rvol is None or atr is None:
        return {"symbol": sym, "skip": "not enough data for RVOL or ATR"}
    prev_close = daily[-1][4]
    if prev_close < cfg["min_price"]:
        return {"symbol": sym, "skip": f"price under ₹{cfg['min_price']}"}
    span = orng["high"] - orng["low"]
    body = orng["close"] - orng["open"]
    side = None if span <= 0 or abs(body) <= cfg["doji_body_pct"] * span else ("LONG" if body > 0 else "SHORT")
    tick = tick or float(tick_size(orng["close"]))
    hit = {"symbol": sym, "date": today.isoformat(), "rvol": round(rvol, 2), "atr": round(atr, 2), "tick": tick,
           "prev_close": prev_close, "range_high": orng["high"], "range_low": orng["low"],
           "first_open": orng["open"], "first_close": orng["close"], "opening_volume": vol_today,
           "side": side, "source": source}
    if side is None:
        hit["skip"] = "doji first candle: no direction"
    elif side == "SHORT" and not cfg["allow_short"]:
        hit["skip"] = "red first candle and shorts are off"
    else:
        raw = orng["high"] + tick if side == "LONG" else orng["low"] - tick
        hit["trigger"] = float(to_tick(raw, tick))
    return hit


def rank(measured: list[dict], cfg: dict) -> tuple[list[dict], list[dict]]:
    """In play = RVOL ≥ rvol_min, sorted by RVOL; keep the top_n, then the ones with a direction can trade."""
    in_play = sorted((r for r in measured if "rvol" in r and r["rvol"] >= cfg["rvol_min"]), key=lambda r: -r["rvol"])
    top = in_play[:cfg["top_n"]]
    return [r for r in top if "trigger" in r], in_play
