"""Paper fills on 5-minute bars, shared by nse-replay and nse-autopilot so both assume exactly the same.

The entry is a resting stop-limit order: trigger one tick beyond the range, limit = the IOC cap. A bar that
reaches the trigger fills it at the trigger (or the bar's open if it opened past it) plus one tick of
slippage, never beyond the cap; a bar that opens past the cap is a gap and doesn't fill. A stop fills at the
stop (or the open if it gapped through) minus one tick. Within the entry bar a stop hit counts (worst case).

Timing: a 5-minute bar is only known ~40 s after it ends, so the watchlist (and its resting orders) exists
from just after the opening window. The first bar that can fill is the one starting after that moment.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from .clock import IST
from .ticks import to_tick

SLIPPAGE_TICKS = 1
ARM_LAG = timedelta(seconds=40)


def first_tradable_bar_start(day, cfg: dict) -> datetime:
    """The start of the first bar a resting entry can fill in: one bar after the opening window."""
    window = max(cfg["orb_minutes"], cfg["rvol_minutes"])
    armed = datetime.combine(day, time(9, 15), IST) + timedelta(minutes=window) + ARM_LAG
    return armed


def cap_price(side: str, trigger: float, tick: float, cfg: dict) -> float:
    if side == "LONG":
        return float(to_tick(trigger * (1 + cfg["entry_cap_pct"]), tick, "down"))
    return float(to_tick(trigger * (1 - cfg["entry_cap_pct"]), tick, "up"))


def entry_fill(side: str, trigger: float, cap: float, bar, tick: float):
    """None: not triggered in this bar. "gap": opened past the cap, no fill. Else the fill price."""
    long = side == "LONG"
    if not ((long and bar.h >= trigger) or (not long and bar.l <= trigger)):
        return None
    base = max(trigger, bar.o) if long else min(trigger, bar.o)
    if (long and base > cap) or (not long and base < cap):
        return "gap"
    fill = base + SLIPPAGE_TICKS * tick if long else base - SLIPPAGE_TICKS * tick
    fill = min(fill, cap) if long else max(fill, cap)
    return round(fill, 2)


def stop_hit(side: str, stop: float, bar) -> bool:
    return bar.l <= stop if side == "LONG" else bar.h >= stop


def stop_fill(side: str, stop: float, bar, tick: float, entry_bar: bool) -> float:
    long = side == "LONG"
    px = stop if entry_bar else (min(stop, bar.o) if long else max(stop, bar.o))
    return round(px - SLIPPAGE_TICKS * tick if long else px + SLIPPAGE_TICKS * tick, 2)
