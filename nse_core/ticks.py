"""NSE cash-segment tick sizes and rounding to the tick grid.

Slabs from NSE circular NSE/CMTR/67133 (effective 15 Apr 2025), as published by Zerodha:
below ₹250 → 0.01; ₹250–1,000 → 0.05; >1,000–5,000 → 0.10; >5,000–10,000 → 0.50;
>10,000–20,000 → 1.00; above 20,000 → 5.00. NSE reviews the slab monthly on the previous month's
price, so the live tick can differ from this table near a boundary: prefer the `tick_size` field of
Kite's instrument dump when you have it.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

_SLABS = (
    (Decimal("250"), Decimal("0.01"), False),     # price < 250
    (Decimal("1000"), Decimal("0.05"), True),     # 250 <= price <= 1000
    (Decimal("5000"), Decimal("0.10"), True),
    (Decimal("10000"), Decimal("0.50"), True),
    (Decimal("20000"), Decimal("1"), True),
)


def tick_size(price) -> Decimal:
    p = Decimal(str(price))
    for limit, tick, inclusive in _SLABS:
        if p < limit or (inclusive and p == limit):
            return tick
    return Decimal("5")


def to_tick(price, tick=None, mode: str = "nearest") -> Decimal:
    """Round a price onto the tick grid. mode: nearest | up | down."""
    p = Decimal(str(price))
    t = Decimal(str(tick)) if tick is not None else tick_size(p)
    rounding = {"nearest": ROUND_HALF_UP, "up": ROUND_CEILING, "down": ROUND_FLOOR}[mode]
    steps = (p / t).quantize(Decimal("1"), rounding=rounding)
    return (steps * t).quantize(t)


def on_tick(price, tick) -> bool:
    return Decimal(str(price)) % Decimal(str(tick)) == 0
