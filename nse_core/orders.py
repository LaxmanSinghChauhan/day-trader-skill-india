"""Order fingerprints and the trade ledger, shared by nse-risk, nse-kite and nse-journal."""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

from . import charges as ch
from . import state

EXEC_FIELDS = ("kind", "date", "symbol", "exchange", "transaction_type", "order_type", "price", "quantity",
               "product", "validity", "stop", "position_id")


def fingerprint(order: dict) -> str:
    """The exact executable order. Change any of these and nse-risk must check it again."""
    core = {k: order.get(k) for k in EXEC_FIELDS}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def confirm_code(order: dict) -> str:
    return fingerprint(order)[:6].upper()


def ledger() -> dict:
    return state.read_json("state/ledger.json", {"trades": [], "orders": []})


def save_ledger(data: dict) -> None:
    state.write_json("state/ledger.json", data)


def open_trades(led: dict) -> list[dict]:
    return [t for t in led["trades"] if t["status"] == "open"]


def realised(led: dict, start: date, end: date) -> float:
    return round(sum(t.get("net", 0) for t in led["trades"]
                     if t["status"] == "closed" and start.isoformat() <= t["date"] <= end.isoformat()), 2)


def open_risk(led: dict, exchange: str = "NSE") -> float:
    """Worst case for what's open: the net loss if every stop fills at its price."""
    total = 0.0
    for t in open_trades(led):
        total += max(0.0, -ch.net_pnl(t["side"], t["entry_price"], t["stop"], t["qty"], exchange))
    return round(total, 2)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())
