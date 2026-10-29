"""Candles: the one file format every skill reads, plus sessions, daily bars, ATR and relative volume.

File format (intraday/candles/<SYMBOL>.json), the same shape Kite's historical API returns:
    {"symbol": "LT", "interval": "5minute", "source": "kite", "tick_size": 0.05,
     "candles": [["2026-10-29T09:15:00+05:30", open, high, low, close, volume], ...]}
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from .clock import IST


@dataclass(frozen=True)
class Bar:
    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: float

    @property
    def end(self) -> datetime:
        return self.t


def parse_time(text: str) -> datetime:
    text = text.replace("Z", "+00:00")
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":   # Kite: 2026-10-29T09:15:00+0530
        text = text[:-2] + ":" + text[-2:]
    dt = datetime.fromisoformat(text)
    return (dt if dt.tzinfo else dt.replace(tzinfo=IST)).astimezone(IST)


def from_rows(rows) -> list[Bar]:
    bars = []
    for row in rows:
        t, o, h, l, c, v = row[:6]
        if None in (o, h, l, c):
            continue
        bars.append(Bar(parse_time(t) if isinstance(t, str) else t, float(o), float(h), float(l), float(c), float(v or 0)))
    bars.sort(key=lambda b: b.t)
    return bars


def load(path: Path) -> dict:
    data = json.loads(Path(path).read_text())
    data["bars"] = from_rows(data.get("candles", []))
    return data


def save(path: Path, symbol: str, interval: str, source: str, rows, tick_size=None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"symbol": symbol, "interval": interval, "source": source, "tick_size": tick_size,
               "candles": [[r[0] if isinstance(r[0], str) else r[0].isoformat(), *r[1:6]] for r in rows]}
    path.write_text(json.dumps(payload, separators=(",", ":")))


def sessions(bars: list[Bar]) -> dict[date, list[Bar]]:
    out: dict[date, list[Bar]] = {}
    for b in bars:
        out.setdefault(b.t.date(), []).append(b)
    return out


def daily_bars(by_day: dict[date, list[Bar]]) -> list[tuple[date, float, float, float, float, float]]:
    rows = []
    for d in sorted(by_day):
        day = by_day[d]
        rows.append((d, day[0].o, max(b.h for b in day), min(b.l for b in day), day[-1].c, sum(b.v for b in day)))
    return rows


def atr(daily: list[tuple], days: int = 14) -> float | None:
    """Average true range over the last `days` sessions (simple mean of true ranges)."""
    if len(daily) < days + 1:
        return None
    trs = []
    for prev, cur in zip(daily[-days - 1:-1], daily[-days:]):
        trs.append(max(cur[2] - cur[3], abs(cur[2] - prev[4]), abs(cur[3] - prev[4])))
    return sum(trs) / days


def bar_at(day_bars: list[Bar], start: time) -> Bar | None:
    for b in day_bars:
        if b.t.time() == start:
            return b
    return None


def opening_range(day_bars: list[Bar], minutes: int = 5, bar_minutes: int = 5) -> dict | None:
    """The first `minutes` of the session from 09:15: high, low, open, close, volume. None if bars are missing."""
    need = max(1, minutes // bar_minutes)
    first = [b for b in day_bars if b.t.time() >= time(9, 15)][:need]
    if len(first) < need or first[0].t.time() != time(9, 15):
        return None
    return {"high": max(b.h for b in first), "low": min(b.l for b in first), "open": first[0].o,
            "close": first[-1].c, "volume": sum(b.v for b in first)}


def window_volume(day_bars: list[Bar], minutes: int = 5, bar_minutes: int = 5) -> float | None:
    """Volume of the first `minutes` from 09:15. None if any of those bars is missing."""
    need = max(1, minutes // bar_minutes)
    first = [b for b in day_bars if b.t.time() >= time(9, 15)][:need]
    if len(first) < need or first[0].t.time() != time(9, 15):
        return None
    return sum(b.v for b in first)


def relative_volume(today: float | None, history: list[float | None]) -> float | None:
    vols = [h for h in history if h]
    if not vols or not today:
        return None
    return today / (sum(vols) / len(vols))
