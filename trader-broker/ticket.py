#!/usr/bin/env python3
"""Order tickets and the decision log for trader-broker (India). Standard library only.

This tool never talks to a broker and never places anything. It does its
work around the one moment that matters, your yes:

  show      renders each proposed order as a plain-English ticket plus the
            exact JSON Claude will send to Zerodha's place_order tool (Kite
            MCP). NSE has no single bracket order for an intraday (MIS)
            trade, so a bracket shows its legs: the entry, the stop-loss
            order that goes to the exchange right after the fill, and the
            take-profit as an alert. An order is READY only if trader-risk
            passed THIS exact order today (matched by fingerprint) and nobody
            has decided on it yet.
  approve   records your explicit yes for ONE order, with your reply word for
            word. It refuses "yes to all", "sure", "ok", a yes that names a
            different stock or amount, and any order that is not READY.
  decline   records a no.
  paper     PAPER account only: records the simulated fill after your yes.
            Nothing goes to a broker. Zerodha has no paper account, so the
            paper trade lives in trader/state/broker.json and trader/portfolio.json.
  result    LIVE account: records what happened after the Allow once / Deny
            card: placed (with the broker's order id), denied, or failed.
  fill      records a fill in trader/portfolio.json (cash and shares).
  flatten   builds a sell ticket that closes a symbol's open position by
            flat_by. It still goes through trader-risk and your yes.
  log       prints today's decisions.

    python3 ticket.py show                    # every order, READY or not
    python3 ticket.py show --index 1 --json   # one ticket as JSON
    python3 ticket.py approve --index 1 --reply "yes"
    python3 ticket.py paper --index 1 --price 1343.10     # paper: the simulated fill
    python3 ticket.py result --index 1 --status placed --broker-id 2611110001234
    python3 ticket.py fill --symbol RELIANCE --side sell --qty 27 --price 1349.90
    python3 ticket.py flatten --symbol RELIANCE --qty 27 --price 1346.00
    python3 ticket.py log

A market order goes to Kite as a LIMIT order a little through the price
("limit_buffer_pct" in the config, default 0.10 %), on the tick grid: Kite's
API wants price protection on market orders, and a limit caps the slippage.

Everything is written to trader/state/broker.json (append only). Dates are
India dates; --now "2026-11-11 10:00" pins the clock.
"""

import argparse
import datetime
import hashlib
import json
import math
import os
import re
import sys

ORDER_FIELDS = ("symbol", "exchange", "product", "side", "qty", "notional", "type", "time_in_force", "limit_price",
                "stop_price", "trail_price", "trail_percent", "extended_hours", "client_order_id",
                "order_class", "take_profit_limit_price", "stop_loss_stop_price",
                "stop_loss_limit_price", "advanced_instructions")
STRING_FIELDS = ("qty", "notional", "limit_price", "stop_price", "trail_price", "trail_percent",
                 "take_profit_limit_price", "stop_loss_stop_price", "stop_loss_limit_price")
TIF_WORDS = {"day": "good for today", "ioc": "immediate or cancel"}
KITE_TOOL = "place_order"           # Zerodha's Kite MCP server (github.com/zerodha/kite-mcp-server)
KITE_VALIDITY = {"day": "DAY", "ioc": "IOC"}
LIMIT_BUFFER_PCT = 0.10             # how far through the price a "market" order's limit is set
TAG = "daytraderskill"              # Kite order tag (20 characters at most)
TICKS_PAISE = (500, 100, 50, 10, 5, 1)   # NSE cash-market tick sizes, in paise
YES_WORDS = ("yes", "y")
BATCH_WORDS = {"all", "every", "everything", "rest", "remaining", "them", "both", "batch", "each"}
DOUBT_WORDS = {"no", "not", "dont", "don't", "wait", "cancel", "stop", "but", "maybe", "later",
               "hold", "unless", "if"}


class TicketError(Exception):
    pass


# ---------------------------------------------------------------- time (India, no tz files)

IST_OFFSET = datetime.timedelta(hours=5, minutes=30)   # India has one time zone and no daylight saving


def to_ist(utc):
    return utc.replace(tzinfo=None) + IST_OFFSET


def ist_to_utc(local):
    return local - IST_OFFSET


def ts_to_ist(ts):
    """Unix seconds -> naive India time (IST). Never uses the machine's time zone."""
    return to_ist(datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=int(ts)))


