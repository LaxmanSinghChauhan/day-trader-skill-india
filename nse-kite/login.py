#!/usr/bin/env python3
"""Your daily Kite Connect login. You type your password and TOTP on Zerodha's own page; this only
exchanges the one-time request_token for today's access token.

  export KITE_API_KEY=...  KITE_API_SECRET=...      # from developers.kite.trade; keep them out of the chat
  login.py open                    # opens Zerodha's login page in your browser
  login.py session REQUEST_TOKEN   # from the redirect URL after you log in → ~/.config/nse-trader/kite.json
  login.py status | logout
The token expires at 6 AM tomorrow. The saved file is readable only by you (0600). Nothing is printed
that could log in as you.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_core import clock  # noqa: E402
from nse_core.kite import API, TOKEN_FILE, Kite, KiteError  # noqa: E402
from nse_core.net import urlopen  # noqa: E402


def mask(text: str) -> str:
    return "**" + text[-2:] if text and len(text) > 2 else "**"


def need(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Set {name} in your shell first (never paste it into the chat).")
    return value


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("open")
    s = sub.add_parser("session")
    s.add_argument("request_token")
    sub.add_parser("status")
    sub.add_parser("logout")
    a = p.parse_args(argv)

    if a.cmd == "open":
        key = need("KITE_API_KEY")
        webbrowser.open(f"https://kite.zerodha.com/connect/login?v=3&api_key={urllib.parse.quote(key)}")
        print("Opened Zerodha's login page. After you log in, copy request_token from the redirect URL and run "
              "`login.py session <request_token>`.")
        return 0
    if a.cmd == "session":
        key, secret = need("KITE_API_KEY"), need("KITE_API_SECRET")
        checksum = hashlib.sha256((key + a.request_token + secret).encode()).hexdigest()
        body = urllib.parse.urlencode({"api_key": key, "request_token": a.request_token, "checksum": checksum}).encode()
        req = urllib.request.Request(API + "/session/token", data=body, method="POST", headers={"X-Kite-Version": "3"})
        try:
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())["data"]
        except Exception as e:
            print(f"Login failed ({e}). The request_token works once and only for a few minutes: log in again.")
            return 1
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"api_key": key, "access_token": data["access_token"], "user": mask(data.get("user_id", "")),
                       "saved_at": clock.now_ist().isoformat(timespec="seconds")}, f)
        print(f"Session saved for user {mask(data.get('user_id', ''))}; valid until 06:00 tomorrow.")
        return 0
    if a.cmd == "status":
        try:
            prof = Kite().profile()
            print(f"Logged in: user {mask(prof.get('user_id', ''))}, broker {prof.get('broker', '?')}.")
            return 0
        except KiteError as e:
            print(e)
            return 1
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
    print("Local session removed (the token also expires by itself at 06:00).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
