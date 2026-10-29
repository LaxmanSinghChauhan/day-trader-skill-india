"""Zerodha intraday equity charges, exact to the paisa, plus break-even and the charges gate.

The arithmetic follows Zerodha's public brokerage calculator (function `cal_intra` in
https://zerodha.com/static/js/brokerage.js, read 18 Oct 2026): same rates, same order of operations,
same rounding. That code works in JavaScript doubles and rounds with toFixed(2) / Math.round, so we do
the same and get identical results (tests: 184 calculator results captured on 18 Oct 2026).

This is the calculator's estimate; your contract note is final. If Zerodha changes its rates, update
RATES and re-capture tests/fixtures/zerodha-calculator-intraday.csv.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal

RATES = {
    "brokerage": 0.0003,      # 0.03 % per executed order …
    "brokerage_cap": 20.0,    # … or ₹20, whichever is lower
    "stt_sell": 0.00025,      # 0.025 % on the sell value
    "nse_txn": 0.0000297,     # NSE transaction charge
    "nse_ipft": 0.000001,     # NSE investor protection fund (added to the transaction charge)
    "bse_txn": 0.0000375,     # BSE transaction charge
    "sebi": 0.000001,         # ₹10 per crore
    "gst": 0.18,              # on brokerage + transaction + SEBI
    "stamp_buy": 0.00003,     # 0.003 % on the buy value
}

MIN_NET_TO_CHARGES_AT_1R = 3   # the gate: net at 1R must be at least 3 × that trade's charges


def to_fixed2(value: float) -> float:
    """JavaScript parseFloat(x.toFixed(2)): rounds the exact binary value, ties away from zero."""
    return float(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def js_round(value: float) -> float:
    return float(math.floor(value + 0.5))


@dataclass(frozen=True)
class Charges:
    exchange: str
    turnover: float
    brokerage: float
    stt: float
    exchange_txn: float
    sebi: float
    stamp: float
    gst: float
    total: float
    breakeven_per_share: float
    gross: float
    net: float

    def as_dict(self) -> dict:
        return asdict(self)


def intraday(buy: float, sell: float, qty: int, exchange: str = "NSE") -> Charges:
    """Charges for one intraday round trip: buy `qty` at `buy`, sell at `sell` (order doesn't matter)."""
    if qty <= 0:
        raise ValueError("Quantity must be at least 1")
    if buy <= 0 or sell <= 0:
        raise ValueError("Buy and sell prices must be greater than zero")
    exchange = exchange.upper()
    if exchange not in ("NSE", "BSE"):
        raise ValueError("Exchange must be NSE or BSE")
    r = RATES
    bp, sp, q = to_fixed2(float(buy)), to_fixed2(float(sell)), to_fixed2(float(qty))

    b_buy = r["brokerage_cap"] if bp * q * r["brokerage"] > r["brokerage_cap"] else to_fixed2(bp * q * r["brokerage"])
    b_sell = r["brokerage_cap"] if sp * q * r["brokerage"] > r["brokerage_cap"] else to_fixed2(sp * q * r["brokerage"])
    brokerage = to_fixed2(b_buy + b_sell)
    turnover = to_fixed2((bp + sp) * q)
    stt = js_round(to_fixed2(sp * q * r["stt_sell"]))
    sebi = to_fixed2(turnover * r["sebi"])
    if exchange == "NSE":
        txn = to_fixed2(r["nse_txn"] * turnover)
        txn = to_fixed2(txn + to_fixed2(r["nse_ipft"] * turnover))
    else:
        txn = to_fixed2(to_fixed2(r["bse_txn"] * turnover) + 0)
    gst = to_fixed2(r["gst"] * (brokerage + txn + sebi))
    stamp = js_round(to_fixed2(bp * q * r["stamp_buy"]))
    total = to_fixed2(brokerage + stt + txn + gst + sebi + stamp)
    return Charges(exchange, turnover, brokerage, stt, txn, sebi, stamp, gst, total,
                   to_fixed2(total / q), round((sp - bp) * q, 2), to_fixed2((sp - bp) * q - total))


def round_trip(side: str, entry: float, exit_: float, qty: int, exchange: str = "NSE") -> Charges:
    """LONG buys at entry and sells at exit; SHORT sells at entry and buys back at exit."""
    side = side.upper()
    if side == "LONG":
        return intraday(entry, exit_, qty, exchange)
    if side == "SHORT":
        return intraday(exit_, entry, qty, exchange)
    raise ValueError("Side must be LONG or SHORT")


def net_pnl(side: str, entry: float, exit_: float, qty: int, exchange: str = "NSE") -> float:
    return round_trip(side, entry, exit_, qty, exchange).net


def break_even_exit(side: str, entry: float, qty: int, tick: float, exchange: str = "NSE") -> float:
    """The first exit on the tick grid where net P&L ≥ 0: estimate from the charges, then adjust by ticks."""
    t = Decimal(str(tick))
    e = Decimal(str(entry))
    if e % t != 0:
        raise ValueError(f"The entry ₹{entry} isn't on the ₹{tick} tick grid (NSE slab ticks: ₹0.10 above ₹1,000)")
    away = t if side.upper() == "LONG" else -t
    per_share = Decimal(str(round_trip(side, entry, entry, qty, exchange).total)) / qty
    price = e + away * (per_share / t).to_integral_value(rounding="ROUND_CEILING")
    for _ in range(10_000):
        if net_pnl(side, float(e), float(price), qty, exchange) >= 0:
            break
        price += away
    else:
        raise ValueError(f"No break-even within 10,000 ticks of {entry}")
    closer = price - away
    while closer != e and net_pnl(side, float(e), float(closer), qty, exchange) >= 0:
        price, closer = closer, closer - away
    return float(price)


def gate(side: str, entry: float, stop: float, qty: int, tick: float, exchange: str = "NSE") -> dict:
    """The charges gate at 1R: is the trade worth its costs? Returns the numbers and a reason when it fails."""
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("Entry and stop must differ")
    if (side.upper() == "LONG") != (stop < entry):
        raise ValueError(f"For a {side.upper()} trade the stop must be {'below' if side.upper() == 'LONG' else 'above'} the entry")
    one_r = entry + risk if side.upper() == "LONG" else entry - risk
    at_1r = round_trip(side, entry, one_r, qty, exchange)
    at_stop = round_trip(side, entry, stop, qty, exchange)
    ok = at_1r.net >= MIN_NET_TO_CHARGES_AT_1R * at_1r.total
    return {
        "pass": ok,
        "reason": None if ok else (f"Net at 1R ₹{at_1r.net:.2f} is less than {MIN_NET_TO_CHARGES_AT_1R} × "
                                   f"charges ₹{at_1r.total:.2f}: the trade can't pay for itself"),
        "one_r_price": round(one_r, 2),
        "net_at_1r": at_1r.net,
        "charges_at_1r": at_1r.total,
        "net_at_stop": at_stop.net,
        "charges_at_stop": at_stop.total,
        "charges_in_r": round(at_stop.total / (risk * qty), 3),
        "break_even_exit": break_even_exit(side, entry, qty, tick, exchange),
    }
