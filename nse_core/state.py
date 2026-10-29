"""The `intraday/` workspace: config with defaults, and small JSON files the skills hand to each other."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

# Defaults are the pack author's own limits for a ₹50,000 account. Change them in intraday/config.json.
DEFAULTS = {
    "paper": True,
    "exchange": "NSE",
    "product": "MIS",
    "capital": 50000,
    "risk_per_trade": 500,          # max loss at the stop, charges included
    "max_daily_loss": 1500,
    "max_weekly_loss": 5000,
    "max_trades_per_day": 30,
    "max_open_positions": 3,
    "max_per_stock": 10000,         # position value cap per stock
    "mis_leverage": 5,              # what your broker allows for MIS; Kite's margin API is the truth
    "allow_short": True,
    "one_trade_per_stock": True,
    "entries_from": "09:20",
    "entries_until": "14:30",
    "hard_exit": "15:10",
    "orb_minutes": 5,
    "bar_minutes": 5,
    "rvol_minutes": 5,              # volume window from 09:15; 10 with Yahoo (its 09:15 bar has no volume)
    "rvol_min": 3.0,
    "rvol_lookback": 14,
    "top_n": 10,
    "atr_days": 14,
    "stop_atr_fraction": 0.10,
    "stop_min_pct": 0.004,
    "entry_cap_pct": 0.0005,        # IOC limit at most 0.05 % beyond the trigger
    "doji_body_pct": 0.10,          # body under 10 % of the range = doji, no trade
    "min_price": 50,
    "min_turnover_cr": 20,          # autopilot: average daily traded value over 20 days, ₹ crore
    "autopilot_source": "yahoo",    # yahoo (free, unofficial) or kite (Connect app)
    "circuit_room_pct": 2.0,        # skip entries within 2 % of the circuit limit
    "max_orders_per_second": 5,     # SEBI's retail-algo threshold is 10 per second
    "event_windows": [],            # [{"from": "2026-12-04 09:55", "to": "2026-12-04 10:20", "why": "RBI policy"}]
    "blocked": [],                  # symbols you never trade
    "extra_holidays": {},           # {"2027-01-26": "Republic Day"}
}


def workspace() -> Path:
    return Path(os.environ.get("NSE_TRADER_DIR", "intraday"))


def path(name: str) -> Path:
    return workspace() / name


def read_json(name: str, default=None):
    p = path(name)
    if not p.exists():
        return default
    return json.loads(p.read_text())


def write_json(name: str, data) -> Path:
    p = path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, p)
    return p


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    user = read_json("config.json", {}) or {}
    unknown = sorted(set(user) - set(DEFAULTS) - {"_comment"})
    cfg.update({k: v for k, v in user.items() if k != "_comment"})
    cfg["_unknown_keys"] = unknown
    return cfg
