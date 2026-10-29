"""The whole chain on one synthetic day: scan → entry → exit plan → size → risk → paper ticket → journal,
and the replay of the same day. Wed 28 Oct 2026; 15 flat sessions before it."""
import contextlib
import io
import unittest
from datetime import date

from _util import Workspace, flat_history, load_script, session, trading_days, write_candles

scan = load_script("nse-scanner/scan.py")
entry = load_script("nse-entry/entry.py")
plan = load_script("nse-exit/plan.py")
size = load_script("nse-size/size.py")
risk = load_script("nse-risk/check.py")
ticket = load_script("nse-kite/ticket.py")
journal = load_script("nse-journal/journal.py")
replay = load_script("nse-replay/replay.py")
briefing = load_script("nse-briefing/briefing.py")

DAY = date(2026, 10, 28)


def run(mod, *argv) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = mod.main(list(argv))
    return code, out.getvalue()


def build_market(ws):
    history = trading_days(DAY, 16)[:-1]                                   # 15 sessions: ATR(14) needs 15
    up = [504.5] + [round(505 + i * 0.5, 2) for i in range(30)]                 # trends to ~519.5
    fake = [404.4, 402.0, 399.0, 397.0, 396.0]                                  # breaks out, then the stop
    down = [445.8] + [round(445 - i * 0.2, 2) for i in range(25)]               # short, drifts lower
    write_candles(ws, "UPTREND", flat_history(history, 500) + session(DAY, (500, 504, 499, 503), up, 5000))
    write_candles(ws, "FAKEOUT", flat_history(history, 400) + session(DAY, (400, 404, 399.5, 403), fake, 4000))
    write_candles(ws, "REDDOWN", flat_history(history, 450) + session(DAY, (450, 450.5, 446, 446.5), down, 3500))
    write_candles(ws, "DOJI", flat_history(history, 300) + session(DAY, (300, 302, 298, 300.05), [], 6000))
    write_candles(ws, "QUIET", flat_history(history, 600) + session(DAY, (600, 602, 598, 601), [], 1000))


