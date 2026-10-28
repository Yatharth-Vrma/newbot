"""Live intraday ORB bot (MIS) — 'ORB on Stocks in Play' (Zarattini, Barbon & Aziz 2023).

Daily timeline (IST):
  09:05  prepare: 14-day ATR and 14-day average volume of the 09:15-09:20 candle for each stock
  09:20  read today's first 5-min candle; pick top N stocks by relative volume (RV > min_rv);
         green candle -> BUY stop-limit above its high, red -> SELL stop-limit below its low
  live   entry filled -> place stop-loss (k x ATR); combined day MTM <= -day_loss_pct -> flatten all
  15:00  cancel entries that never triggered
  15:15  cancel stops, square off everything (before Zerodha's ~15:20 auto square-off + Rs 50 fee)

The bot talks to an adapter with one interface; three adapters exist:
  KiteAdapter   real orders + real data (Kite Connect, paid plan for data)
  PaperAdapter  real Kite data, simulated orders (forward test without money)
  ReplayAdapter (sim.py) historical 1-minute data, simulated orders (runs anywhere, for testing)
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .engine import MisCosts

log = logging.getLogger("orb")


@dataclass
class OrbConfig:
    symbols: list[str]
    capital: float = 100000
    top_n: int = 3
    stop_atr: float = 0.25
    min_rv: float = 1.0
    risk_pct: float = 0.005
    day_loss_pct: float = 0.02
    max_leverage: float = 4.0
    entry_limit_buffer: float = 0.001   # stop-limit: limit = trigger +/- 0.1%
    exit_limit_buffer: float = 0.01     # protective SL / square-off limit buffer 1%
    entry_cutoff: str = "15:00"
    square_off: str = "15:15"
    state_dir: str = "state/intraday"


@dataclass
class Leg:
    symbol: str
    side: str                 # BUY (long) / SELL (short)
    qty: int
    trigger: float
    atr: float
    rv: float
    status: str = "NEW"       # NEW, ENTRY_OPEN, IN_POSITION, DONE, CANCELLED
    entry_id: str | None = None
    entry_price: float | None = None
    entry_time: str | None = None
    stop_id: str | None = None
    stop_price: float | None = None
    exit_id: str | None = None
    exit_price: float | None = None
    exit_time: str | None = None
    exit_reason: str | None = None

    @property
    def dir(self):
        return 1 if self.side == "BUY" else -1

    @property
    def exit_side(self):
        return "SELL" if self.side == "BUY" else "BUY"


def tick_round(px, tick, up: bool):
    n = px / tick
    return round((math.ceil(n - 1e-9) if up else math.floor(n + 1e-9)) * tick, 2)


class OrbBot:
    def __init__(self, cfg: OrbConfig, adapter, costs: MisCosts | None = None):
        self.cfg, self.a = cfg, adapter
        self.costs = costs or MisCosts()
        self.legs: dict[str, Leg] = {}
        self.feats: dict[str, dict] = {}
        self.phase = "INIT"   # INIT -> PREPARED -> TRADING -> CLOSING -> DONE
        self.halt_reason = None
        self.today = None

    # ----------------------------------------------------------------- persistence
    def _state_path(self):
        return Path(self.cfg.state_dir) / f"{self.today}.json"

    def save(self):
        p = self._state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"phase": self.phase, "halt": self.halt_reason, "feats": self.feats,
                                 "legs": {k: asdict(v) for k, v in self.legs.items()}}, indent=1, default=str))

    def load(self):
        p = self._state_path()
        if p.exists():
            s = json.loads(p.read_text())
            self.phase, self.halt_reason, self.feats = s["phase"], s["halt"], s["feats"]
            self.legs = {k: Leg(**v) for k, v in s["legs"].items()}
            log.info("Resumed state: phase=%s legs=%d", self.phase, len(self.legs))

    # ----------------------------------------------------------------- steps
    def step(self):
        now = self.a.now()
        if self.today is None:
            self.today = now.date().isoformat()
            self.load()
        hm = now.strftime("%H:%M")
        if self.phase == "INIT" and hm >= "09:05":
            self.prepare()
        if self.phase == "PREPARED" and now.time() >= dt.time(9, 20, 3):
            self.select_and_enter()
        if self.phase == "TRADING":
            self.sync()
            self.risk_check()
            if hm >= self.cfg.entry_cutoff:
                self.cancel_unfilled()
            if hm >= self.cfg.square_off:
                self.flatten("square_off")
        if self.phase == "CLOSING":
            self.sync()
            if all(l.status in ("DONE", "CANCELLED") for l in self.legs.values()):
                self.finish()
        self.save()
        return self.phase

    def prepare(self):
        for s in self.cfg.symbols:
            try:
                daily = self.a.daily_bars(s, 20)            # list of (o,h,l,c,v), oldest first, excluding today
                first5 = self.a.first_candle_volumes(s, 14)  # volumes of the 09:15 5-min candle, last 14 days
            except Exception as e:
                log.warning("prepare %s failed: %s", s, e)
                continue
            if len(daily) < 15 or len(first5) < 10:
                continue
            d = np.array(daily, dtype=float)
            pc = d[:-1, 3]
            tr = np.maximum.reduce([d[1:, 1] - d[1:, 2], np.abs(d[1:, 1] - pc), np.abs(d[1:, 2] - pc)])
            if np.any(np.abs(d[1:, 0] / pc - 1) > 0.25):
                continue  # corporate action in the window: skip the stock today
            self.feats[s] = {"atr": float(tr[-14:].mean()), "avg_vol5": float(np.mean(first5))}
        self.phase = "PREPARED"
        log.info("Prepared %d/%d symbols", len(self.feats), len(self.cfg.symbols))

    def select_and_enter(self):
        cands = []
        for s, f in self.feats.items():
            try:
                o, h, l, c, v = self.a.today_first_candle(s)
            except Exception as e:
                log.warning("first candle %s: %s", s, e)
                continue
            rv = v / f["avg_vol5"] if f["avg_vol5"] > 0 else 0
            if rv < self.cfg.min_rv or c == o:
                continue
            cands.append((rv, s, o, h, l, c))
        cands.sort(reverse=True)
        cap = self.cfg.capital
        for rv, s, o, h, l, c in cands[: self.cfg.top_n]:
            atr = self.feats[s]["atr"]
            tick = self.a.tick_size(s)
            side = "BUY" if c > o else "SELL"
            trigger = tick_round(h + tick, tick, True) if side == "BUY" else tick_round(l - tick, tick, False)
            stop_dist = self.cfg.stop_atr * atr
            qty = int(self.cfg.risk_pct * cap / stop_dist)
            qty = min(qty, int(cap * self.cfg.max_leverage / self.cfg.top_n / trigger))
            if qty <= 0:
                continue
            leg = Leg(s, side, qty, trigger, atr, round(rv, 2))
            limit = trigger * (1 + self.cfg.entry_limit_buffer * leg.dir)
            limit = tick_round(limit, tick, side == "BUY")
            try:
                leg.entry_id = self.a.place(s, side, qty, "SL", price=limit, trigger=trigger)
                leg.status = "ENTRY_OPEN"
                log.info("ENTRY %s %s x%d trigger %.2f limit %.2f (RV %.2f, ATR %.2f)", side, s, qty, trigger, limit, rv, atr)
            except Exception as e:
                log.error("entry order failed %s: %s", s, e)
                leg.status = "CANCELLED"
            self.legs[s] = leg
        self.phase = "TRADING"
        if not self.legs:
            log.info("No qualifying stocks today.")
            self.finish()

    def sync(self):
        book = self.a.orders()
        for leg in self.legs.values():
            if leg.status == "ENTRY_OPEN":
                o = book.get(leg.entry_id, {})
                if o.get("status") == "COMPLETE":
                    leg.entry_price, leg.entry_time = o["average_price"], o.get("time")
                    leg.status = "IN_POSITION"
                    self._place_stop(leg)
                elif o.get("status") in ("CANCELLED", "REJECTED"):
                    leg.status = "CANCELLED"
                    log.warning("entry %s %s: %s", leg.symbol, o.get("status"), o.get("message"))
            elif leg.status == "IN_POSITION":
                for oid, reason in ((leg.stop_id, "stop"), (leg.exit_id, leg.exit_reason or "exit")):
                    o = book.get(oid, {}) if oid else {}
                    if o.get("status") == "COMPLETE":
                        leg.exit_price, leg.exit_time, leg.exit_reason = o["average_price"], o.get("time"), reason
                        leg.status = "DONE"
                        self._journal(leg)
                        break
                    if oid == leg.stop_id and o.get("status") in ("CANCELLED", "REJECTED") and not leg.exit_id:
                        log.error("STOP for %s was %s -> exiting at market", leg.symbol, o.get("status"))
                        self._exit_now(leg, "stop_rejected")

    def _place_stop(self, leg: Leg):
        tick = self.a.tick_size(leg.symbol)
        stop = leg.entry_price - leg.dir * self.cfg.stop_atr * leg.atr
        stop = tick_round(stop, tick, leg.dir == -1)
        limit = tick_round(stop * (1 - leg.dir * self.cfg.exit_limit_buffer), tick, leg.dir == -1)
        leg.stop_price = stop
        try:
            leg.stop_id = self.a.place(leg.symbol, leg.exit_side, leg.qty, "SL", price=limit, trigger=stop)
            log.info("FILLED %s %s x%d @ %.2f -> stop %.2f", leg.side, leg.symbol, leg.qty, leg.entry_price, stop)
        except Exception as e:
            log.error("stop order failed %s: %s -> exiting", leg.symbol, e)
            self._exit_now(leg, "stop_failed")

    def _exit_now(self, leg: Leg, reason: str):
        if leg.stop_id:
            try:
                self.a.cancel(leg.stop_id)
            except Exception:
                pass
            o = self.a.orders().get(leg.stop_id, {})
            if o.get("status") == "COMPLETE":  # stop already filled: never send a second exit
                leg.exit_price, leg.exit_time, leg.exit_reason = o["average_price"], o.get("time"), "stop"
                leg.status = "DONE"
                self._journal(leg)
                return
        ltp = self.a.ltp([leg.symbol]).get(leg.symbol, leg.entry_price)
        tick = self.a.tick_size(leg.symbol)
        limit = tick_round(ltp * (1 - leg.dir * self.cfg.exit_limit_buffer), tick, leg.dir == -1)
        leg.exit_reason = reason
        leg.exit_id = self.a.place(leg.symbol, leg.exit_side, leg.qty, "LIMIT", price=limit)

    def mtm(self) -> float:
        live = [l for l in self.legs.values() if l.status in ("IN_POSITION", "DONE") and l.entry_price]
        if not live:
            return 0.0
        prices = self.a.ltp([l.symbol for l in live if l.status == "IN_POSITION"])
        total = 0.0
        for l in live:
            px = l.exit_price if l.status == "DONE" else prices.get(l.symbol, l.entry_price)
            total += l.dir * l.qty * (px - l.entry_price) - self.costs.charges(l.qty * l.entry_price, l.qty * px)
        return total

    def risk_check(self):
        m = self.mtm()
        if m <= -self.cfg.day_loss_pct * self.cfg.capital:
            self.halt_reason = f"day loss {m:,.0f} <= -{self.cfg.day_loss_pct:.1%} of capital"
            log.error("CIRCUIT BREAKER: %s", self.halt_reason)
            self.flatten("day_loss_limit")

    def cancel_unfilled(self):
        for leg in self.legs.values():
            if leg.status == "ENTRY_OPEN":
                try:
                    self.a.cancel(leg.entry_id)
                except Exception as e:
                    log.warning("cancel %s: %s", leg.symbol, e)
                leg.status = "CANCELLED"

    def flatten(self, reason: str):
        self.cancel_unfilled()
        for leg in self.legs.values():
            if leg.status == "IN_POSITION" and not leg.exit_id:
                self._exit_now(leg, reason)
        self.phase = "CLOSING"

    def finish(self):
        self.phase = "DONE"
        done = [l for l in self.legs.values() if l.status == "DONE"]
        pnl = sum(l.dir * l.qty * (l.exit_price - l.entry_price)
                  - self.costs.charges(l.qty * l.entry_price, l.qty * l.exit_price) for l in done)
        log.info("DAY DONE: %d trades, net P&L Rs %.0f%s", len(done), pnl,
                 f" (halted: {self.halt_reason})" if self.halt_reason else "")
        self.day_pnl = pnl

    def _journal(self, leg: Leg):
        f = Path(self.cfg.state_dir) / "journal.csv"
        f.parent.mkdir(parents=True, exist_ok=True)
        new = not f.exists()
        slip_bps = (leg.entry_price - leg.trigger) / leg.trigger * 1e4 * leg.dir
        gross = leg.dir * leg.qty * (leg.exit_price - leg.entry_price)
        ch = self.costs.charges(leg.qty * leg.entry_price, leg.qty * leg.exit_price)
        with f.open("a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["date", "symbol", "side", "qty", "rv", "trigger", "entry", "entry_slip_bps", "stop",
                            "exit", "reason", "entry_time", "exit_time", "gross", "charges", "net"])
            w.writerow([self.today, leg.symbol, leg.side, leg.qty, leg.rv, leg.trigger, leg.entry_price,
                        round(slip_bps, 2), leg.stop_price, leg.exit_price, leg.exit_reason, leg.entry_time,
                        leg.exit_time, round(gross, 2), round(ch, 2), round(gross - ch, 2)])


def run_forever(bot: OrbBot, poll_seconds: float = 2.0):
    """Live loop: call step() every couple of seconds until the day is done."""
    while bot.step() != "DONE":
        if bot.a.now().time() >= dt.time(15, 29):
            log.error("Market closing and bot not done; check positions manually!")
            break
        time.sleep(poll_seconds)


# =========================================================================== Kite adapters
class KiteAdapter:
    """Real Zerodha. Requires a Kite Connect app (Rs 500/month plan for market data),
    static-IP whitelisting (SEBI) and today's access token from kite_login.py."""

    IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

    def __init__(self, api_key: str, access_token: str):
        from kiteconnect import KiteConnect

        self.k = KiteConnect(api_key=api_key)
        self.k.set_access_token(access_token)
        inst = self.k.instruments("NSE")
        self._tok = {i["tradingsymbol"]: i["instrument_token"] for i in inst}
        self._tick = {i["tradingsymbol"]: float(i["tick_size"]) for i in inst}
        self._last_hist = 0.0

    def now(self):
        return dt.datetime.now(self.IST).replace(tzinfo=None)

    def tick_size(self, s):
        return self._tick.get(s, 0.05)

    def _hist(self, s, frm, to, interval):
        wait = 0.35 - (time.time() - self._last_hist)  # historical API: 3 requests/second
        if wait > 0:
            time.sleep(wait)
        self._last_hist = time.time()
        return self.k.historical_data(self._tok[s], frm, to, interval)

    def daily_bars(self, s, n):
        today = self.now().date()
        rows = self._hist(s, today - dt.timedelta(days=n * 2 + 10), today - dt.timedelta(days=1), "day")
        return [(r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in rows][-n:]

    def first_candle_volumes(self, s, n):
        today = self.now().date()
        rows = self._hist(s, today - dt.timedelta(days=n * 2 + 10), today - dt.timedelta(days=1), "5minute")
        vols = [r["volume"] for r in rows if r["date"].strftime("%H:%M") == "09:15"]
        return vols[-n:]

    def today_first_candle(self, s):
        t = self.now()
        rows = self._hist(s, t.replace(hour=9, minute=15, second=0), t.replace(hour=9, minute=19, second=59), "5minute")
        r = rows[0]
        return r["open"], r["high"], r["low"], r["close"], r["volume"]

    def ltp(self, symbols):
        if not symbols:
            return {}
        q = self.k.ltp([f"NSE:{s}" for s in symbols])
        return {k.split(":")[1]: v["last_price"] for k, v in q.items()}

    def place(self, s, side, qty, order_type, price=None, trigger=None):
        k = self.k
        oid = k.place_order(
            variety=k.VARIETY_REGULAR, exchange=k.EXCHANGE_NSE, tradingsymbol=s,
            transaction_type=side, quantity=qty, product=k.PRODUCT_MIS,
            order_type={"SL": k.ORDER_TYPE_SL, "LIMIT": k.ORDER_TYPE_LIMIT}[order_type],
            price=price, trigger_price=trigger, validity=k.VALIDITY_DAY, tag="orbbot")
        time.sleep(0.15)  # far below SEBI's 10 orders/second
        return oid

    def cancel(self, oid):
        self.k.cancel_order(self.k.VARIETY_REGULAR, oid)

    def orders(self):
        out = {}
        for o in self.k.orders():
            out[o["order_id"]] = {"status": o["status"], "average_price": o["average_price"],
                                  "time": str(o.get("exchange_timestamp") or o.get("order_timestamp")),
                                  "message": o.get("status_message")}
        return out


class PaperAdapter(KiteAdapter):
    """Real Kite prices, fake orders: SL orders fill when LTP crosses the trigger (at LTP), LIMIT
    exits fill at LTP. Good for a 2-4 week forward test before risking money."""

    def __init__(self, api_key, access_token, slip_bps=2.0):
        super().__init__(api_key, access_token)
        self.book, self.n, self.slip = {}, 0, slip_bps / 1e4

    def place(self, s, side, qty, order_type, price=None, trigger=None):
        self.n += 1
        oid = f"PAPER{self.n}"
        self.book[oid] = {"symbol": s, "side": side, "type": order_type, "price": price, "trigger": trigger,
                          "status": "TRIGGER PENDING" if order_type == "SL" else "OPEN", "average_price": 0}
        return oid

    def cancel(self, oid):
        if self.book[oid]["status"] not in ("COMPLETE",):
            self.book[oid]["status"] = "CANCELLED"

    def orders(self):
        open_ = [o for o in self.book.values() if o["status"] in ("OPEN", "TRIGGER PENDING")]
        px = self.ltp(list({o["symbol"] for o in open_}))
        for o in open_:
            p = px.get(o["symbol"])
            if p is None:
                continue
            d = 1 if o["side"] == "BUY" else -1
            hit = o["type"] == "LIMIT" or (p - o["trigger"]) * d >= 0
            if hit and (p - o["price"]) * d <= 0:
                o.update(status="COMPLETE", average_price=round(p * (1 + d * self.slip), 2), time=str(self.now()))
        return dict(self.book)