def parse_now(text):
    """ISO time -> naive UTC. A time without an offset is taken as India time (IST)."""
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise TicketError("--now wants a time like \"2026-11-11 10:00\" (India time) or ...Z (UTC)")
    if dt.tzinfo is None:
        return ist_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def ist_iso(now_utc):
    """naive UTC -> "2026-11-11T10:00:00+05:30" (India wall clock with its offset)."""
    return "%s+05:30" % to_ist(now_utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- files

def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise TicketError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise TicketError("%s is not valid JSON: %s" % (path, e))


def write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def rec_day(rec):
    """The trading day a decision belongs to: its "date" (the day it was made under), else the day of "at"."""
    return str(rec.get("date") or str(rec.get("at", ""))[:10])


# ---------------------------------------------------------------- the order

def fingerprint(order):
    """Same function as trader-risk/check.py: identifies the exact order."""
    core = {k: order[k] for k in ORDER_FIELDS if k in order and order[k] is not None}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _str_num(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f == int(f) else repr(f)
    return str(v)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def tool_input(order):
    """The order's own fields as they sit in trader/orders.json, numbers as strings.
    "why" and "plan" are ours and never leave the machine. The broker's arguments
    are built from these by kite_entry() and kite_stop()."""
    out = {}
    for k in ORDER_FIELDS:
        if k in order and order[k] is not None:
            out[k] = _str_num(order[k]) if k in STRING_FIELDS else order[k]
    return out


def tick_paise(order):
    """The tick this order's prices sit on, in paise: NSE's slab for the price (under 250 -> 1,
    to 1,000 -> 5, to 5,000 -> 10, to 10,000 -> 50, to 20,000 -> 100, above -> 500), stepped
    down to the largest standard tick that the order's own prices already sit on."""
    plan = order.get("plan") or {}
    prices = [p for p in (_f(order.get("limit_price")), _f(plan.get("entry")), _f(order.get("stop_loss_stop_price")),
                          _f(order.get("take_profit_limit_price")), _f(order.get("stop_price"))) if p]
    if not prices:
        return 5
    ref = prices[0]
    slab = 500
    for limit, t in ((250, 1), (1000.0001, 5), (5000.0001, 10), (10000.0001, 50), (20000.0001, 100)):
        if ref < limit:
            slab = t
            break
    for t in TICKS_PAISE:
        if t <= slab and all(int(round(p * 100)) % t == 0 for p in prices):
            return t
    return 1


def protected_price(side, ref, pct, tick):
    """A "market" order as a limit: a buy a little above the reference price (rounded up to
    the tick), a sell a little below it (rounded down)."""
    paise = ref * 100.0 * (1 + pct / 100.0) if side == "buy" else ref * 100.0 * (1 - pct / 100.0)
    steps = math.ceil(round(paise / tick, 6)) if side == "buy" else math.floor(round(paise / tick, 6))
    return steps * tick / 100.0


def kite_entry(order, cfg=None):
    """(arguments for Kite's place_order, note). The first leg of a bracket, or the whole
    order when it is not one. Kite types quantity and prices as numbers."""
    cfg = cfg or {}
    side = str(order.get("side", "")).lower()
    typ = str(order.get("type", "market")).lower()
    plan = order.get("plan") or {}
    args = {"variety": "regular", "exchange": str(order.get("exchange") or cfg.get("exchange") or "NSE").upper(),
            "tradingsymbol": str(order.get("symbol", "")).upper(), "transaction_type": side.upper(),
            "quantity": int(float(order.get("qty") or 0)),
            "product": str(order.get("product") or cfg.get("product") or "MIS").upper()}
    note = ""
    tif = KITE_VALIDITY.get(str(order.get("time_in_force", "day")).lower(), "DAY")
    if typ == "limit":
        args.update(order_type="LIMIT", price=round(_f(order.get("limit_price")), 2))
    elif typ == "stop":
        args.update(order_type="SL-M", trigger_price=round(_f(order.get("stop_price")), 2))
    elif typ == "stop_limit":
        args.update(order_type="SL", trigger_price=round(_f(order.get("stop_price")), 2),
                    price=round(_f(order.get("limit_price")), 2))
    else:
        ref = _f(plan.get("entry")) or _f(order.get("ref_price"))
        pct = _f(cfg.get("limit_buffer_pct"))
        pct = LIMIT_BUFFER_PCT if pct is None else pct
        if ref:
            px = protected_price(side, ref, pct, tick_paise(order))
            args.update(order_type="LIMIT", price=round(px, 2))
            note = ("a market order goes to Kite as a limit at %s, %s%% %s %s: Kite's API wants price "
                    "protection, and the limit caps the slippage. If the price has run past it, it will not fill"
                    % (_p(px), _pct(pct), "above" if side == "buy" else "below", _p(ref)))
        else:
            args.update(order_type="MARKET")
            note = ("a plain MARKET order: there is no reference price to set a protective limit from. Kite's "
                    "API can reject it; if it does, give a price (ticket.py flatten --price LAST)")
    args["validity"] = tif
    args["tag"] = TAG
    return args, note


def kite_stop(order, cfg=None):
    """Arguments for the protective stop-loss order of a bracket (placed after the entry fills),
    or None when the order has no stop leg."""
    cfg = cfg or {}
    if order.get("stop_loss_stop_price") is None:
        return None
    side = "SELL" if str(order.get("side", "")).lower() == "buy" else "BUY"
    args = {"variety": "regular", "exchange": str(order.get("exchange") or cfg.get("exchange") or "NSE").upper(),
            "tradingsymbol": str(order.get("symbol", "")).upper(), "transaction_type": side,
            "quantity": int(float(order.get("qty") or 0)),
            "product": str(order.get("product") or cfg.get("product") or "MIS").upper()}
    if order.get("stop_loss_limit_price") is not None:
        args.update(order_type="SL", trigger_price=round(_f(order["stop_loss_stop_price"]), 2),
                    price=round(_f(order["stop_loss_limit_price"]), 2))
    else:
        args.update(order_type="SL-M", trigger_price=round(_f(order["stop_loss_stop_price"]), 2))
    args["validity"] = "DAY"
    args["tag"] = TAG
    return args


def _pct(x):
    s = "%.2f" % float(x)
    return s.rstrip("0").rstrip(".") if "." in s else s


def _group(digits):
    """Indian digit grouping: '1234567' -> '12,34,567' (thousands, then lakhs and crores in twos)."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def _money(v):
    """Rupees with Indian grouping; whole rupees drop the paise."""
    f = float(v)
    whole, frac = ("%.2f" % abs(f)).split(".")
    return ("-" if f < -0.005 else "") + "₹" + _group(whole) + ("" if frac == "00" else "." + frac)


def _p(v):
    return "%.2f" % float(v)


def is_bracket(order):
    oc = str(order.get("order_class") or "").lower()
    legs = order.get("take_profit_limit_price") is not None or order.get("stop_loss_stop_price") is not None
    return oc == "bracket" or (not oc and legs)


def max_loss(order):
    """(rupees, stop) lost if the stop fills exactly at the stop, or (None, stop). Charges are extra."""
    stop = _f(order.get("stop_loss_stop_price")) or _f((order.get("plan") or {}).get("stop"))
    q = _f(order.get("qty"))
    if not stop or not q:
        return None, stop
    plan = order.get("plan") or {}
    if str(order.get("type", "market")) == "limit" and _f(order.get("limit_price")):
        entry = _f(order["limit_price"])
    elif _f(plan.get("max_loss")) is not None:
        return round(_f(plan["max_loss"]), 2), stop
    else:
        entry = _f(plan.get("entry"))
    if not entry:
        return None, stop
    risk = abs(entry - stop)
    return round(q * int(round(risk * 100)) / 100.0, 2), stop


def plain_parts(order):
    """The ticket in plain words, one part per line."""
    side = str(order.get("side", "")).upper()
    sym = order.get("symbol", "?")
    typ = str(order.get("type", "market"))
    tif = TIF_WORDS.get(str(order.get("time_in_force", "day")), order.get("time_in_force"))
    if is_bracket(order):
        how = "limit %s" % _p(order["limit_price"]) if typ == "limit" and order.get("limit_price") else typ
        parts = ["%s %s %s, %s, %s" % (side, _str_num(order.get("qty")), sym, how, tif)]
        if order.get("stop_loss_stop_price") is not None:
            leg = "stop-loss %s" % _p(order["stop_loss_stop_price"])
            if order.get("stop_loss_limit_price") is not None:
                leg += " (limit %s)" % _p(order["stop_loss_limit_price"])
            parts.append(leg)
        if order.get("take_profit_limit_price") is not None:
            parts.append("take-profit %s" % _p(order["take_profit_limit_price"]))
        loss, stop = max_loss(order)
        if loss is not None:
            parts.append("max loss about %s if the stop fills at %s (it can fill worse in a fast market)"
                         % (_money(loss), _p(stop)))
        return parts
    if order.get("notional") is not None:
        what = "%s of %s" % (_money(order["notional"]), sym)
    else:
        q = _str_num(order.get("qty"))
        what = "%s share%s of %s" % (q, "" if q == "1" else "s", sym)
    if typ == "limit":
        how = "limit order at %s" % _money(order.get("limit_price"))
    elif typ == "stop":
        how = "stop order at %s" % _money(order.get("stop_price"))
    elif typ == "stop_limit":
        how = "stop %s, limit %s" % (_money(order.get("stop_price")), _money(order.get("limit_price")))
    else:
        how = "%s order" % typ.replace("_", " ")
    return ["%s %s, %s, %s" % (side, what, how, tif)]


def plain(order):
    """SELL 27 shares of RELIANCE, market order, good for today
    BUY 27 RELIANCE, market, good for today / stop-loss 1335.70 / take-profit 1349.90 / max loss about 191.70 ..."""
    return " / ".join(plain_parts(order))


def amount_numbers(order):
    nums = []
    for k in ("notional", "qty", "limit_price", "stop_loss_stop_price", "take_profit_limit_price",
              "stop_loss_limit_price"):
        if order.get(k) is not None:
            v = _f(order[k])
            if v is not None:
                nums.append(v)
    loss, _ = max_loss(order)
    if loss is not None:
        nums.append(loss)
    return nums


def parse_yes(reply, order, batch_symbols=()):
    """Is this reply an explicit yes for THIS one order? Returns (ok, why)."""
    raw = (reply or "").strip()
    if not raw:
        return False, "the reply is empty"
    if "?" in raw:
        return False, "the reply is a question, not a yes"
    words = re.findall(r"[a-z']+", raw.lower())
    if not words or words[0] not in YES_WORDS:
        return False, "only a reply that starts with \"yes\" counts (not ok, sure, go, do it)"
    if BATCH_WORDS & set(words):
        return False, "a yes covers one order at a time, not a batch"
    if DOUBT_WORDS & set(words[1:]):
        return False, "the reply has a condition or a doubt in it; ask again"
    sym = str(order.get("symbol", "")).upper()
    tokens = set(re.findall(r"[A-Z0-9&][A-Z0-9&.\-]{0,19}", raw.upper()))
    others = {s.upper() for s in batch_symbols} - {sym}
    named = tokens & others
    if named:
        return False, "the reply names %s, but this order is for %s" % (", ".join(sorted(named)), sym)
    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", raw)]
    if nums:
        want = amount_numbers(order)
        if not any(abs(n - w) < 0.005 for n in nums for w in want):
            return False, "the reply says %s, but this order is %s" % (
                ", ".join(_str_num(n) for n in nums), plain(order))
    return True, "explicit yes for %s" % plain(order)


# ---------------------------------------------------------------- state

def load_state(path):
    return read_json(path, "broker state", required=False) or {"orders": []}


def latest(state, fp, today):
    """The latest decision recorded today for this fingerprint, or None."""
    found = None
    for rec in state.get("orders", []):
        if rec.get("fingerprint") == fp and rec_day(rec) == today:
            found = rec
    return found


def risk_verdict(risk, fp, today):
    if not risk:
        return None, "trader-risk has not checked these orders (run check.py)"
    if risk.get("date") != today:
        return None, "the risk check is from %s, not today; run check.py again" % risk.get("date")
    for r in risk.get("results", []):
        if r.get("fingerprint") == fp:
            return r, None
    return None, "this exact order was not in the last risk check (it changed or is new); run check.py again"


def status_of(order, risk, state, today):
    """(ready, label, risk_result)"""
    fp = fingerprint(order)
    rv, why = risk_verdict(risk, fp, today)
    if rv is None:
        return False, "NOT READY: " + why, None
    if rv.get("verdict") != "PASS":
        return False, "BLOCKED by trader-risk: " + "; ".join(rv.get("reasons", [])), rv
    rec = latest(state, fp, today)
    if rec:
        st = rec.get("status")
        if st == "approved":
            return False, "APPROVED by you at %s, waiting for the order to be recorded" % rec.get("at"), rv
        return False, "DONE: %s at %s" % (st, rec.get("at")), rv
    return True, "READY: trader-risk PASS, waiting for your yes", rv


def kind_of(order, rv):
    """entry or exit, as trader-risk saw it (older checks: a buy is an entry)."""
    if rv and rv.get("kind"):
        return rv["kind"]
    return "entry" if str(order.get("side", "")).lower() == "buy" else "exit"


# ---------------------------------------------------------------- rendering

def render(order, idx, total, cfg, risk, state, today):
    ready, label, rv = status_of(order, risk, state, today)
    paper = cfg.get("paper", True)
    acct = "PAPER account" if paper else "LIVE ACCOUNT, REAL MONEY"
    lines = ["ORDER %d of %d, %s, Zerodha (%s %s)" % (
        idx, total, acct, str(order.get("exchange") or cfg.get("exchange") or "NSE").upper(),
        str(order.get("product") or cfg.get("product") or "MIS").upper())]
    for part in plain_parts(order):
        lines.append("  " + part)
    charges = (order.get("plan") or {}).get("charges_at_stop")
    if _f(charges):
        lines.append("  charges about %s on top if the stop fills (Zerodha intraday, an estimate)" % _money(charges))
    if order.get("why"):
        lines.append("  why: " + order["why"])
    lines.append("  " + label)
    for w in (rv or {}).get("warnings", []):
        lines.append("  note: " + w)
    entry, note = kite_entry(order, cfg)
    stop = kite_stop(order, cfg)
    if paper:
        lines.append("  PAPER: nothing goes to a broker. After your yes the fill is recorded here")
        lines.append("  (ticket.py paper), at the latest price you give it or the order's own price.")
        lines.append("  On a live account Claude would call %s with exactly:" % KITE_TOOL)
    else:
        lines.append("  Claude will call %s (Kite MCP) with exactly:" % KITE_TOOL)
    for l in json.dumps(entry, indent=2).splitlines():
        lines.append("    " + l)
    if note:
        lines.append("  note: " + note)
    if stop:
        lines.append("  Then, as soon as the entry fills, the stop-loss order with exactly:")
        for l in json.dumps(stop, indent=2).splitlines():
            lines.append("    " + l)
        lines.append("  That stop sits at the exchange. The take-profit is an alert, not an order: a second")
        lines.append("  sell order could leave you short when the stop fills. trader-alerts rings at the")
        lines.append("  target and at your flat-by time; then ticket.py flatten.")
    if ready:
        lines.append("  Reply \"yes\" to %s this one order, or \"no\" to skip it."
                     % ("paper-trade" if paper else "place"))
        if not paper:
            lines.append("  Claude's own card then asks again for each call: Allow once places it, Deny stops it.")
    return "\n".join(lines), ready


def ticket_json(order, idx, cfg, risk, state, today):
    ready, label, rv = status_of(order, risk, state, today)
    loss, stop = max_loss(order)
    entry, note = kite_entry(order, cfg)
    return {"index": idx, "ready": ready, "status": label, "plain": plain(order),
            "fingerprint": fingerprint(order), "paper": bool(cfg.get("paper", True)),
            "broker": cfg.get("broker", "zerodha"), "tool": KITE_TOOL,
            "tool_input": entry, "tool_note": note, "stop_order": kite_stop(order, cfg),
            "order": tool_input(order), "why": order.get("why", ""),
            "bracket": is_bracket(order), "max_loss": loss, "stop": stop}


# ---------------------------------------------------------------- fills -> portfolio

def leg_charges(side, price, qty):
    """Zerodha's intraday equity charges for ONE filled leg on NSE, in rupees: brokerage (0.03 %,
    20 rupees at most), STT on a sell (0.025 %), exchange and investor-protection fees, SEBI's
    fee, stamp duty on a buy (0.003 %) and 18 % GST on the fees. An estimate (rates read
    18 Oct 2026); the contract note is final."""
    value = float(price) * float(qty)
    brokerage = min(20.0, round(value * 0.0003, 2))
    stt = float(round(value * 0.00025)) if side == "sell" else 0.0
    txn = round(value * 0.0000307, 2)
    sebi = round(value * 0.000001, 2)
    stamp = float(round(value * 0.00003)) if side == "buy" else 0.0
    gst = round(0.18 * (brokerage + txn + sebi), 2)
    return round(brokerage + stt + txn + sebi + stamp + gst, 2)


def apply_fill(portfolio_path, cfg, symbol, side, qty, price, date):
    """Record a filled order in trader/portfolio.json: cash and shares, with a
    cost-basis lot per buy (oldest lots are relieved first on a sell). The leg's charges
    (leg_charges) come out of the cash, so the account shows what the trade really made."""
    pf = read_json(portfolio_path, "portfolio", required=False)
    if pf is None:
        budget = cfg.get("budget")
        if not budget:
            raise TicketError("no %s yet and no budget in the config to start it from" % portfolio_path)
        pf = {"cash": float(budget), "positions": []}
    symbol = symbol.upper()
    qty, price = float(qty), float(price)
    if qty <= 0 or price <= 0:
        raise TicketError("a fill needs a positive qty and price")
    cost = round(qty * price, 2)
    fee = leg_charges(side, price, qty)
    pos = None
    for p in pf.setdefault("positions", []):
        if str(p.get("ticker", "")).upper() == symbol:
            pos = p
    if side == "buy":
        if pos is None:
            pos = {"ticker": symbol, "shares": 0.0, "lots": []}
            pf["positions"].append(pos)
        lots = pos.setdefault("lots", [])
        lots.append({"id": "%s-%d" % (symbol, len(lots) + 1), "date": date, "shares": qty, "cost": cost})
        pos["shares"] = round(float(pos.get("shares", 0)) + qty, 6)
        pf["cash"] = round(float(pf.get("cash", 0)) - cost - fee, 2)
    else:
        if pos is None or float(pos.get("shares", 0)) + 1e-9 < qty:
            raise TicketError("cannot record selling %s %s: the portfolio holds %s"
                              % (_str_num(qty), symbol, pos.get("shares", 0) if pos else 0))
        left = qty
        for lot in sorted(pos.get("lots", []), key=lambda l: l.get("date", "")):
            if left <= 1e-9:
                break
            take = min(left, float(lot["shares"]))
            per = float(lot["cost"]) / float(lot["shares"]) if float(lot["shares"]) else 0
            lot["cost"] = round(float(lot["cost"]) - per * take, 2)
            lot["shares"] = round(float(lot["shares"]) - take, 6)
            left -= take
        pos["lots"] = [l for l in pos.get("lots", []) if float(l["shares"]) > 1e-9]
        pos["shares"] = round(float(pos["shares"]) - qty, 6)
        if pos["shares"] <= 1e-9:
            pf["positions"].remove(pos)
        pf["cash"] = round(float(pf.get("cash", 0)) + cost - fee, 2)
    pf["charges_paid"] = round(float(pf.get("charges_paid", 0)) + fee, 2)
    pf["last_charges"] = fee
    write_json(portfolio_path, pf)
    return pf


def log_fill(state_path, now, today, symbol, side, qty, price):
    """A fill in the log, so trader-risk can count day trades (a buy and a sell the same day)."""
    state = load_state(state_path)
    state.setdefault("orders", []).append({
        "at": ist_iso(now), "date": today, "status": "filled", "symbol": symbol.upper(), "side": side,
        "qty": _str_num(float(qty)), "price": float(price),
        "plain": "%s %s %s at %s" % (side.upper(), _str_num(float(qty)), symbol.upper(), _p(price))})
    write_json(state_path, state)


# ---------------------------------------------------------------- commands

def _clock(a):
    now = parse_now(getattr(a, "now", None))
    today = getattr(a, "today", None) or to_ist(now).date().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        raise TicketError("--today wants a date like 2026-11-11")
    return now, today


def _load(a):
    doc = read_json(a.orders, "orders file (run trader-budget, or ticket.py flatten, first)")
    orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
    if not isinstance(orders, list) or not orders:
        raise TicketError("no orders in %s" % a.orders)
    cfg = read_json(a.config, "config", required=False) or {}
    risk = read_json(a.risk, "risk check", required=False)
    state = load_state(a.state)
    now, today = _clock(a)
    return orders, cfg, risk, state, today, now


def _pick(orders, index):
    if index is None:
        raise TicketError("say which order: --index N")
    if not 1 <= index <= len(orders):
        raise TicketError("there is no order %d (there are %d)" % (index, len(orders)))
    return orders[index - 1]


def cmd_show(a):
    orders, cfg, risk, state, today, now = _load(a)
    picks = [(a.index, _pick(orders, a.index))] if a.index else list(enumerate(orders, 1))
    if a.json:
        out = [ticket_json(o, i, cfg, risk, state, today) for i, o in picks]
        print(json.dumps(out[0] if a.index else out, indent=2))
        return 0 if any(t["ready"] for t in out) else 1
    blocks, any_ready = [], False
    for i, o in picks:
        text, ready = render(o, i, len(orders), cfg, risk, state, today)
        blocks.append(text)
        any_ready = any_ready or ready
    print("\n\n".join(blocks))
    print("\nOne order at a time: a yes covers one ticket, never the batch. Education and tooling, "
          "not financial advice.")
    return 0 if any_ready else 1


def cmd_approve(a):
    orders, cfg, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    ready, label, rv = status_of(order, risk, state, today)
    if not ready:
        raise TicketError("order %d is not ready: %s" % (a.index, label))
    ok, why = parse_yes(a.reply, order, [o.get("symbol", "") for o in orders])
    if not ok:
        print("Not recorded: %s. Ask the user again with the ticket for order %d." % (why, a.index))
        return 1
    loss, stop = max_loss(order)
    rec = {"at": ist_iso(now), "date": today, "index": a.index, "fingerprint": fingerprint(order),
           "symbol": str(order.get("symbol", "")).upper(), "side": order.get("side"),
           "qty": order.get("qty"), "kind": kind_of(order, rv), "max_loss": loss, "stop": stop,
           "plain": plain(order), "status": "approved", "reply": a.reply,
           "paper": bool(cfg.get("paper", True)), "broker": cfg.get("broker", "zerodha")}
    state.setdefault("orders", []).append(rec)
    write_json(a.state, state)
    print("Recorded your yes for order %d: %s." % (a.index, plain(order)))
    entry, note = kite_entry(order, cfg)
    stop = kite_stop(order, cfg)
    if cfg.get("paper", True):
        print("PAPER account: nothing goes to a broker. Get a fresh price (trader-alerts: alerts.py quote %s)"
              % rec["symbol"])
        print("and record the simulated fill: ticket.py paper --index %d --price LAST" % a.index)
        return 0
    print("Now call %s (Kite MCP) with exactly:" % KITE_TOOL)
    print(json.dumps(entry, indent=2))
    if note:
        print("Note: " + note + ".")
    print("Claude's card shows Allow once / Deny. Then: ticket.py result --index %d --status "
          "placed|denied|failed" % a.index)
    if stop:
        print("As soon as the entry fills (get_orders), place the stop-loss with exactly:")
        print(json.dumps(stop, indent=2))
        print("If the entry did not fill, do not place the stop: a sell with no shares would open a short.")
    return 0


def cmd_decline(a):
    orders, cfg, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    rec = {"at": ist_iso(now), "date": today, "index": a.index, "fingerprint": fingerprint(order),
           "symbol": str(order.get("symbol", "")).upper(), "side": order.get("side"),
           "plain": plain(order), "status": "declined", "reply": a.reply or "no"}
    state.setdefault("orders", []).append(rec)
    write_json(a.state, state)
    print("Recorded: you said no to order %d (%s). Nothing was sent." % (a.index, plain(order)))
    return 0


def cmd_result(a):
    orders, cfg, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    fp = fingerprint(order)
    rec = latest(state, fp, today)
    if not rec or rec.get("status") != "approved":
        raise TicketError("order %d has no yes recorded today; a result can only follow an approval" % a.index)
    new = {"at": ist_iso(now), "date": today, "index": a.index, "fingerprint": fp, "symbol": rec["symbol"],
           "side": rec["side"], "plain": rec["plain"], "status": a.status}
    for k in ("qty", "kind", "max_loss", "stop"):
        if rec.get(k) is not None:
            new[k] = rec[k]
    if a.broker_id:
        new["broker_order_id"] = a.broker_id
    if a.note:
        new["note"] = a.note
    state["orders"].append(new)
    write_json(a.state, state)
    print("Recorded order %d as %s." % (a.index, a.status))
    if a.status == "placed" and a.filled_qty and a.filled_price:
        apply_fill(a.portfolio, cfg, rec["symbol"], rec["side"], a.filled_qty, a.filled_price, today)
        log_fill(a.state, now, today, rec["symbol"], rec["side"], a.filled_qty, a.filled_price)
        pf = read_json(a.portfolio, "portfolio", required=False) or {}
        print("Added the fill to %s (charges about %s taken from the cash)."
              % (a.portfolio, _money(pf.get("last_charges", 0))))
    elif a.status == "placed":
        print("When it fills, record it: ticket.py fill --symbol %s --side %s --qty Q --price P"
              % (rec["symbol"], rec["side"]))
        if rec.get("kind") == "entry" and is_bracket(order):
            print("When the stop-loss fills later, or you sell at the target, record that sell the same way.")
    return 0


def cmd_paper(a):
    """PAPER account: record the simulated fill of an approved order. No broker is involved."""
    orders, cfg, risk, state, today, now = _load(a)
    if not cfg.get("paper", True):
        raise TicketError("this is a LIVE account (\"paper\": false): place the order with %s, then record it "
                          "with ticket.py result" % KITE_TOOL)
    order = _pick(orders, a.index)
    rec = latest(state, fingerprint(order), today)
    if not rec or rec.get("status") != "approved":
        raise TicketError("order %d has no yes recorded today; a paper fill can only follow an approval" % a.index)
    qty = _f(order.get("qty"))
    if not qty:
        raise TicketError("order %d has no whole-share qty to fill" % a.index)
    typ = str(order.get("type", "market")).lower()
    side = str(order.get("side", "")).lower()
    limit = _f(order.get("limit_price"))
    if typ != "limit":
        entry, _note = kite_entry(order, cfg)
        limit = _f(entry.get("price"))
    price = _f(a.price)
    if a.price is not None and (price is None or price <= 0):
        raise TicketError("--price wants the latest price, like --price 1343.10")
    if price is None:
        price = _f(order.get("limit_price")) or _f((order.get("plan") or {}).get("entry")) or _f(order.get("ref_price"))
        if not price:
            raise TicketError("no price to fill order %d at: give --price LAST (trader-alerts: alerts.py quote %s)"
                              % (a.index, rec["symbol"]))
    elif limit and ((side == "buy" and price > limit + 0.005) or (side == "sell" and price < limit - 0.005)):
        a.status, a.broker_id, a.filled_qty, a.filled_price = "failed", None, None, None
        a.note = "paper: the price %s is past the order's limit %s, so it would not have filled" % (_p(price), _p(limit))
        cmd_result(a)
        print("Not filled: %s is %s the limit %s. A late entry is a different trade: make a new plan, or skip it."
              % (_p(price), "above" if side == "buy" else "below", _p(limit)))
        return 1
    a.status = "placed"
    a.broker_id = "PAPER-%s" % fingerprint(order)[:8]
    a.filled_qty, a.filled_price = _str_num(qty), "%.2f" % price
    a.note = "paper fill at %s" % _p(price)
    cmd_result(a)
    print("Paper fill: %s %s %s at %s. Nothing went to a broker." % (side.upper(), _str_num(qty), rec["symbol"], _p(price)))
    if is_bracket(order) and rec.get("kind") == "entry":
        print("The stop-loss %s and the take-profit %s are yours to watch: trader-alerts (alerts.py add --from-plan)."
              % (_p(order["stop_loss_stop_price"]), _p(order["take_profit_limit_price"])))
        print("When one is hit, record the sell: ticket.py fill --symbol %s --side sell --qty %s --price P"
              % (rec["symbol"], _str_num(qty)))
    return 0


def cmd_fill(a):
    cfg = read_json(a.config, "config", required=False) or {}
    now = parse_now(a.now)
    date = a.date or to_ist(now).date().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise TicketError("--date wants a date like 2026-11-11")
    pf = apply_fill(a.portfolio, cfg, a.symbol, a.side, a.qty, a.price, date)
    log_fill(a.state, now, date, a.symbol, a.side, a.qty, a.price)
    print("Recorded %s %s %s at %s on %s in %s. Cash now %s, after about %s charges on this leg."
          % (a.side, a.qty, a.symbol.upper(), _money(a.price), date, a.portfolio, _money(pf["cash"]),
             _money(pf.get("last_charges", 0))))
    return 0


def cmd_flatten(a):
    cfg = read_json(a.config, "config", required=False) or {}
    sym = a.symbol.strip().upper()
    now, today = _clock(a)
    paper = cfg.get("paper", True)
    source = "the broker, get_positions"
    if a.qty is not None:
        qty = _f(a.qty)
        if qty is None or qty <= 0:
            raise TicketError("--qty wants the number of shares you hold, like --qty 27")
    else:
        pf = read_json(a.portfolio, "portfolio", required=False) or {}
        qty = sum(_f(p.get("shares", p.get("qty"))) or 0 for p in pf.get("positions", [])
                  if str(p.get("ticker") or p.get("symbol") or "").upper() == sym)
        source = a.portfolio
        if qty <= 1e-9:
            raise TicketError("nothing to flatten: no %s shares in %s. Check the broker (get_positions) and "
                              "pass --qty if you do hold some" % (sym, a.portfolio))
    plan = read_json(a.plan, "plan", required=False) or {}
    flat_by = (plan.get("flat_by") if str(plan.get("symbol", "")).upper() == sym else None) \
        or cfg.get("flat_by") or "15:10"
    order = {"symbol": sym, "exchange": str(cfg.get("exchange") or "NSE").upper(),
             "product": str(cfg.get("product") or "MIS").upper(), "side": "sell", "qty": _str_num(qty),
             "type": "market", "time_in_force": "day",
             "why": "flat by %s India time: closes the %s day trade before the close (qty from %s)"
             % (flat_by, sym, source)}
    if a.price is not None:
        ref = _f(a.price)
        if ref is None or ref <= 0:
            raise TicketError("--price wants the latest price, like --price 1346.00")
        order["ref_price"] = "%.2f" % ref
    old = read_json(a.orders, "orders", required=False)
    replaced = len(old.get("orders", [])) if isinstance(old, dict) else 0
    doc = {"created_by": "trader-broker", "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "proposed",
           "paper": bool(paper),
           "note": "Flatten ticket. Nothing is placed until trader-risk passes it and you say yes in the chat.",
           "source": "ticket.py flatten %s on %s" % (sym, today), "orders": [order]}
    write_json(a.orders, doc)
    print("Flatten %s: %s (flat by %s India time)." % (sym, plain(order), flat_by))
    print("Wrote it to %s%s." % (a.orders, (" (it replaced %d earlier proposal%s)"
                                             % (replaced, "" if replaced == 1 else "s")) if replaced else ""))
    if a.qty is None:
        print("The qty comes from %s.%s" % (source, "" if paper else " Check it against get_positions before you say yes."))
    print("Next:")
    print("  1. trader-risk: check.py. A sell that only closes what you hold is never blocked by the daily")
    print("     limits or the entry window.")
    print("  2. ticket.py show, then the user's yes for this one order.")
    if paper:
        print("  3. ticket.py paper --index 1 --price LAST records the simulated sell.")
    else:
        print("  3. The stop-loss order is still open at the exchange. Cancel it FIRST: get_orders, then")
        print("     cancel_order for the open SL order (Needs approval). If you sell first, that stop can still")
        print("     fire later and leave you short. Then %s with the ticket." % KITE_TOOL)
    print("Brokers square off intraday (MIS) positions on their own a few minutes before the 3:30 PM close")
    print("(Zerodha from 3:25 PM, with a charge): be out before that.")
    return 0


def cmd_log(a):
    state = load_state(a.state)
    now, today = _clock(a)
    rows = [r for r in state.get("orders", []) if a.all or rec_day(r) == today]
    if not rows:
        print("No decisions recorded%s." % ("" if a.all else " today"))
        return 1
    for r in rows:
        extra = (" id " + r["broker_order_id"]) if r.get("broker_order_id") else ""
        reply = (' reply "%s"' % r["reply"]) if r.get("reply") and r["status"] in ("approved", "declined") else ""
        loss = (" max loss %s" % _money(r["max_loss"])) if r.get("max_loss") is not None and r["status"] == "placed" else ""
        idx = ("#%s" % r["index"]) if r.get("index") is not None else "  "
        print("%s  %s %-9s %s%s%s%s" % (r.get("at"), idx, r.get("status"), r.get("plain"), reply, loss, extra))
    placed = sum(1 for r in rows if r.get("status") == "placed")
    print("%d placed%s." % (placed, "" if a.all else " today"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Order tickets and your yes (trader-broker, India). Never places orders.")
    sub = ap.add_subparsers(dest="cmd")

    def clock(p):
        p.add_argument("--now", help="pretend it is this India time, e.g. \"2026-11-11 10:00\"")
        p.add_argument("--today", help="YYYY-MM-DD (default: today in India)")

    def common(p):
        p.add_argument("--orders", default="trader/orders.json")
        p.add_argument("--config", default="trader/config.json")
        p.add_argument("--risk", default="trader/state/risk.json")
        p.add_argument("--state", default="trader/state/broker.json")
        clock(p)

    p = sub.add_parser("show", help="render the tickets")
    common(p)
    p.add_argument("--index", type=int)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("approve", help="record the user's explicit yes for one order")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--reply", required=True, help="the user's reply, word for word")
    p = sub.add_parser("decline", help="record a no")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--reply")
    p = sub.add_parser("paper", help="PAPER account: record the simulated fill of an approved order")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--price", help="the latest price to fill at (default: the order's own price)")
    p.add_argument("--portfolio", default="trader/portfolio.json")
    p = sub.add_parser("result", help="LIVE account: record what happened after the Allow once / Deny card")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--status", required=True, choices=["placed", "denied", "failed"])
    p.add_argument("--broker-id")
    p.add_argument("--note")
    p.add_argument("--filled-qty")
    p.add_argument("--filled-price")
    p.add_argument("--portfolio", default="trader/portfolio.json")
    p = sub.add_parser("fill", help="record a fill in trader/portfolio.json")
    p.add_argument("--symbol", required=True)
    p.add_argument("--side", required=True, choices=["buy", "sell"])
    p.add_argument("--qty", required=True)
    p.add_argument("--price", required=True)
    p.add_argument("--date", help="YYYY-MM-DD (default: today in India)")
    p.add_argument("--now")
    p.add_argument("--portfolio", default="trader/portfolio.json")
    p.add_argument("--config", default="trader/config.json")
    p.add_argument("--state", default="trader/state/broker.json")
    p = sub.add_parser("flatten", help="a sell ticket that closes a symbol's position by flat_by")
    p.add_argument("--symbol", required=True)
    p.add_argument("--qty", help="shares you hold, from get_positions (default: trader/portfolio.json)")
    p.add_argument("--price", help="the latest price: the sell goes as a limit a little below it")
    p.add_argument("--orders", default="trader/orders.json", help="where the ticket is written")
    p.add_argument("--portfolio", default="trader/portfolio.json")
    p.add_argument("--plan", default="trader/plan.json")
    p.add_argument("--config", default="trader/config.json")
    clock(p)
    p = sub.add_parser("log", help="today's decisions")
    p.add_argument("--state", default="trader/state/broker.json")
    clock(p)
    p.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"show": cmd_show, "approve": cmd_approve, "decline": cmd_decline, "paper": cmd_paper,
                "result": cmd_result,
                "fill": cmd_fill, "flatten": cmd_flatten, "log": cmd_log}[a.cmd](a)
    except TicketError as e:
        print("ticket.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
