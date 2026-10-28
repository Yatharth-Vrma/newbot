"""Paper portfolio for the monthly momentum rotation, run once per trading day after the close.

On the first trading day of a new month the signal is computed from the previous month-end close
and filled at that day's open (same as the backtest). Every other day it just marks to market.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .momentum import MomParams, risk_on, scores, target_portfolio


def run_day(state_path: Path, opens, closes, vols, index_close, p: MomParams, capital: float) -> dict:
    st = {"cash": capital, "positions": {}, "last_rebalance_month": None, "fills": [], "equity": []}
    if state_path.exists():
        st |= json.loads(state_path.read_text())
    today = closes.index[-1]
    if st["equity"] and st["equity"][-1]["date"] >= str(today.date()):
        return {"status": "already_ran", "date": str(today.date())}
    # interest on idle cash for the days since the last mark
    if st["equity"]:
        gap = max((today - pd.Timestamp(st["equity"][-1]["date"])).days, 0)
        st["cash"] *= (1 + p.cash_yield) ** (gap / 365)

    month = today.strftime("%Y-%m")
    orders = []
    # Rebalance once per month: normally on its first trading day; if a run was missed (or this is the
    # very first run) it catches up on the next run, still using the previous month-end signal.
    if st["last_rebalance_month"] != month:
        before = closes.index[closes.index.strftime("%Y-%m") < month]
        signal_day = before[-1]
        sig_i = closes.index.get_loc(signal_day)
        held = list(st["positions"])
        if risk_on(index_close, signal_day, p):
            sc = scores(closes.iloc[: sig_i + 1], vols.iloc[: sig_i + 1], signal_day, p)
            target = target_portfolio(sc, held, p) if len(sc) else held
            regime = "RISK-ON"
        else:
            target, regime = [], "RISK-OFF (index below 200-day average): holding cash"
        c = p.costs
        po = opens.iloc[-1]
        for s in held:
            if s not in target and np.isfinite(po.get(s, np.nan)):
                q, basis, bd = st["positions"].pop(s)
                px = c.fill_price("SELL", float(po[s]))
                ch = c.charges("SELL", q, px)
                st["cash"] += q * px - ch
                orders.append({"date": str(today.date()), "symbol": s, "side": "SELL", "qty": q, "price": round(px, 2),
                               "charges": round(ch, 2), "pnl": round(q * (px - basis) - ch, 2), "held_since": bd})
        prev = closes.iloc[-2]
        mark = st["cash"] + sum(q * float(prev.get(s, b)) for s, (q, b, _) in st["positions"].items())
        slot = mark / len(target) if target else 0
        for s in target:
            if s in st["positions"] or not np.isfinite(po.get(s, np.nan)):
                continue
            px = c.fill_price("BUY", float(po[s]))
            q = int(min(slot, st["cash"]) / (px * 1.002))
            if q <= 0:
                continue
            ch = c.charges("BUY", q, px)
            st["cash"] -= q * px + ch
            st["positions"][s] = [q, px + ch / q, str(today.date())]
            orders.append({"date": str(today.date()), "symbol": s, "side": "BUY", "qty": q, "price": round(px, 2),
                           "charges": round(ch, 2)})
        st["last_rebalance_month"] = month
        st["last_regime"] = regime
        st["last_target"] = target
        st["fills"] += orders

    cl = closes.iloc[-1]
    value = st["cash"] + sum(q * float(cl.get(s, b) if np.isfinite(cl.get(s, np.nan)) else b)
                             for s, (q, b, _) in st["positions"].items())
    st["equity"].append({"date": str(today.date()), "equity": round(value, 2), "cash": round(st["cash"], 2),
                         "n_positions": len(st["positions"])})
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(st, indent=1))
    return {"status": "ok", "date": str(today.date()), "equity": round(value, 2), "orders": orders,
            "positions": {s: q for s, (q, _, _) in st["positions"].items()}, "regime": st.get("last_regime")}
