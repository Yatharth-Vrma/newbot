"""Paper portfolio for the monthly momentum rotation, run once per trading day after the close.

Once a month (normally the first trading day; a missed run catches up on the next one) the bot:
  1. decides how much to invest (0-100%) from the market regime: trend, breadth, volatility
  2. ranks the Nifty 500 by momentum and picks the top N
  3. sells what dropped out, trims/tops up holdings that drifted from target size, buys new names
Signals use the previous month-end close; fills use today's open. Other days: mark to market.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .momentum import MomParams, breadth_panel, exposure, scores, target_portfolio


def run_day(state_path: Path, opens, closes, vols, index_close, p: MomParams, capital: float) -> dict:
    st = {"cash": capital, "positions": {}, "last_rebalance_month": None, "fills": [], "equity": [], "regime_log": []}
    if state_path.exists():
        st |= json.loads(state_path.read_text())
    today = closes.index[-1]
    if st["equity"] and st["equity"][-1]["date"] >= str(today.date()):
        return {"status": "already_ran", "date": str(today.date())}
    if st["equity"]:  # interest on idle cash (liquid fund) since the last mark
        gap = max((today - pd.Timestamp(st["equity"][-1]["date"])).days, 0)
        st["cash"] *= (1 + p.cash_yield) ** (gap / 365)

    month = today.strftime("%Y-%m")
    orders = []
    if st["last_rebalance_month"] != month:
        before = closes.index[closes.index.strftime("%Y-%m") < month]
        signal_day = before[-1]
        k = closes.index.get_loc(signal_day) + 1
        hist_c, hist_v = closes.iloc[:k], vols.iloc[:k]
        above = breadth_panel(hist_c) if p.exposure_mode == "adaptive" else None
        e, why = exposure(index_close, above, signal_day, p)
        held = list(st["positions"])
        if e > 0:
            sc = scores(hist_c, hist_v, signal_day, p)
            target = target_portfolio(sc, held, p) if len(sc) else held
        else:
            target = []
        orders = _rebalance(st, target, e, opens.iloc[-1], closes.iloc[-2], today, p)
        st["last_rebalance_month"] = month
        st["last_regime"] = f"invest {e:.0%}: {why}"
        st["last_exposure"] = e
        st["last_target"] = target
        st["regime_log"].append({"month": month, "exposure": e, "why": why})
        st["fills"] += orders

    cl = closes.iloc[-1]
    value = st["cash"] + sum(q * (float(cl[s]) if np.isfinite(cl.get(s, np.nan)) else b)
                             for s, (q, b, _) in st["positions"].items())
    st["equity"].append({"date": str(today.date()), "equity": round(value, 2), "cash": round(st["cash"], 2),
                         "n_positions": len(st["positions"])})
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(st, indent=1))
    return {"status": "ok", "date": str(today.date()), "equity": round(value, 2), "orders": orders,
            "positions": {s: q for s, (q, _, _) in st["positions"].items()}, "regime": st.get("last_regime")}


def _rebalance(st, target, e, po, prev, today, p: MomParams) -> list[dict]:
    c, pos, orders, day = p.costs, st["positions"], [], str(today.date())

    def sell(s, q, reason):
        q0, basis, bd = pos[s]
        px = c.fill_price("SELL", float(po[s]))
        ch = c.charges("SELL", q, px)
        st["cash"] += q * px - ch
        orders.append({"date": day, "symbol": s, "side": "SELL", "qty": q, "price": round(px, 2), "charges": round(ch, 2),
                       "pnl": round(q * (px - basis) - ch, 2), "held_since": bd, "reason": reason})
        if q >= q0:
            pos.pop(s)
        else:
            pos[s] = [q0 - q, basis, bd]

    for s in list(pos):  # 1. exits
        if s not in target and np.isfinite(po.get(s, np.nan)):
            sell(s, pos[s][0], "dropped out")
    mark = st["cash"] + sum(q * (float(prev[s]) if np.isfinite(prev.get(s, np.nan)) else b) for s, (q, b, _) in pos.items())
    slot = mark * e / len(target) if target else 0.0
    band = p.rebalance_band if p.exposure_mode == "adaptive" else None
    for s in list(pos):  # 2. trims (adaptive only)
        px0 = po.get(s, np.nan)
        if band is not None and np.isfinite(px0) and pos[s][0] * px0 > slot * (1 + band):
            cut = pos[s][0] - int(slot / px0)
            if cut > 0:
                sell(s, cut, "trim to target")
    for s in target:  # 3. new buys and top-ups
        px0 = po.get(s, np.nan)
        if not np.isfinite(px0):
            continue
        have = pos[s][0] * px0 if s in pos else 0.0
        if s in pos and (band is None or have >= slot * (1 - band)):
            continue
        px = c.fill_price("BUY", float(px0))
        q = int(min(slot - have, st["cash"]) / (px * 1.002))
        if q <= 0:
            continue
        ch = c.charges("BUY", q, px)
        st["cash"] -= q * px + ch
        if s in pos:
            q0, b0, bd0 = pos[s]
            pos[s] = [q0 + q, (q0 * b0 + q * px + ch) / (q0 + q), bd0]
        else:
            pos[s] = [q, px + ch / q, day]
        orders.append({"date": day, "symbol": s, "side": "BUY", "qty": q, "price": round(px, 2), "charges": round(ch, 2)})
    return orders
