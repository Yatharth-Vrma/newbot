"""Brokers with one interface: PaperBroker (simulated) and ZerodhaBroker (real money via Kite Connect).

Both keep a small JSON state file so the bot only ever manages the shares IT bought,
never shares you already owned.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pandas as pd

from .costs import CostModel


class StateFile:
    def __init__(self, path: str, defaults: dict):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {**defaults, **(json.loads(self.path.read_text()) if self.path.exists() else {})}

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, default=str))
        tmp.replace(self.path)


def round_tick(price: float, tick: float, side: str) -> float:
    steps = price / tick
    steps = math.ceil(steps) if side == "BUY" else math.floor(steps)
    return round(steps * tick, 2)


# --------------------------------------------------------------------------- paper
class PaperBroker:
    """Simulates AMO limit orders filled at the next session's open, with full Zerodha charges."""

    mode = "paper"

    def __init__(self, capital: float, costs: CostModel, state_path="state/paper.json"):
        self.costs = costs
        self.st = StateFile(state_path, {"cash": capital, "positions": {}, "pending": [], "fills": []})

    @property
    def cash(self) -> float:
        return self.st.data["cash"]

    def positions(self) -> dict[str, int]:
        return {k: v for k, v in self.st.data["positions"].items() if v > 0}

    def sync(self, data: dict[str, pd.DataFrame], symbols=None):
        """Fill yesterday's pending orders at the first open after the order date."""
        still = []
        for o in self.st.data["pending"]:
            df = data.get(o["symbol"])
            after = df[df.index > pd.Timestamp(o["date"])] if df is not None else None
            if after is None or after.empty:
                still.append(o)
                continue
            day, open_px = after.index[0], float(after.open.iloc[0])
            ok = open_px <= o["limit"] if o["side"] == "BUY" else open_px >= o["limit"]
            if not ok:
                self._log(o, day, None, "REJECTED: open gapped past limit")
                continue
            px = self.costs.fill_price(o["side"], open_px)
            ch = self.costs.charges(o["side"], o["qty"], px)
            pos = self.st.data["positions"]
            if o["side"] == "BUY":
                if o["qty"] * px + ch > self.cash:
                    self._log(o, day, None, "REJECTED: insufficient cash")
                    continue
                self.st.data["cash"] -= o["qty"] * px + ch
                pos[o["symbol"]] = pos.get(o["symbol"], 0) + o["qty"]
            else:
                q = min(o["qty"], pos.get(o["symbol"], 0))
                self.st.data["cash"] += q * px - ch
                pos[o["symbol"]] = pos.get(o["symbol"], 0) - q
            self._log(o, day, px, "FILLED", ch)
        self.st.data["pending"] = still

    def _log(self, o, day, px, status, charges=0.0):
        self.st.data["fills"].append({**o, "fill_date": str(day.date()), "fill_price": px,
                                      "charges": round(charges, 2), "status": status})

    def tick_size(self, symbol: str) -> float:
        return 0.05

    def place(self, symbol: str, side: str, qty: int, limit: float, date) -> str:
        oid = f"P{int(time.time() * 1000)}{symbol}"
        self.st.data["pending"].append({"id": oid, "symbol": symbol, "side": side, "qty": qty,
                                        "limit": limit, "date": str(pd.Timestamp(date).date())})
        return oid

    def save(self):
        self.st.save()


# --------------------------------------------------------------------------- live
class ZerodhaBroker:
    """Real orders through Kite Connect: NSE, CNC (delivery), LIMIT, AMO variety.

    SEBI (from 1 Apr 2026): orders must come from your registered static IP and you must log in
    with 2FA once per trading day -> run `python kite_login.py` each day before the bot runs.
    """

    mode = "live"

    def __init__(self, api_key: str, access_token: str, capital: float, costs: CostModel,
                 state_path="state/live.json"):
        from kiteconnect import KiteConnect

        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)
        self.costs = costs
        self.st = StateFile(state_path, {"cash": capital, "baseline": {}, "bot_positions": {},
                                         "pending": [], "fills": []})
        self._ticks = None

    @property
    def cash(self) -> float:
        return self.st.data["cash"]

    def _actual_qty(self) -> dict[str, int]:
        qty: dict[str, int] = {}
        for h in self.kite.holdings():
            qty[h["tradingsymbol"]] = qty.get(h["tradingsymbol"], 0) + h["quantity"] + h.get("t1_quantity", 0)
        for p in self.kite.positions()["net"]:
            if p["product"] == "CNC" and p["exchange"] == "NSE":
                qty[p["tradingsymbol"]] = qty.get(p["tradingsymbol"], 0) + p["quantity"]
        return qty

    def positions(self) -> dict[str, int]:
        return {k: v for k, v in self.st.data["bot_positions"].items() if v > 0}

    def sync(self, data: dict[str, pd.DataFrame], symbols: list[str]):
        actual = self._actual_qty()
        base = self.st.data["baseline"]
        for s in symbols:  # first time we see a symbol: whatever you already own is yours, not the bot's
            base.setdefault(s, actual.get(s, 0))
        # Update the cash ledger from orders placed in the last run.
        still = []
        for o in self.st.data["pending"]:
            try:
                hist = self.kite.order_history(o["id"])
                last = hist[-1]
            except Exception:
                last = {"status": "UNKNOWN"}
            if last.get("status") == "COMPLETE":
                px, q = float(last["average_price"]), int(last["filled_quantity"])
                ch = self.costs.charges(o["side"], q, px)
                self.st.data["cash"] += (-1 if o["side"] == "BUY" else 1) * q * px - ch
                self.st.data["fills"].append({**o, "fill_price": px, "filled": q, "charges": round(ch, 2),
                                              "status": "FILLED"})
            elif last.get("status") in ("CANCELLED", "REJECTED"):
                self.st.data["fills"].append({**o, "status": last["status"],
                                              "reason": last.get("status_message")})
            elif last.get("status") == "UNKNOWN" and o.get("tries", 0) >= 2:
                self.st.data["fills"].append({**o, "status": "UNKNOWN (dropped)"})
            else:
                o["tries"] = o.get("tries", 0) + 1
                still.append(o)
        self.st.data["pending"] = still
        self.st.data["bot_positions"] = {s: max(0, actual.get(s, 0) - base.get(s, 0)) for s in symbols}

    def tick_size(self, symbol: str) -> float:
        if self._ticks is None:
            self._ticks = {i["tradingsymbol"]: i["tick_size"] for i in self.kite.instruments("NSE")}
        return float(self._ticks.get(symbol, 0.05))

    def available_margin(self) -> float:
        return float(self.kite.margins("equity")["net"])

    def place(self, symbol: str, side: str, qty: int, limit: float, date) -> str:
        k = self.kite
        oid = k.place_order(
            variety=k.VARIETY_AMO, exchange=k.EXCHANGE_NSE, tradingsymbol=symbol,
            transaction_type=k.TRANSACTION_TYPE_BUY if side == "BUY" else k.TRANSACTION_TYPE_SELL,
            quantity=qty, product=k.PRODUCT_CNC, order_type=k.ORDER_TYPE_LIMIT,
            price=limit, validity=k.VALIDITY_DAY, tag="tradebot",
        )
        self.st.data["pending"].append({"id": oid, "symbol": symbol, "side": side, "qty": qty,
                                        "limit": limit, "date": str(pd.Timestamp(date).date())})
        time.sleep(0.25)  # stay far below SEBI's 10 orders/second threshold
        return oid

    def save(self):
        self.st.save()
