"""Monthly momentum rotation (Nifty 200/500 style), long-only delivery.

Each month, using data up to the last trading day of the previous month:
  1. Universe: stocks with >= 1 year of history, among the `liquid_top` most-traded (by 3-month median
     traded value), price >= min_price.
  2. Score = average z-score of risk-adjusted 12-1 month and 6-month returns
     (return / annualised volatility) - the same idea as NSE's Nifty200 Momentum 30 index.
  3. Hold the top `hold_n`, equal weight. Existing holdings stay while rank <= `buffer_rank` (cuts turnover).
  4. Regime filter (optional): if the market index closes below its 200-day average, hold cash instead.
Orders are filled at the next day's open with Zerodha delivery charges + slippage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .costs import CostModel


@dataclass
class MomParams:
    hold_n: int = 20
    buffer_rank: int = 40
    liquid_top: int = 300
    min_price: float = 30.0
    regime_filter: bool = True
    regime_ma: int = 200
    cash_yield: float = 0.055          # liquid fund / LIQUIDBEES on idle cash
    stcg: float = 0.20                 # tax on gains held < 12 months
    ltcg: float = 0.125                # tax on gains held >= 12 months
    ltcg_exempt: float = 125000.0      # yearly LTCG exemption
    costs: CostModel = field(default_factory=lambda: CostModel(slippage_pct=0.001))


def load_panel(folder, symbols=None):
    from pathlib import Path

    o, c, v = {}, {}, {}
    for f in sorted(Path(folder).glob("*.csv")):
        s = f.name.replace(".NS.csv", "").replace(".csv", "")
        if symbols and s not in symbols:
            continue
        df = pd.read_csv(f, index_col=0, parse_dates=True)
        df.columns = [x.lower() for x in df.columns]
        df = df[~df.index.duplicated()].sort_index()
        df = df[(df.close > 0) & (df.open > 0)]
        o[s], c[s], v[s] = df.open, df.close, df.volume
    return pd.DataFrame(o), pd.DataFrame(c), pd.DataFrame(v)


def scores(close: pd.DataFrame, volume: pd.DataFrame, asof, p: MomParams) -> pd.Series:
    """Momentum scores for all eligible stocks using data up to and including `asof`."""
    hist = close.loc[:asof]
    if len(hist) < 260:
        return pd.Series(dtype=float)
    last = hist.iloc[-1]
    enough = hist.iloc[-253:].notna().sum() >= 240
    tv = (hist.iloc[-63:] * volume.loc[:asof].iloc[-63:]).median()
    elig = enough & (last >= p.min_price) & tv.notna()
    liquid = tv[elig].sort_values(ascending=False).index[: p.liquid_top]
    h = hist[liquid]
    r12 = h.iloc[-22] / h.iloc[-253] - 1
    r6 = h.iloc[-1] / h.iloc[-127] - 1
    vol = np.log(h.iloc[-253:]).diff().std() * np.sqrt(252)
    a, b = r12 / vol, r6 / vol
    z = lambda x: (x - x.mean()) / x.std()
    return ((z(a) + z(b)) / 2).dropna().sort_values(ascending=False)


def target_portfolio(sc: pd.Series, held: list[str], p: MomParams) -> list[str]:
    rank = {s: i + 1 for i, s in enumerate(sc.index)}
    keep = [s for s in held if rank.get(s, 10**9) <= p.buffer_rank]
    for s in sc.index:
        if len(keep) >= p.hold_n:
            break
        if s not in keep:
            keep.append(s)
    return keep[: p.hold_n]


def risk_on(index_close: pd.Series, asof, p: MomParams) -> bool:
    if not p.regime_filter:
        return True
    h = index_close.loc[:asof].dropna()
    return len(h) >= p.regime_ma and h.iloc[-1] >= h.iloc[-p.regime_ma:].mean()


def backtest(opens, closes, vols, index_close, p: MomParams, capital=1_000_000.0, start=None, end=None):
    dates = closes.loc[start:end].index
    month_end = pd.Series(dates, index=dates).groupby(dates.to_period("M")).last()
    rebal_signal_days = set(month_end.values[:-1])
    cash, pos = capital, {}          # pos: sym -> [qty, cost_basis_per_share, buy_date]
    tax_bucket = {"st": 0.0, "lt": 0.0}
    eq, trades, pending = [], [], None
    c = p.costs
    fy_of = lambda d: d.year if d.month >= 4 else d.year - 1
    cur_fy = fy_of(dates[0])
    for i, d in enumerate(dates):
        # pay last FY's capital-gains tax on the first trading day of a new FY
        if fy_of(d) != cur_fy:
            st, lt = tax_bucket["st"], tax_bucket["lt"]
            net_st = st
            net_lt = lt + min(net_st, 0)          # ST losses can offset LT gains
            tax = max(net_st, 0) * p.stcg + max(net_lt - p.ltcg_exempt, 0) * p.ltcg
            cash -= tax
            trades.append({"date": d, "symbol": "TAX", "side": "TAX", "qty": 0, "price": 0, "value": -tax})
            tax_bucket = {"st": 0.0, "lt": 0.0}
            cur_fy = fy_of(d)
        if i > 0:
            cash *= (1 + p.cash_yield) ** (1 / 252)
        if pending is not None:
            target = pending
            pending = None
            px_open = opens.loc[d]
            # sells
            for s in list(pos):
                if s not in target and np.isfinite(px_open.get(s, np.nan)):
                    q, basis, bd = pos.pop(s)
                    px = c.fill_price("SELL", px_open[s])
                    ch = c.charges("SELL", q, px)
                    cash += q * px - ch
                    gain = q * (px - basis) - ch
                    tax_bucket["lt" if (d - bd).days >= 365 else "st"] += gain
                    trades.append({"date": d, "symbol": s, "side": "SELL", "qty": q, "price": px, "value": q * px})
            # buys: equal weight of current equity across target names
            prev = closes.iloc[closes.index.get_loc(d) - 1]
            mark = cash + sum(q * (prev.get(s) if np.isfinite(prev.get(s, np.nan)) else basis) for s, (q, basis, _) in pos.items())
            slot = mark / max(len(target), 1) if target else 0
            for s in target:
                if s in pos or not np.isfinite(px_open.get(s, np.nan)):
                    continue
                px = c.fill_price("BUY", px_open[s])
                q = int(min(slot, cash) / (px * 1.002))
                if q <= 0:
                    continue
                ch = c.charges("BUY", q, px)
                cash -= q * px + ch
                pos[s] = [q, px + ch / q, d]
                trades.append({"date": d, "symbol": s, "side": "BUY", "qty": q, "price": px, "value": q * px})
        cl = closes.loc[d]
        value = cash + sum(q * (cl.get(s) if np.isfinite(cl.get(s, np.nan)) else basis) for s, (q, basis, _) in pos.items())
        eq.append((d, value))
        if d in rebal_signal_days:
            if risk_on(index_close, d, p):
                sc = scores(closes, vols, d, p)
                pending = target_portfolio(sc, list(pos), p) if len(sc) else list(pos)
            else:
                pending = []
    return pd.Series(dict(eq)), pd.DataFrame(trades)


def perf(eq: pd.Series, rf=0.065):
    r = eq.pct_change().dropna()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    ex = r - rf / 252
    return {"cagr": (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1, "sharpe": ex.mean() / ex.std() * np.sqrt(252),
            "max_dd": (eq / eq.cummax() - 1).min(), "vol": r.std() * np.sqrt(252)}
