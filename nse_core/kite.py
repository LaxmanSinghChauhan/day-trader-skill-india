"""A small Zerodha Kite Connect v3 REST client (standard library only).

Credentials are read from the environment (KITE_API_KEY, KITE_ACCESS_TOKEN) or from
~/.config/nse-trader/kite.json (mode 0600, written by nse-kite/login.py). They are never printed.

Facts this relies on (Kite docs and Zerodha support, checked Oct 2026):
- Every call sends "X-Kite-Version: 3" and "Authorization: token api_key:access_token".
- The access token expires at 6 AM the next day; you log in once a day, yourself.
- Orders work on the free Personal app; quotes, historical candles and WebSocket need the paid Connect app.
- From 1 Apr 2026 orders are rejected unless they come from a static IP registered in your Kite
  developer profile (up to 2 IPs, one change per calendar week). Read calls work from any IP.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .net import urlopen
from pathlib import Path

API = "https://api.kite.trade"
TOKEN_FILE = Path.home() / ".config" / "nse-trader" / "kite.json"


class KiteError(RuntimeError):
    pass


def credentials() -> tuple[str, str]:
    key, token = os.environ.get("KITE_API_KEY"), os.environ.get("KITE_ACCESS_TOKEN")
    if (not key or not token) and TOKEN_FILE.exists():
        saved = json.loads(TOKEN_FILE.read_text())
        key, token = key or saved.get("api_key"), token or saved.get("access_token")
    if not key or not token:
        raise KiteError("No Kite session: run nse-kite/login.py (or set KITE_API_KEY and KITE_ACCESS_TOKEN)")
    return key, token


class Kite:
    def __init__(self, api_key: str | None = None, access_token: str | None = None, timeout: float = 10):
        if api_key is None or access_token is None:
            api_key, access_token = credentials()
        self._auth = f"token {api_key}:{access_token}"
        self.timeout = timeout

    def _call(self, method: str, path: str, params: dict | None = None, raw: bool = False):
        url = API + path
        data = None
        if params and method == "GET":
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        elif params:
            data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"X-Kite-Version": "3", "Authorization": self._auth})
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("message", "")
            except Exception:
                msg = ""
            hint = " (session expired: log in again)" if e.code == 403 else ""
            raise KiteError(f"Kite {method} {path}: HTTP {e.code} {msg}{hint}") from None
        except urllib.error.URLError as e:
            raise KiteError(f"Kite {method} {path}: {e.reason}") from None
        if raw:
            return body.decode()
        payload = json.loads(body)
        if payload.get("status") != "success":
            raise KiteError(f"Kite {method} {path}: {payload.get('message', 'error')}")
        return payload["data"]

    # read-only (any IP)
    def profile(self):
        return self._call("GET", "/user/profile")

    def margins(self):
        return self._call("GET", "/user/margins/equity")

    def positions(self):
        return self._call("GET", "/portfolio/positions")

    def orders(self):
        return self._call("GET", "/orders")

    def order_history(self, order_id: str):
        return self._call("GET", f"/orders/{order_id}")

    def instruments(self, exchange: str = "NSE") -> str:
        return self._call("GET", f"/instruments/{exchange}", raw=True)

    def quote(self, symbols: list[str]):          # Connect app
        return self._call("GET", "/quote", {"i": symbols})

    def historical(self, token: int, interval: str, start: str, end: str):   # Connect app
        return self._call("GET", f"/instruments/historical/{token}/{interval}", {"from": start, "to": end})["candles"]

    # orders (static IP)
    def place_order(self, **order) -> str:
        return self._call("POST", "/orders/regular", order)["order_id"]

    def cancel_order(self, order_id: str) -> str:
        return self._call("DELETE", f"/orders/regular/{order_id}")["order_id"]
