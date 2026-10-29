"""Stop, quantity and the charges fit: one function each, shared by nse-exit, nse-size and nse-replay."""
from __future__ import annotations

import math

from . import charges as ch
from .ticks import to_tick


def base_stop(side: str, entry: float, atr: float, tick: float, cfg: dict) -> tuple[float, str]:
    """Stop distance = max(stop_atr_fraction × ATR, stop_min_pct × entry), rounded away from the entry."""
    by_atr = cfg["stop_atr_fraction"] * atr
    by_pct = cfg["stop_min_pct"] * entry
    dist = max(by_atr, by_pct)
    why = (f"{cfg['stop_atr_fraction']:.0%} of ATR ₹{atr:.2f} = ₹{by_atr:.2f}" if by_atr >= by_pct
           else f"minimum {cfg['stop_min_pct']:.1%} of price = ₹{by_pct:.2f}")
    if side == "LONG":
        return float(to_tick(entry - dist, tick, "down")), why
    return float(to_tick(entry + dist, tick, "up")), why


def quantity(side: str, entry: float, stop: float, cfg: dict, margin: float | None = None, exchange: str = "NSE") -> tuple[int, str]:
    """Largest qty within the per-stock cap, the margin, and a net loss at the stop (charges included) ≤ risk_per_trade."""
    caps = {"per-stock cap": math.floor(cfg["max_per_stock"] / entry)}
    if margin is not None:
        caps["margin"] = math.floor(margin * cfg["mis_leverage"] / entry)
    per_share = abs(entry - stop)
    caps["risk"] = math.floor(cfg["risk_per_trade"] / per_share) if per_share > 0 else 0
    qty = min(caps.values())
    while qty > 0 and -ch.net_pnl(side, entry, stop, qty, exchange) > cfg["risk_per_trade"]:
        qty -= 1                      # charges push the loss over the limit: one share less
    limit = min(caps, key=caps.get)
    return max(qty, 0), limit


def fit_stop_to_charges(side: str, entry: float, stop: float, tick: float, cfg: dict, margin: float | None = None,
                        exchange: str = "NSE", max_ticks: int = 400) -> tuple[float, int, bool]:
    """Widen a too-tight stop, tick by tick, until the trade passes the 3× charges gate at 1R.

    A stop so tight that charges eat more than ~25 % of R can't pay for itself. Returns (stop, qty, widened).
    """
    widened = False
    for _ in range(max_ticks):
        qty, _ = quantity(side, entry, stop, cfg, margin, exchange)
        if qty <= 0:
            return stop, 0, widened
        if ch.gate(side, entry, stop, qty, tick, exchange)["pass"]:
            return stop, qty, widened
        stop = round(stop - tick, 2) if side == "LONG" else round(stop + tick, 2)
        widened = True
    return stop, 0, widened
