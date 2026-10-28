"""Intraday ORB backtest engine (MIS, Zerodha charges, minute-by-minute simulation).

Strategies (both are the most widely cited intraday setups):
  orb5_sip : Zarattini, Barbon & Aziz (2023) "ORB on Stocks in Play". First 5-min candle sets the
             direction (green -> long only, red -> short only). Stop entry at the 5-min high/low,
             stop-loss = k x 14-day ATR, no target, square off at 15:15. Each day trade only the
             N stocks with the highest relative volume in the first 5 minutes.
  orb15    : Classic 15-minute opening-range breakout. Trade the first break of the 9:15-9:30
             high/low, stop at the other side of the range, target = R multiple, square off 15:15.

Portfolio: risk `risk_pct` of equity per trade (qty = risk / stop distance), notional capped by
`max_leverage`, and a `day_loss_pct` circuit breaker that squares off everything mid-day.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data import C, H, L, MINUTES, O, V, daily_from_grid

SQUARE_OFF = 360       # 15:15 bar index -> exit at its open
LAST_ENTRY = 345       # 15:00, no new entries after this


@dataclass
class MisCosts:
    brokerage_pct: float = 0.0003
    brokerage_cap: float = 20.0
    stt_sell_pct: float = 0.00025
    txn_pct: float = 0.0000307
    sebi_pct: float = 0.000001
    stamp_buy_pct: float = 0.00003
    gst_pct: float = 0.18
    slip_stop_pct: float = 0.0003   # stop orders (entries + stop-loss exits) slip 3 bps
    slip_mkt_pct: float = 0.0002    # square-off / circuit-breaker exits slip 2 bps

    def charges(self, buy_value: float, sell_value: float) -> float:
        brk = min(buy_value * self.brokerage_pct, self.brokerage_cap) + min(sell_value * self.brokerage_pct, self.brokerage_cap)
        txn = (buy_value + sell_value) * self.txn_pct
        sebi = (buy_value + sell_value) * self.sebi_pct
        return brk + txn + sebi + sell_value * self.stt_sell_pct + buy_value * self.stamp_buy_pct + (brk + txn + sebi) * self.gst_pct


@dataclass
class Params:
    strategy: str = "orb5_sip"
    top_n: int = 5
    stop_atr: float = 0.10          # orb5_sip stop distance in ATRs
    target_r: float = 2.0           # orb15 target in R multiples
    min_rv: float = 1.0             # minimum relative volume to qualify
    risk_pct: float = 0.005         # 0.5% of equity risked per trade
    day_loss_pct: float = 0.02      # stop trading the day at -2%
    max_leverage: float = 4.0       # total notional / equity cap (MIS)
    entry_bar_rule: str = "close"   # "close" or "conservative" (see simulate)
    costs: MisCosts = field(default_factory=MisCosts)


# --------------------------------------------------------------------------- setups
def prepare(grid: np.ndarray, p: Params):
    """Per-day features computed from PRIOR days only (ATR14, avg opening volume)."""
    d = daily_from_grid(grid)
    pc = np.roll(d[:, 3], 1)
    pc[0] = np.nan
    tr = np.nanmax(np.stack([d[:, 1] - d[:, 2], np.abs(d[:, 1] - pc), np.abs(d[:, 2] - pc)]), 0)
    atr = pd.Series(tr).rolling(14).mean().shift(1).to_numpy().copy()
    # an overnight jump > 25% is almost always an unadjusted split/bonus -> distrust ATR/volume for 15 days
    jump = np.abs(d[:, 0] / pc - 1) > 0.25
    bad = pd.Series(jump).rolling(15, min_periods=1).max().fillna(0).to_numpy().astype(bool)
    atr[bad] = np.nan
    or_len = 5 if p.strategy == "orb5_sip" else 15
    or_vol = grid[:, :or_len, V].sum(1)
    avg_vol = pd.Series(or_vol).rolling(14).mean().shift(1).to_numpy()
    rv = or_vol / avg_vol
    return atr, rv


def setup(day: np.ndarray, atr: float, p: Params):
    """Return (start_min, long_trigger, short_trigger, long_stop, short_stop, target_r) or None."""
    if not np.isfinite(atr) or atr <= 0:
        return None
    if p.strategy == "orb5_sip":
        o, c = day[0, O], day[4, C]
        hi, lo = day[:5, H].max(), day[:5, L].min()
        if c > o:
            return 5, hi, None, hi - p.stop_atr * atr, None, None
        if c < o:
            return 5, None, lo, None, lo + p.stop_atr * atr, None
        return None
    if p.strategy == "orb15":
        hi, lo = day[:15, H].max(), day[:15, L].min()
        if hi - lo <= 0 or hi - lo > 1.5 * atr:  # skip huge gap/news ranges
            return None
        return 15, hi, lo, lo, hi, p.target_r
    raise ValueError(p.strategy)


def simulate(day: np.ndarray, s, p: Params):
    """Simulate one setup on one day. Returns dict with per-share MTM path or None (no trigger)."""
    start, lt, st, ls, ss, tr = s
    cs = p.costs
    h, l, o, c = day[:, H], day[:, L], day[:, O], day[:, C]
    entry_i = None
    for i in range(start, LAST_ENTRY + 1):
        up = lt is not None and h[i] >= lt
        dn = st is not None and l[i] <= st
        if up and dn:
            return None  # both sides hit in one minute: ambiguous, skip
        if up:
            d, px, stop = 1, max(lt, o[i]) * (1 + cs.slip_stop_pct), ls
            break
        if dn:
            d, px, stop = -1, min(st, o[i]) * (1 - cs.slip_stop_pct), ss
            break
    else:
        return None
    entry_i = i
    risk = abs(px - stop)
    if risk <= 0:
        return None
    target = px + d * tr * risk if tr else None
    exit_i, exit_px, reason = SQUARE_OFF, o[SQUARE_OFF] * (1 - d * cs.slip_mkt_pct), "eod"
    for j in range(entry_i, SQUARE_OFF):
        if j == entry_i:
            # Within the fill minute we can't see the order of ticks. "close": stopped only if the
            # minute closed beyond the stop; "conservative": stopped if the minute's range touched it.
            ref_l, ref_h = (c[j], c[j]) if p.entry_bar_rule == "close" else (l[j], h[j])
            stopped = (ref_l <= stop) if d == 1 else (ref_h >= stop)
            fill = stop
        else:
            stopped = (l[j] <= stop) if d == 1 else (h[j] >= stop)
            fill = min(stop, o[j]) if d == 1 else max(stop, o[j])  # gap through the stop fills at the open
        if stopped:
            exit_i, exit_px, reason = j, fill * (1 - d * cs.slip_stop_pct), "stop"
            break
        if target is not None and j > entry_i and ((h[j] >= target) if d == 1 else (l[j] <= target)):
            exit_i, exit_px, reason = j, target, "target"
            break
    mtm = np.full(MINUTES, np.nan, dtype=np.float64)
    mtm[entry_i:exit_i] = (c[entry_i:exit_i] - px) * d
    mtm[exit_i:] = (exit_px - px) * d
    return {"dir": d, "entry_i": entry_i, "entry": px, "stop": stop, "exit_i": exit_i, "exit": exit_px,
            "reason": reason, "risk": risk, "mtm": mtm, "close": c}


# --------------------------------------------------------------------------- portfolio
def run(universe: dict[str, tuple[pd.DatetimeIndex, np.ndarray]], p: Params, capital=100000.0):
    feats = {s: prepare(g, p) for s, (days, g) in universe.items()}
    all_days = sorted(set().union(*[set(days) for days, _ in universe.values()]))
    pos = {s: pd.Series(np.arange(len(days)), index=days) for s, (days, _) in universe.items()}
    equity = capital
    eq_curve, trades = [], []
    for day in all_days:
        cands = []
        for s, (days, g) in universe.items():
            k = pos[s].get(day)
            if k is None:
                continue
            atr, rv = feats[s][0][k], feats[s][1][k]
            if not np.isfinite(rv) or rv < p.min_rv:
                continue
            cands.append((rv, s, k, atr))
        cands.sort(reverse=True)
        chosen = []
        for rv, s, k, atr in cands[: p.top_n]:
            g = universe[s][1][k]
            st = setup(g, atr, p)
            if st is None:
                continue
            sim = simulate(g, st, p)
            if sim is None:
                continue
            qty = int(p.risk_pct * equity / sim["risk"])
            qty = min(qty, int(equity * p.max_leverage / p.top_n / sim["entry"]))
            if qty <= 0:
                continue
            chosen.append((s, rv, qty, sim))
        day_pnl = 0.0
        if chosen:
            # circuit breaker: combined MTM (after estimated costs) hits -day_loss_pct -> close all
            est_cost = sum(p.costs.charges(q * x["entry"], q * x["entry"]) for _, _, q, x in chosen)
            path = sum(np.nan_to_num(q * x["mtm"]) for _, _, q, x in chosen) - est_cost
            hit = np.where(path <= -p.day_loss_pct * equity)[0]
            cut = hit[0] if len(hit) else None
            for s, rv, q, x in chosen:
                exit_i, exit_px, reason = x["exit_i"], x["exit"], x["reason"]
                if cut is not None and x["entry_i"] <= cut < exit_i:
                    exit_i, reason = cut, "day_loss_limit"
                    exit_px = x["close"][cut] * (1 - x["dir"] * p.costs.slip_mkt_pct)
                elif cut is not None and x["entry_i"] > cut:
                    continue  # never entered: breaker already tripped
                gross = q * (exit_px - x["entry"]) * x["dir"]
                buy_v, sell_v = (q * x["entry"], q * exit_px) if x["dir"] == 1 else (q * exit_px, q * x["entry"])
                ch = p.costs.charges(buy_v, sell_v)
                pnl = gross - ch
                day_pnl += pnl
                trades.append({"date": day, "symbol": s, "rv": round(rv, 2), "side": "LONG" if x["dir"] == 1 else "SHORT",
                               "qty": q, "entry": round(x["entry"], 2), "exit": round(exit_px, 2), "reason": reason,
                               "entry_time": _hhmm(x["entry_i"]), "exit_time": _hhmm(exit_i),
                               "gross": round(gross, 2), "charges": round(ch, 2), "pnl": round(pnl, 2),
                               "risk_rs": round(q * x["risk"], 2), "r": round(pnl / (q * x["risk"]), 3)})
        equity += day_pnl
        eq_curve.append((day, equity))
    eq = pd.Series(dict(eq_curve))
    return eq, pd.DataFrame(trades)


def _hhmm(i):
    t = 9 * 60 + 15 + int(i)
    return f"{t // 60:02d}:{t % 60:02d}"


def stats(eq: pd.Series, trades: pd.DataFrame, rf=0.065) -> dict:
    r = eq.pct_change().dropna()
    yrs = len(eq) / 252
    ex = r - rf / 252
    out = {
        "cagr": (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else np.nan,
        "sharpe": ex.mean() / ex.std() * np.sqrt(252) if ex.std() > 0 else 0.0,
        "max_dd": (eq / eq.cummax() - 1).min(),
        "trades": len(trades),
    }
    if len(trades):
        out |= {"win_rate": (trades.pnl > 0).mean(),
                "avg_r_gross": (trades.gross / trades.risk_rs).mean(),
                "avg_r_net": trades.r.mean(),
                "charges_rs": trades.charges.sum(),
                "gross_rs": trades.gross.sum()}
    return out
