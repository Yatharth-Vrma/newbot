"""Daily bot run. Schedule it once per trading day AFTER market close (e.g. 16:30 IST).

1. Load daily candles, settle/reconcile yesterday's orders
2. Risk checks (kill switch on drawdown, stale data, halt file)
3. Compute today's signal per symbol and place AMO limit orders for tomorrow's open
"""
from __future__ import annotations

import csv
import datetime as dt
import logging
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from . import data as data_mod
from . import strategies
from .broker import PaperBroker, ZerodhaBroker, round_tick
from .costs import CostModel

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger("tradebot")


def make_broker(cfg: dict, costs: CostModel):
    mode = cfg["mode"]
    capital = float(cfg["capital"])
    if mode == "paper":
        return PaperBroker(capital, costs, cfg.get("state_dir", "state") + "/paper.json")
    if mode == "live":
        if os.environ.get("TRADEBOT_LIVE") != "YES":
            raise SystemExit("Refusing live mode: set environment variable TRADEBOT_LIVE=YES to confirm real-money trading.")
        api_key = os.environ["KITE_API_KEY"]
        token_file = Path(cfg.get("state_dir", "state")) / "access_token.txt"
        if not token_file.exists():
            raise SystemExit("No access token. Run `python kite_login.py` (daily 2FA login) first.")
        return ZerodhaBroker(api_key, token_file.read_text().strip(), capital, costs,
                             cfg.get("state_dir", "state") + "/live.json")
    raise SystemExit(f"Unknown mode {mode}")


def run(cfg: dict, force: bool = False, as_of=None, preloaded: dict | None = None) -> dict:
    """as_of + preloaded: replay the bot for a past trading day using only candles up to that day."""
    costs = CostModel.from_config(cfg.get("costs"))
    risk = cfg.get("risk", {})
    symbols: list[str] = cfg["symbols"]
    state_dir = Path(cfg.get("state_dir", "state"))
    halt_file = state_dir / "HALT"
    if halt_file.exists():
        log.error("HALT file present (%s). Bot is stopped. Delete the file to resume.", halt_file)
        return {"status": "halted"}

    broker = make_broker(cfg, costs)
    kite = getattr(broker, "kite", None)
    start = (dt.date.today() - dt.timedelta(days=int(cfg.get("lookback_days", 800)))).isoformat()
    data = {}
    if preloaded is not None:
        cut = pd.Timestamp(as_of)
        data = {s: df.loc[:cut] for s, df in preloaded.items() if not df.loc[:cut].empty}
    else:
        for s in symbols:
            try:
                data[s] = data_mod.load(s, cfg.get("data", {}), start, kite=kite)
            except Exception as e:  # one bad symbol shouldn't kill the run
                log.warning("Data failed for %s: %s", s, e)

    today = pd.Timestamp(as_of).date() if as_of is not None else dt.datetime.now(IST).date()
    if not data:
        log.error("No data loaded; aborting.")
        return {"status": "no_data"}
    last_bar = max(df.index[-1].date() for df in data.values())
    if last_bar != today and not force:
        log.info("Latest candle is %s, not today (%s): market holiday/weekend or data not updated. Nothing to do.",
                 last_bar, today)
        broker.sync(data, symbols)
        broker.save()
        return {"status": "no_new_bar", "last_bar": str(last_bar)}

    broker.sync(data, symbols)
    pos = broker.positions()
    closes = {s: float(df.close.iloc[-1]) for s, df in data.items()}
    equity = broker.cash + sum(q * closes.get(s, 0) for s, q in pos.items())

    st = broker.st.data
    st["peak_equity"] = max(st.get("peak_equity", equity), equity)
    dd = equity / st["peak_equity"] - 1
    prev = st.get("last_equity", equity)
    day_ret = equity / prev - 1 if prev else 0.0
    st["last_equity"] = equity

    kill = None
    if dd <= -abs(risk.get("max_drawdown_pct", 0.15)):
        kill = f"drawdown {dd:.1%} breached limit"
    elif day_ret <= -abs(risk.get("max_daily_loss_pct", 0.05)):
        kill = f"one-day loss {day_ret:.1%} breached limit"

    fn = strategies.get(cfg["strategy"], cfg.get("strategy_params"))
    per_symbol = min(float(cfg["capital"]) / len(symbols), float(cfg["capital"]) * risk.get("max_position_pct", 1.0))
    buffer = risk.get("limit_buffer_pct", 0.01)
    max_orders = int(risk.get("max_orders_per_run", 20))
    orders, signals = [], {}
    cash_left = broker.cash
    if hasattr(broker, "available_margin"):
        cash_left = min(cash_left, broker.available_margin())

    for s, df in data.items():
        if df.index[-1].date() != last_bar:
            log.warning("%s data is stale (%s); skipping", s, df.index[-1].date())
            continue
        sig = 0 if kill else int(fn(df).iloc[-1])
        signals[s] = sig
        have = pos.get(s, 0)
        px = closes[s]
        if sig == 1 and have == 0:
            qty = math.floor(per_symbol / (px * (1 + buffer)))
            limit = round_tick(px * (1 + buffer), broker.tick_size(s), "BUY")
            need = qty * limit + costs.charges("BUY", qty, limit)
            if qty <= 0:
                log.info("%s: allocation Rs %.0f too small for one share at %.2f", s, per_symbol, px)
            elif need > cash_left:
                log.info("%s: not enough cash (need %.0f, have %.0f)", s, need, cash_left)
            else:
                orders.append((s, "BUY", qty, limit))
                cash_left -= need
        elif sig == 0 and have > 0:
            orders.append((s, "SELL", have, round_tick(px * (1 - buffer), broker.tick_size(s), "SELL")))

    orders.sort(key=lambda o: o[1] != "SELL")  # sells first
    if len(orders) > max_orders:
        log.warning("Capping %d orders to max_orders_per_run=%d", len(orders), max_orders)
        orders = orders[:max_orders]

    placed = []
    for s, side, qty, limit in orders:
        try:
            oid = broker.place(s, side, qty, limit, last_bar)
            placed.append({"symbol": s, "side": side, "qty": qty, "limit": limit, "id": oid})
            log.info("ORDER %s %s x%d @ %.2f (%s)", side, s, qty, limit, broker.mode)
        except Exception as e:
            log.error("Order failed %s %s: %s", side, s, e)

    if kill:
        halt_file.write_text(f"{dt.datetime.now(IST).isoformat()} {kill}\n")
        log.error("KILL SWITCH: %s. Exit orders placed, bot halted.", kill)

    broker.save()
    _journal(state_dir, broker.mode, last_bar, equity, dd, signals, placed)
    summary = {"status": "ok" if not kill else "killed", "date": str(last_bar), "mode": broker.mode,
               "equity": round(equity, 2), "cash": round(broker.cash, 2), "drawdown": round(dd, 4),
               "positions": pos, "signals": signals, "orders": placed, "kill": kill}
    log.info("Summary: %s", summary)
    return summary


def _journal(state_dir: Path, mode, date, equity, dd, signals, orders):
    f = state_dir / f"journal_{mode}.csv"
    new = not f.exists()
    with f.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["date", "equity", "drawdown", "signals", "orders"])
        w.writerow([date, round(equity, 2), round(dd, 4),
                    ";".join(f"{k}={v}" for k, v in signals.items()),
                    ";".join(f"{o['side']} {o['symbol']} {o['qty']}@{o['limit']}" for o in orders)])