class Pipeline(unittest.TestCase):
    def test_scanner_lists_stocks_in_play(self):
        with Workspace() as ws:
            build_market(ws)
            code, out = run(scan, "sip", "--now", "2026-10-28 09:21")
            self.assertEqual(code, 0, out)
            wl = ws.read("watchlist.json")
            self.assertEqual([h["symbol"] for h in wl["hits"]], ["UPTREND", "FAKEOUT", "REDDOWN"])
            self.assertEqual(wl["doji_or_off"], ["DOJI"])
            up = wl["hits"][0]
            self.assertEqual((up["side"], up["rvol"], up["trigger"], up["tick"]), ("LONG", 5.0, 504.05, 0.05))
            self.assertEqual((wl["hits"][2]["side"], wl["hits"][2]["trigger"]), ("SHORT", 445.95))
            self.assertEqual(run(scan, "sip", "--now", "2026-10-28 09:17")[0], 1)       # range not complete
            self.assertEqual(run(scan, "sip", "--now", "2026-10-20 09:30")[0], 1)       # Dussehra

    def test_full_chain_in_paper(self):
        with Workspace() as ws:
            build_market(ws)
            run(scan, "sip", "--now", "2026-10-28 09:21")
            code, out = run(entry, "check", "UPTREND", "--price", "504.10", "--now", "2026-10-28 09:24")
            self.assertEqual(code, 0, out)
            self.assertEqual(ws.read("entry.json")["limit"], 504.30)
            self.assertEqual(run(entry, "check", "UPTREND", "--price", "505.00", "--now", "2026-10-28 09:24")[0], 1)  # too far

            self.assertEqual(run(plan, "UPTREND")[0], 0)
            p = ws.read("plan.json")
            self.assertEqual((p["entry"], p["stop"], p["gate"]), (504.30, 502.25, "PASS"))

            self.assertEqual(run(size, "--margin", "20000", "--now", "2026-10-28 09:24")[0], 0)
            order = ws.read("orders.json")["orders"][0]
            self.assertEqual((order["quantity"], order["validity"], order["stop"]["order_type"]), (19, "IOC", "SL-M"))

            code, out = run(risk, "--now", "2026-10-28 09:25")
            self.assertEqual(code, 0, out)
            code, out = run(ticket, "--now", "2026-10-28 09:25", "show")
            self.assertIn("PAPER", out)
            code_word = out.split("code ")[-1].strip()

            self.assertEqual(run(ticket, "--now", "2026-10-28 09:25", "place", order["id"], "--confirm", "WRONG1")[0], 1)
            self.assertEqual(run(ticket, "--now", "2026-10-28 09:35", "place", order["id"], "--confirm", code_word)[0], 1)  # stale
            code, out = run(ticket, "--now", "2026-10-28 09:26", "place", order["id"], "--confirm", code_word, "--fill", "504.15")
            self.assertEqual(code, 0, out)
            self.assertEqual(run(ticket, "--now", "2026-10-28 09:26", "place", order["id"], "--confirm", code_word)[0], 1)  # twice

            led = ws.read("state/ledger.json")
            pos = led["trades"][0]
            self.assertEqual((pos["status"], pos["qty"], pos["entry_price"], pos["paper"]), ("open", 19, 504.15, True))
            self.assertEqual(run(ticket, "--now", "2026-10-28 15:11", "close", pos["id"], "--price", "519.5", "--reason", "time")[0], 0)
            closed = ws.read("state/ledger.json")["trades"][0]
            self.assertGreater(closed["net"], 0)
            code, out = run(journal, "day", "--date", "2026-10-28")
            self.assertIn("1 trades, 1 wins", out)

    def test_risk_blocks(self):
        with Workspace() as ws:
            build_market(ws)
            run(scan, "sip", "--now", "2026-10-28 09:21")
            run(entry, "check", "UPTREND", "--price", "504.10", "--now", "2026-10-28 09:24")
            run(plan, "UPTREND")
            run(size, "--now", "2026-10-28 09:24")
            code, out = run(risk, "--now", "2026-10-28 14:45", "--no-write")
            self.assertEqual(code, 1)
            self.assertIn("window", out)
            code, out = run(risk, "--now", "2026-10-28 09:25", "--no-write")
            self.assertIn("margin not checked", out)
            ws.write("state/ledger.json", {"trades": [{"id": "x", "date": "2026-10-28", "symbol": "SBIN", "side": "LONG", "qty": 10,
                                                       "entry_price": 800, "stop": 790, "status": "closed", "net": -1480}]})
            code, out = run(risk, "--now", "2026-10-28 09:25", "--no-write")
            self.assertIn("daily loss", out)
            ws.write("events.json", {"date": "2026-10-28", "avoid_today": {"UPTREND": "results today"}})
            code, out = run(risk, "--now", "2026-10-28 09:25", "--no-write")
            self.assertIn("results today", out)

    def test_exit_is_never_blocked_by_limits(self):
        with Workspace() as ws:
            ws.write("state/ledger.json", {"trades": [{"id": "x", "date": "2026-10-28", "symbol": "SBIN", "side": "LONG",
                                                       "qty": 10, "entry_price": 800, "stop": 790, "status": "closed", "net": -5000}]})
            ws.write("orders.json", {"orders": [{"id": "EXIT-1", "kind": "exit", "date": "2026-10-28", "symbol": "SBIN",
                                                 "exchange": "NSE", "transaction_type": "SELL", "order_type": "MARKET",
                                                 "market_protection": -1, "quantity": 10, "product": "MIS", "validity": "DAY"}]})
            code, out = run(risk, "--now", "2026-10-28 15:12", "--no-write")
            self.assertEqual(code, 0, out)

    def test_replay_trades_the_day(self):
        with Workspace() as ws:
            build_market(ws)
            code, out = run(replay, "--json", "--seed", "7", "--boot", "500")
            r = ws.read("replay.json")
            got = {(t["symbol"], t["side"], t["reason"]) for t in r["trades"]}
            self.assertEqual(got, {("UPTREND", "LONG", "time"), ("FAKEOUT", "LONG", "stop"), ("REDDOWN", "SHORT", "time")})
            fake = next(t for t in r["trades"] if t["symbol"] == "FAKEOUT")
            self.assertLess(fake["net"], 0)
            self.assertEqual(r["stats"]["trades"], 3)
            again = (run(replay, "--json", "--seed", "7", "--boot", "500"), ws.read("replay.json")["stats"])
            self.assertEqual(again[1], r["stats"])                                     # same seed, same answer

    def test_briefing(self):
        with Workspace():
            code, out = run(briefing, "--now", "2026-11-10 08:45")
            self.assertEqual(code, 1)
            self.assertIn("Diwali Balipratipada", out)
            code, out = run(briefing, "--now", "2026-10-27 08:45")
            self.assertIn("monthly F&O expiry", out)


if __name__ == "__main__":
    unittest.main()
