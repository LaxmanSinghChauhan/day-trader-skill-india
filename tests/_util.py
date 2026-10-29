"""Test helpers: load a skill script by path, a temporary intraday/ workspace, synthetic NSE sessions.

The candles here are synthetic (clearly so: round numbers, flat history) so every expected number in the
tests can be worked out by hand. Real candles are never committed: Kite's data is licensed to you.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nse_core import clock  # noqa: E402


def load_script(rel: str):
    path = ROOT / rel
    name = "skill_" + rel.replace("/", "_").replace("-", "_").removesuffix(".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Workspace:
    """A fresh intraday/ folder for one test; NSE_TRADER_DIR points at it."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "intraday"
        self.path.mkdir()
        self._old = os.environ.get("NSE_TRADER_DIR")
        os.environ["NSE_TRADER_DIR"] = str(self.path)
        return self

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop("NSE_TRADER_DIR", None)
        else:
            os.environ["NSE_TRADER_DIR"] = self._old
        self._tmp.cleanup()

    def write(self, name: str, data) -> None:
        p = self.path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))

    def read(self, name: str):
        return json.loads((self.path / name).read_text())


def trading_days(end: date, n: int) -> list[date]:
    days, d = [], end
    while len(days) < n:
        if clock.is_trading_day(d):
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def session(day: date, first: tuple, path: list[float], first_vol: float, vol: float = 1000) -> list[list]:
    """09:15 bar = `first` (o, h, l, c); then one 5-minute bar per close in `path`; flat to 15:25."""
    t = datetime.combine(day, time(9, 15), clock.IST)
    o, h, l, c = first
    rows = [[t.isoformat(), o, h, l, c, first_vol]]
    prev = c
    closes = list(path)
    while len(rows) < 75:                       # 09:15 … 15:25
        t += timedelta(minutes=5)
        close = closes.pop(0) if closes else prev
        rows.append([t.isoformat(), prev, round(max(prev, close) + 0.2, 2), round(min(prev, close) - 0.2, 2), close, vol])
        prev = close
    return rows


def flat_history(days: list[date], base: float) -> list[list]:
    rows = []
    for d in days:
        rows += session(d, (base, base + 2, base - 2, base), [], 1000)
    return rows


def write_candles(ws: Workspace, symbol: str, rows: list[list], tick=None) -> None:
    ws.write(f"candles/{symbol}.json", {"symbol": symbol, "interval": "5minute", "source": "synthetic",
                                        "tick_size": tick, "candles": rows})
