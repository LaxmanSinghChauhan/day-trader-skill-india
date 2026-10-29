#!/usr/bin/env python3
"""Corporate announcements and event windows for today: tag them, and tell nse-risk what to avoid.

  events.py add LT "Outcome of board meeting: financial results" [--time "2026-10-29 08:10"] [--url URL]
  events.py classify [--now "2026-10-29 08:50"]       # → intraday/events.json (avoid list + flags)
  events.py window --from "2026-12-04 09:55" --to "2026-12-04 10:20" --why "RBI policy"
  events.py show
Claude collects the announcements from NSE/BSE pages (see SKILL.md) and adds them; this script only
classifies text by keywords, so a human-readable reason is always kept with each tag.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import clock, state  # noqa: E402

TAGS = {
    "results": r"financial results|quarterly results|results for the (quarter|half|year)|\baudited\b|\bunaudited\b",
    "board_meeting": r"board meeting|meeting of the board",
    "dividend": r"dividend",
    "split_bonus": r"sub-?division|stock split|split of|bonus",
    "fund_raise": r"\bqip\b|preferential|rights issue|fund ?raising|\bncds?\b|warrants",
    "order_win": r"\border(s)? (win|received|worth)|bags|letter of award|\bloa\b|contract",
    "pledge": r"pledge|encumbrance",
    "rating": r"credit rating|rating (upgrade|downgrade|reaffirm)",
    "regulatory": r"\bsebi\b.*(order|notice)|show cause|penalt|search|raid|tax demand|gst demand|\bnclt\b|insolvency|fraud",
    "management": r"resign|appointment of|\bceo\b|\bcfo\b|managing director",
    "merger": r"merger|amalgamation|acquisition|demerger|scheme of arrangement",
    "deals": r"block deal|bulk deal",
}
AVOID = {"results": "results today", "board_meeting": "board meeting today", "merger": "merger or acquisition news",
         "regulatory": "regulatory action news", "fund_raise": "fund raising news"}


def tag(title: str) -> list[str]:
    t = title.lower()
    return [name for name, rx in TAGS.items() if re.search(rx, t)] or ["other"]


def load() -> dict:
    return state.read_json("announcements.json", {"items": []})


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--now")
    sub = p.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add")
    ad.add_argument("symbol")
    ad.add_argument("title")
    ad.add_argument("--time")
    ad.add_argument("--url")
    ad.add_argument("--source", default="NSE")
    sub.add_parser("classify")
    w = sub.add_parser("window")
    w.add_argument("--from", dest="start", required=True)
    w.add_argument("--to", dest="end", required=True)
    w.add_argument("--why", required=True)
    sub.add_parser("show")
    a = p.parse_args(argv)
    now = clock.parse_now(a.now)

    if a.cmd == "add":
        data = load()
        when = clock.parse_now(a.time) if a.time else now
        data["items"].append({"symbol": a.symbol.upper(), "title": a.title, "time": when.isoformat(timespec="minutes"),
                              "url": a.url, "source": a.source, "tags": tag(a.title)})
        state.write_json("announcements.json", data)
        print(f"Added {a.symbol.upper()}: {', '.join(tag(a.title))}")
        return 0

    events = state.read_json("events.json", {}) or {}
    if events.get("date") != now.date().isoformat():
        events = {"date": now.date().isoformat(), "event_windows": [w for w in events.get("event_windows", [])
                                                                     if w["to"][:10] >= now.date().isoformat()]}
    if a.cmd == "window":
        clock.parse_now(a.start), clock.parse_now(a.end)          # validates both
        events.setdefault("event_windows", []).append({"from": a.start, "to": a.end, "why": a.why})
        state.write_json("events.json", events)
        print(f"Event window {a.start} → {a.end}: {a.why}. nse-risk blocks new entries inside it.")
        return 0

    if a.cmd == "classify":
        since = now - timedelta(hours=18)
        avoid, flags = {}, {}
        for item in load()["items"]:
            if clock.parse_now(item["time"][:16].replace("T", " ")) < since:
                continue
            tags = tag(item["title"])
            flags[item["symbol"]] = sorted(set(flags.get(item["symbol"], [])) | set(tags))
            for t in tags:
                if t in AVOID and item["symbol"] not in avoid:
                    avoid[item["symbol"]] = AVOID[t]
        events.update({"avoid_today": avoid, "flags": flags, "classified_at": now.isoformat(timespec="minutes")})
        state.write_json("events.json", events)

    print(json.dumps({k: v for k, v in events.items()}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
