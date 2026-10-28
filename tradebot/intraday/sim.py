"""ReplayAdapter: run the real OrbBot against historical 1-minute data, minute by minute.

Order model: an order placed at the end of minute i is first eligible in minute i+1.
  SL BUY  : triggers when high >= trigger; fills at max(trigger, open) if <= limit,
            else rests as a limit order at `limit` (fills when low <= limit).   SELL mirrored.
  LIMIT   : marketable at the open -> fills at the open; otherwise fills at the limit if touched.
Every fill pays `slip_bps` adverse slippage.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .data import C, H, L, MINUTES, O, V, daily_from_grid


class ReplayAdapter:
    def __init__(self, universe: dict, day: pd.Timestamp, slip_bps: float = 3.0):
        self.u, self.day, self.slip = universe, pd.Timestamp(day), slip_bps / 1e4
        self.k = {s: days.get_indexer([self.day])[0] for s, (days, _) in universe.items()}
        self.i = -1                     # last completed minute
        self.book, self.n = {}, 0

    # clock
    def now(self):
        base = dt.datetime.combine(self.day.date(), dt.time(9, 15))
        return base + dt.timedelta(minutes=self.i + 1, seconds=5)

    def set_minute(self, i):
        self.i = i
        self._match(i)

    def _bar(self, s, i):
        days, g = self.u[s]
        return g[self.k[s], i]

    # data
    def tick_size(self, s):
        return 0.05 if self._bar(s, 0)[C] >= 250 else 0.01

    def daily_bars(self, s, n):
        days, g = self.u[s]
        k = self.k[s]
        d = daily_from_grid(g[max(0, k - n):k])
        return [tuple(map(float, r)) for r in d]

    def first_candle_volumes(self, s, n):
        days, g = self.u[s]
        k = self.k[s]
        return [float(x) for x in g[max(0, k - n):k, :5, V].sum(1)]

    def today_first_candle(self, s):
        if self.i < 4:
            raise RuntimeError("first candle not complete")
        days, g = self.u[s]
        b = g[self.k[s], :5]
        return float(b[0, O]), float(b[:, H].max()), float(b[:, L].min()), float(b[4, C]), float(b[:, V].sum())

    def ltp(self, symbols):
        return {s: float(self._bar(s, self.i)[C]) for s in symbols if s in self.u}

    # orders
    def place(self, s, side, qty, order_type, price=None, trigger=None):
        self.n += 1
        oid = f"SIM{self.n}"
        self.book[oid] = {"symbol": s, "side": side, "qty": qty, "type": order_type, "price": price,
                          "trigger": trigger, "status": "TRIGGER PENDING" if order_type == "SL" else "OPEN",
                          "average_price": 0.0, "placed": self.i, "triggered": False}
        return oid

    def cancel(self, oid):
        if self.book[oid]["status"] != "COMPLETE":
            self.book[oid]["status"] = "CANCELLED"

    def orders(self):
        return {k: dict(v) for k, v in self.book.items()}

    def _fill(self, o, px, i):
        d = 1 if o["side"] == "BUY" else -1
        o.update(status="COMPLETE", average_price=round(px * (1 + d * self.slip), 2),
                 time=(dt.datetime.combine(self.day.date(), dt.time(9, 15)) + dt.timedelta(minutes=i)).strftime("%H:%M"))

    def _match(self, i):
        for o in self.book.values():
            if o["status"] not in ("OPEN", "TRIGGER PENDING") or o["placed"] >= i:
                continue
            op, hi, lo = (float(x) for x in self._bar(o["symbol"], i)[[O, H, L]])
            buy = o["side"] == "BUY"
            if o["type"] == "SL" and not o["triggered"]:
                if (buy and hi >= o["trigger"]) or (not buy and lo <= o["trigger"]):
                    o["triggered"] = True
                    o["status"] = "OPEN"
                    px = max(o["trigger"], op) if buy else min(o["trigger"], op)
                    if (buy and px <= o["price"]) or (not buy and px >= o["price"]):
                        self._fill(o, px, i)
                        continue
                else:
                    continue
            # resting limit (plain LIMIT, or SL that triggered beyond its limit)
            if buy and (op <= o["price"] or lo <= o["price"]):
                self._fill(o, min(op, o["price"]), i)
            elif not buy and (op >= o["price"] or hi >= o["price"]):
                self._fill(o, max(op, o["price"]), i)


def replay_day(universe, day, cfg, costs=None, slip_bps=3.0):
    from .live import OrbBot

    a = ReplayAdapter(universe, day, slip_bps)
    bot = OrbBot(cfg, a, costs)
    for i in range(MINUTES):
        a.set_minute(i)
        if bot.step() == "DONE":
            break
    return bot
