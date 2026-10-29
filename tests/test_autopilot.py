"""The autopilot's day-loop must trade exactly what the replay says, on the same bars, to the paisa."""
import contextlib
import io
import json
import unittest

from _util import Workspace, load_script
from test_pipeline import DAY, build_market

autopilot = load_script("nse-autopilot/autopilot.py")
replay = load_script("nse-replay/replay.py")


def run(mod, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = mod.main(list(argv))
    return code, out.getvalue()


class Autopilot(unittest.TestCase):
    def test_simulated_day_matches_the_replay(self):
        with Workspace() as ws:
            build_market(ws)
            run(replay, "--no-write", "--json")
            code, out = run(replay, "--json", "--boot", "200")
            expected = {(t["symbol"], t["side"], t["entry"], t["exit"], t["reason"], t["net"]) for t in ws.read("replay.json")["trades"]}
            code, out = run(autopilot, "simulate", "--date", DAY.isoformat())
            self.assertEqual(code, 0, out)
            led = ws.read("state/sim-ledger.json")
            got = {(t["symbol"], t["side"], t["entry_price"], t["exit_price"], t["exit_reason"], t["net"]) for t in led["trades"]}
            self.assertEqual(got, expected)
            self.assertEqual(len(got), 3)
            self.assertTrue(all(t["paper"] and t["auto"] for t in led["trades"]))
            self.assertFalse((ws.path / "state/ledger.json").exists())                 # the real paper ledger is untouched
            self.assertFalse((ws.path / "state/autopilot.json").exists())              # and so is the live day's state
            self.assertFalse((ws.path / "watchlist.json").exists())
            report = ws.read(f"reports/sim-autopilot-{DAY.isoformat()}.json")
            self.assertEqual(report["trades"], 3)
            self.assertIn("scan: 5 scanned", "\n".join(report["log"]))

    def test_risk_limits_still_apply(self):
        with Workspace() as ws:
            build_market(ws)
            ws.write("config.json", {"max_open_positions": 1})
            run(autopilot, "simulate", "--date", DAY.isoformat())
            led = ws.read("state/sim-ledger.json")
            self.assertEqual(len(led["trades"]), 1)          # all three trigger in the 09:25 bar; one may be open
            report = ws.read(f"reports/sim-autopilot-{DAY.isoformat()}.json")
            blocked = [why for why in report["not_traded"].values() if "risk BLOCK" in why]
            self.assertEqual(len(blocked), 2)
            self.assertIn("positions", blocked[0])

    def test_closed_day_does_nothing(self):
        with Workspace() as ws:
            build_market(ws)
            code, out = run(autopilot, "simulate", "--date", "2026-10-20")              # Dussehra
            self.assertIn("NSE is closed", out)

    def test_stays_on_paper_even_if_config_says_live(self):
        with Workspace() as ws:
            build_market(ws)
            ws.write("config.json", {"paper": False})
            code, out = run(autopilot, "simulate", "--date", DAY.isoformat())
            self.assertIn("paper only", out)
            self.assertTrue(all(t["paper"] for t in ws.read("state/sim-ledger.json")["trades"]))


if __name__ == "__main__":
    unittest.main()
