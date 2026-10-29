"""NSE cash-market clock: IST, session phases, trading days, holidays.

Holidays: NSE capital-market segment, 2026, weekdays only (weekend holidays don't change anything).
Read from Zerodha's market holiday calendar on 29 Oct 2026, which follows NSE's circulars. NSE publishes
next year's list in December: add it to HOLIDAYS (or to "extra_holidays" in intraday/config.json) and
check against the current NSE circular before trading.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")

PRE_OPEN_START = time(9, 0)
PRE_OPEN_ORDER_ENTRY_END = time(9, 8)
NORMAL_OPEN = time(9, 15)
NORMAL_CLOSE = time(15, 30)
ZERODHA_MIS_SQUARE_OFF = time(15, 25)   # equity MIS, ₹50 + GST per position (Zerodha, Dec 2025)

HOLIDAYS = {
    date(2026, 1, 15): "Municipal Corporation elections in Maharashtra",
    date(2026, 1, 26): "Republic Day",
    date(2026, 3, 3): "Holi",
    date(2026, 3, 26): "Shri Ram Navami",
    date(2026, 3, 31): "Shri Mahavir Jayanti",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 5, 28): "Bakri Eid",
    date(2026, 6, 26): "Moharram",
    date(2026, 9, 14): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 10): "Diwali Balipratipada",
    date(2026, 11, 24): "Prakash Gurpurb Sri Guru Nanak Dev",
    date(2026, 12, 25): "Christmas",
}
KNOWN_YEARS = {2026}

# Special sessions on non-trading days. Timings come by NSE circular shortly before the day.
SPECIAL_SESSIONS = {
    date(2026, 11, 8): "Muhurat trading (Diwali Laxmi Pujan, Sunday); timing by NSE circular",
}


def now_ist() -> datetime:
    return datetime.now(IST)


def parse_now(text: str | None) -> datetime:
    """`--now "2026-10-29 09:20"` pins the clock (IST); None means the real clock."""
    if not text:
        return now_ist()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=IST)
        except ValueError:
            pass
    raise ValueError(f"Can't read the time {text!r}; use 'YYYY-MM-DD HH:MM' (IST)")


def holiday_name(day: date, extra: dict | None = None) -> str | None:
    if extra and day.isoformat() in extra:
        return extra[day.isoformat()]
    return HOLIDAYS.get(day)


def is_trading_day(day: date, extra: dict | None = None) -> bool:
    return day.weekday() < 5 and holiday_name(day, extra) is None


def calendar_known(day: date) -> bool:
    return day.year in KNOWN_YEARS


def previous_trading_day(day: date, extra: dict | None = None) -> date:
    d = day - timedelta(days=1)
    while not is_trading_day(d, extra):
        d -= timedelta(days=1)
    return d


def next_trading_day(day: date, extra: dict | None = None) -> date:
    d = day + timedelta(days=1)
    while not is_trading_day(d, extra):
        d += timedelta(days=1)
    return d


def phase(moment: datetime, extra: dict | None = None) -> str:
    """closed | pre-open | open | post-close (normal market of the NSE cash segment)."""
    moment = moment.astimezone(IST)
    if not is_trading_day(moment.date(), extra):
        return "closed"
    t = moment.time()
    if PRE_OPEN_START <= t < NORMAL_OPEN:
        return "pre-open"
    if NORMAL_OPEN <= t < NORMAL_CLOSE:
        return "open"
    if t >= NORMAL_CLOSE:
        return "post-close"
    return "closed"


def hhmm(text: str) -> time:
    h, m = text.split(":")
    return time(int(h), int(m))


def is_last_tuesday(day: date) -> bool:
    """Last Tuesday of the month: NSE's monthly equity-derivative expiry day since Sep 2025
    (it moves to the previous trading day on a holiday). Expiry days move index heavyweights."""
    if day.weekday() != 1:
        return False
    return (day + timedelta(days=7)).month != day.month
