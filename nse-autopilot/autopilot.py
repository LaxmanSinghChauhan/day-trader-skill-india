#!/usr/bin/env python3
"""Paper-trading autopilot: one NSE day, the whole chain, by itself. It never sends an order to a broker.

  autopilot.py run [--source yahoo|kite]        # today on the real clock: data at 08:30, scan after the opening
                                                # window, trades on paper, closes by 15:10, report at 15:35
  autopilot.py simulate --date 2026-10-29       # the same day-loop over saved candles (separate sim ledger)
  autopilot.py status

What it does each 5 minutes: refresh the bars of the stocks it watches or holds, then on every newly
completed bar: fill a resting stop-limit entry (trigger, capped) if the bar reached it, run the exact
nse-risk check on that order, open the paper position, and manage stops and the 15:10 exit. Fills follow
nse_core/paper.py, the same rules as nse-replay. Only bars that start after the watchlist was ready count.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time as systime
from datetime import datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nse_core import candles as cd  # noqa: E402
from nse_core import charges as ch  # noqa: E402
from nse_core import clock, paper, sip, state  # noqa: E402
from nse_core import orders as od  # noqa: E402
from nse_core import plan as pl  # noqa: E402

BAR = timedelta(minutes=5)
PUBLISH_LAG = paper.ARM_LAG                   # wait this long after a bar ends before trusting it


def _load(rel: str):
    spec = importlib.util.spec_from_file_location("ap_" + rel.replace("/", "_").replace("-", "_")[:-3], ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


risk = _load("nse-risk/check.py")


# ---------- data ----------
class Feed:
    """Keeps intraday/candles/<SYMBOL>.json current. `simulate` uses SavedFeed, which fetches nothing."""

    def __init__(self, source: str):
        self.source = source
        self._tokens = None

    def _kite(self):
        from nse_core.kite import Kite
        if self._tokens is None:
            import csv
            import io
            k = Kite()
            self._tokens = {r["tradingsymbol"]: (int(r["instrument_token"]), float(r["tick_size"]))
                            for r in csv.DictReader(io.StringIO(k.instruments("NSE")))
                            if r["segment"] == "NSE" and r["instrument_type"] == "EQ"}
            self._k = k
        return self._k

    def _rows(self, sym: str, start, end, rng: str):
        if self.source == "yahoo":
            from nse_core import yahoo
            return yahoo.chart(sym, "5m", rng), None
        k = self._kite()
        if sym not in self._tokens:
            raise RuntimeError("not in Kite's NSE EQ instruments")
        token, tick = self._tokens[sym]
        return k.historical(token, "5minute", start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")), tick

    def _merge(self, sym: str, rows, tick, max_days: int = 60) -> None:
        """New rows replace old ones with the same start time (a bar still forming gets its final values later)."""
        f = state.path(f"candles/{sym}.json")
        try:
            old = json.loads(f.read_text()) if f.exists() else {"candles": [], "tick_size": tick}
        except ValueError:
            old = {"candles": [], "tick_size": tick}
        by_t = {r[0]: r for r in old["candles"]}
        by_t.update({r[0]: r for r in rows})
        merged = sorted(by_t.values(), key=lambda r: r[0])
        days = sorted({r[0][:10] for r in merged})[-max_days:]
        if days:
            merged = [r for r in merged if r[0][:10] >= days[0]]
        cd.save(f, sym, "5minute", self.source, merged, old.get("tick_size") or tick)

    def _fetch_all(self, jobs, now, log, label: str) -> None:
        """jobs: [(symbol, start, yahoo_range)]; 4 at a time, politely."""
        from concurrent.futures import ThreadPoolExecutor

        def one(job):
            sym, start, rng = job
            try:
                rows, tick = self._rows(sym, start, now, rng)
                self._merge(sym, rows, tick)
                return None
            except Exception as e:
                return f"{sym} ({e})"
            finally:
                systime.sleep(0.2)

        if self.source == "kite":
            self._kite()                      # load instruments once, before the threads start
        with ThreadPoolExecutor(max_workers=1 if self.source == "kite" else 4) as pool:
            failed = [r for r in pool.map(one, jobs) if r]
        if failed or label != "refresh":          # the 5-minute refresh only speaks up when something failed
            log(f"{label}: {len(jobs) - len(failed)} of {len(jobs)} fetched" + (f"; failed {len(failed)}: {', '.join(failed[:4])}" if failed else ""))

    def history(self, symbols, now, log) -> None:
        need = clock.previous_trading_day(now.date())
        jobs = []
        for s in symbols:
            f = state.path(f"candles/{s}.json")
            try:
                bars = cd.load(f)["bars"] if f.exists() else []
            except (ValueError, KeyError):
                bars = []                     # unreadable file: load it again
            if bars and bars[-1].t.date() >= need:
                continue
            fresh = len({b.t.date() for b in bars}) >= 20
            start = (bars[-1].t if fresh else now - timedelta(days=40))
            jobs.append((s, start, "5d" if fresh else "60d"))       # top up a good file, else load ~60 days
        if jobs:
            self._fetch_all(jobs, now, log, "history")
        else:
            log("history: all files current")

    def today(self, symbols, now, log) -> None:
        start = datetime.combine(now.date(), time(9, 15), clock.IST)
        self._fetch_all([(s, start, "1d") for s in symbols], now, log, "refresh")


class SavedFeed(Feed):
    def __init__(self):
        super().__init__("saved")

    def history(self, symbols, now, log):
        pass

    def today(self, symbols, now, log):
        pass


def completed(bars, now):
    return [b for b in bars if b.t + BAR + PUBLISH_LAG <= now]


# ---------- the day ----------
class Day:
    def __init__(self, cfg: dict, day, feed: Feed, log, prefix: str = ""):
        self.cfg, self.day, self.feed, self.log = cfg, day, feed, log
        self.prefix = prefix                              # "sim-" keeps a simulation away from the live day's files
        self.window = max(cfg["orb_minutes"], cfg["rvol_minutes"])
        self.scan_at = datetime.combine(day, time(9, 15), clock.IST) + timedelta(minutes=self.window)
        self.st = state.read_json(f"state/{prefix}autopilot.json") or {}
        if self.st.get("date") != day.isoformat():
            self.st = {"date": day.isoformat(), "phase": "pre", "armed": {}, "done": {}, "seen": {}, "log": []}

    def save(self):
        state.write_json(f"state/{self.prefix}autopilot.json", self.st)

    def note(self, text: str, now):
        line = f"{now:%H:%M} {text}"
        self.st["log"].append(line)
        self.log(line)

    def universe(self) -> list[str]:
        uni = state.read_json("universe.json")
        if not uni:
            raise SystemExit("No universe: run nse-scanner `scan.py universe` first.")
        blocked = {b.upper() for b in self.cfg["blocked"]}
        return [m["symbol"] for m in uni["members"] if m["symbol"] not in blocked]

    def liquid(self, symbols) -> list[str]:
        keep = []
        for s in symbols:
            f = state.path(f"candles/{s}.json")
            if not f.exists():
                continue
            daily = cd.daily_bars({d: b for d, b in cd.sessions(cd.load(f)["bars"]).items() if d < self.day})[-20:]
            if not daily:
                continue
            value = sum(r[4] * r[5] for r in daily) / len(daily) / 1e7
            if daily[-1][4] >= self.cfg["min_price"] and value >= self.cfg["min_turnover_cr"]:
                keep.append(s)
        return keep

    def bars(self, sym, now):
        f = state.path(f"candles/{sym}.json")
        data = cd.load(f)
        return completed(data["bars"], now), data.get("tick_size")

    # --- phases ---
    def tick(self, now) -> bool:
        """One step on the clock. Returns False when the day is finished."""
        if not clock.is_trading_day(self.day, self.cfg["extra_holidays"]):
            self.note(f"NSE is closed today ({clock.holiday_name(self.day, self.cfg['extra_holidays']) or 'weekend'})", now)
            return False
        ph = self.st["phase"]
        if ph == "pre" and now.time() >= time(8, 30):
            self.feed.history(self.universe(), now, lambda m: self.note(m, now))
            self.st["liquid"] = self.liquid(self.universe())
            self.st["phase"] = "ready"
            self.note(f"pre-market: {len(self.st['liquid'])} liquid stocks (≥ ₹{self.cfg['min_price']}, ≥ ₹{self.cfg['min_turnover_cr']} cr/day)", now)
        elif ph == "ready" and now >= self.scan_at + PUBLISH_LAG:
            self.scan(now)
        elif ph == "trading":
            self.manage(now)
            if now.time() >= time(15, 35):
                self.report(now)
                self.st["phase"] = "done"
        self.save()
        return self.st["phase"] != "done"

    def scan(self, now):
        symbols = self.st.get("liquid") or self.liquid(self.universe())
        self.feed.today(symbols, now, lambda m: self.note(m, now))
        measured = []
        for s in symbols:
            bars, tick = self.bars(s, now)
            measured.append(sip.measure(s, cd.sessions(bars), self.day, self.cfg, tick, self.feed.source))
        tradable, in_play = sip.rank([m for m in measured if "rvol" in m], self.cfg)
        armed_at = max(now, self.scan_at)
        for h in tradable:
            h["cap"] = paper.cap_price(h["side"], h["trigger"], h["tick"], self.cfg)
            h["armed_at"] = armed_at.isoformat()
            self.st["armed"][h["symbol"]] = h
        state.write_json(f"{self.prefix}watchlist.json", {"as_of": now.isoformat(timespec="minutes"), "hits": tradable,
                                            "in_play": len(in_play), "scanned": len(measured)})
        names = ", ".join(f"{h['symbol']} {h['side']} {h['rvol']}×" for h in tradable) or "none"
        self.note(f"scan: {len(measured)} scanned, {len(in_play)} in play, armed {len(tradable)}: {names}", now)
        self.st["phase"] = "trading"

    def manage(self, now):
        led = od.ledger()
        mine = [t for t in od.open_trades(led) if t.get("auto") and t["date"] == self.day.isoformat()]
        watch = sorted({t["symbol"] for t in mine} | set(self.st["armed"]))
        if watch:
            self.feed.today(watch, now, lambda m: self.note(m, now))
        events = state.read_json("events.json", {}) or {}
        until, hard = clock.hhmm(self.cfg["entries_until"]), clock.hhmm(self.cfg["hard_exit"])
        for sym in watch:
            bars, _ = self.bars(sym, now)
            seen = self.st["seen"].get(sym)
            new = [b for b in bars if b.t.date() == self.day and (not seen or b.t.isoformat() > seen)]
            for b in new:
                self.st["seen"][sym] = b.t.isoformat()
                pos = next((t for t in od.open_trades(led) if t.get("auto") and t["symbol"] == sym), None)
                if pos:
                    self.exit_if_due(led, pos, b, hard, now)
                    continue
                h = self.st["armed"].get(sym)
                if not h or b.t < datetime.fromisoformat(h["armed_at"]):      # only bars that start after arming
                    continue
                if b.t.time() >= until:
                    self.disarm(sym, "no trigger by " + self.cfg["entries_until"], now)
                    continue
                fill = paper.entry_fill(h["side"], h["trigger"], h["cap"], b, h["tick"])
                if fill is None:
                    continue
                if fill == "gap":
                    self.disarm(sym, f"opened past the cap ₹{h['cap']} at {b.t:%H:%M}", now)
                    continue
                self.enter(led, h, fill, b, events, now)
                pos = next((t for t in od.open_trades(led) if t.get("auto") and t["symbol"] == sym), None)
                if pos:
                    self.exit_if_due(led, pos, b, hard, now, entry_bar=True)
        if now.time() >= (datetime.combine(self.day, hard) + BAR + PUBLISH_LAG).time():
            for t in [t for t in od.open_trades(led) if t.get("auto") and t["date"] == self.day.isoformat()]:
                bars, _ = self.bars(t["symbol"], now)
                last = bars[-1].c if bars else t["entry_price"]
                self.close(led, t, last, "time", now, "no 15:10 bar: closed at the last price")
        od.save_ledger(led)

    def disarm(self, sym, why, now):
        self.st["armed"].pop(sym, None)
        self.st["done"][sym] = why
        self.note(f"{sym}: {why}", now)

    def enter(self, led, h, fill, b, events, now):
        side, tick = h["side"], h["tick"]
        stop, _ = pl.base_stop(side, fill, h["atr"], tick, self.cfg)
        stop, qty, _ = pl.fit_stop_to_charges(side, fill, stop, tick, self.cfg, None, self.cfg["exchange"])
        when = b.t + timedelta(minutes=2)                     # inside the bar the stop order would have filled in
        order = {"id": f"{h['symbol']}-{b.t:%H%M}", "kind": "entry", "date": self.day.isoformat(), "symbol": h["symbol"],
                 "exchange": self.cfg["exchange"], "side": side, "transaction_type": "BUY" if side == "LONG" else "SELL",
                 "order_type": "SL", "trigger_price": h["trigger"], "price": h["cap"], "quantity": qty,
                 "product": "MIS", "validity": "DAY", "tick": tick, "margin_checked": False,
                 "stop": {"transaction_type": "SELL" if side == "LONG" else "BUY", "order_type": "SL-M",
                          "trigger_price": stop, "market_protection": -1}}
        if qty <= 0:
            self.disarm(h["symbol"], "no quantity fits the limits", now)
            return
        block, _ = risk.check_order(order, self.cfg, led, events, when, [])
        if block:
            self.disarm(h["symbol"], "risk BLOCK: " + "; ".join(block), now)
            return
        led["trades"].append({"id": f"A-{order['id']}", "date": self.day.isoformat(), "symbol": h["symbol"], "side": side,
                              "qty": qty, "entry_price": fill, "entry_at": b.t.isoformat(), "stop": stop,
                              "hard_exit": self.cfg["hard_exit"], "status": "open", "paper": True, "auto": True, "tick": tick,
                              "rvol": h["rvol"], "fingerprint": od.fingerprint(order)})
        self.st["armed"].pop(h["symbol"], None)
        self.st["done"][h["symbol"]] = "entered"
        self.note(f"{h['symbol']}: PAPER {side} {qty} @ ₹{fill:,.2f} ({b.t:%H:%M} bar), stop ₹{stop:,.2f}", now)

    def exit_if_due(self, led, pos, b, hard, now, entry_bar=False):
        if not entry_bar and b.t.time() >= hard:
            self.close(led, pos, b.o, "time", now)
        elif paper.stop_hit(pos["side"], pos["stop"], b):
            self.close(led, pos, paper.stop_fill(pos["side"], pos["stop"], b, pos["tick"], entry_bar), "stop", now)

    def close(self, led, t, price, reason, now, note=None):
        rt = ch.round_trip(t["side"], t["entry_price"], price, t["qty"], self.cfg["exchange"])
        risk_rs = abs(t["entry_price"] - t["stop"]) * t["qty"]
        t.update({"status": "closed", "exit_price": round(price, 2), "exit_at": now.isoformat(timespec="minutes"),
                  "exit_reason": reason, "charges": rt.total, "gross": rt.gross, "net": rt.net,
                  "r": round(rt.net / risk_rs, 2) if risk_rs else None})
        self.note(f"{t['symbol']}: closed ({reason}) @ ₹{price:,.2f}, net ₹{rt.net:,.2f} ({t['r']}R){' · ' + note if note else ''}", now)

    def report(self, now):
        led = od.ledger()
        today = [t for t in led["trades"] if t.get("auto") and t["date"] == self.day.isoformat() and t["status"] == "closed"]
        net = round(sum(t["net"] for t in today), 2)
        charges = round(sum(t["charges"] for t in today), 2)
        wins = sum(1 for t in today if t["net"] > 0)
        rep = {"date": self.day.isoformat(), "trades": len(today), "wins": wins, "net": net, "charges": charges,
               "not_traded": self.st["done"], "log": self.st["log"]}
        state.write_json(f"reports/{self.prefix}autopilot-{self.day.isoformat()}.json", rep)
        self.note(f"report: {len(today)} paper trades, {wins} wins, net ₹{net:,.2f} after ₹{charges:,.2f} charges", now)


# ---------- commands ----------
def make_logger():
    logdir = state.path("logs")
    logdir.mkdir(parents=True, exist_ok=True)

    def log(line):
        print(line, flush=True)
        with open(logdir / f"autopilot-{clock.now_ist():%Y-%m-%d}.log", "a") as f:
            f.write(line + "\n")
    return log


def prepare_cfg(source: str) -> dict:
    cfg = state.load_config()
    if not cfg["paper"]:
        print("intraday/config.json says \"paper\": false. The autopilot trades on paper only and stays on paper;"
              " real orders go through nse-kite, one yes at a time.")
    if source == "yahoo" and cfg["rvol_minutes"] < 10:
        cfg["rvol_minutes"] = 10        # Yahoo's 09:15 bar has no volume for NSE stocks
    return cfg


def cmd_run(a) -> int:
    source = a.source or state.load_config()["autopilot_source"]
    cfg = prepare_cfg(source)
    log = make_logger()
    now = clock.now_ist()
    day = Day(cfg, now.date(), Feed(source), log)
    log(f"autopilot {now:%a %d %b %H:%M}: PAPER, data from {source}, scan at {day.scan_at:%H:%M}, hard exit {cfg['hard_exit']}")
    while day.tick(clock.now_ist()):
        now = clock.now_ist()
        if now.time() < time(8, 30):
            wake = datetime.combine(now.date(), time(8, 30), clock.IST)
        else:
            nxt = now.replace(second=0, microsecond=0) + timedelta(minutes=5 - now.minute % 5)
            wake = nxt + PUBLISH_LAG
        systime.sleep(max(5, (wake - now).total_seconds()))
    return 0


def cmd_simulate(a) -> int:
    old = os.environ.get("NSE_LEDGER")
    os.environ["NSE_LEDGER"] = "state/sim-ledger.json"          # never touch the real paper ledger
    try:
        return _simulate(a)
    finally:
        if old is None:
            os.environ.pop("NSE_LEDGER", None)
        else:
            os.environ["NSE_LEDGER"] = old


def _simulate(a) -> int:
    cfg = prepare_cfg(a.source or "saved")
    log = make_logger()
    day = datetime.strptime(a.date, "%Y-%m-%d").date()
    st = state.path("state/sim-autopilot.json")
    if st.exists():
        st.unlink()
    led = od.ledger()
    led["trades"] = [t for t in led["trades"] if t["date"] != a.date]
    od.save_ledger(led)
    d = Day(cfg, day, SavedFeed(), log, prefix="sim-")
    d.st["phase"] = "ready"
    d.st["liquid"] = d.liquid(d.universe()) if state.read_json("universe.json") else [p.stem for p in state.path("candles").glob("*.json")]
    t = datetime.combine(day, time(9, 15), clock.IST) + PUBLISH_LAG      # the live loop wakes at these times too
    while d.tick(t) and t.time() < time(15, 40):
        t += BAR
    d.tick(datetime.combine(day, time(15, 40), clock.IST))
    st.unlink(missing_ok=True)
    return 0


def cmd_status(a) -> int:
    st = state.read_json("state/autopilot.json")
    if not st:
        print("The autopilot hasn't run today.")
        return 1
    print(f"{st['date']} · phase {st['phase']} · armed {', '.join(st['armed']) or 'none'}")
    for line in st["log"][-15:]:
        print("  " + line)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--source", choices=["yahoo", "kite"])
    s = sub.add_parser("simulate")
    s.add_argument("--date", required=True)
    s.add_argument("--source", choices=["yahoo", "kite"], help="treat the saved data as this source (yahoo → 10-min volume window)")
    sub.add_parser("status")
    a = p.parse_args(argv)
    return {"run": cmd_run, "simulate": cmd_simulate, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
