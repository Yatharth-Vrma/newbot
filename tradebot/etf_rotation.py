"""Small-account ETF rotation ("dual momentum") with a monthly SIP.

Every month (first trading day):
  1. Add the monthly SIP amount (e.g. Rs 3,000) as cash.
  2. Score each risk ETF by its blended 3/6/12-month return (data up to the previous month-end).
  3. Hold the top `top_k` ETFs, but only those whose score beats cash (liquid fund) over the same window;
     otherwise park money in the liquid ETF. This is Antonacci-style dual momentum
     (relative + absolute momentum), adapted to Indian ETFs.
  4. Switch only when the pick changes (saves charges and short-term tax); new SIP money goes to the pick.

Whole units only; Zerodha delivery charges; capital-gains tax at sale (20% < 12 months, 12.5% after).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .costs import CostModel

DEFAULT_ASSETS = {          # NSE symbol -> what it holds
    "NIFTYBEES": "Nifty 50",
    "MID150BEES": "Nifty Midcap 150",
    "MON100": "Nasdaq 100 (US tech, in rupees)",
    "GOLDBEES": "Gold",
}
CASH = "LIQUIDBEES"


@dataclass
class RotParams:
    assets: list[str] = field(default_factory=lambda: list(DEFAULT_ASSETS))
    cash: str = CASH
    lookbacks: tuple = (63, 126, 252)      # ~3, 6, 12 months of trading days
    top_k: int = 1
    cash_rate: float = 0.06                # liquid-fund yield used for the absolute-momentum test
    stcg: float = 0.20
    ltcg: float = 0.125
    costs: CostModel = field(default_factory=lambda: CostModel(slippage_pct=0.001))


def scores(prices: pd.DataFrame, asof, p: RotParams) -> pd.Series:
    h = prices.loc[:asof, p.assets].dropna(how="all")
    out = {}
    for a in p.assets:
        s = h[a].dropna()
        if len(s) <= max(p.lookbacks):
            continue
        out[a] = np.mean([s.iloc[-1] / s.iloc[-1 - lb] - 1 for lb in p.lookbacks])
    return pd.Series(out).sort_values(ascending=False)


def picks(prices: pd.DataFrame, asof, p: RotParams) -> tuple[list[str], pd.Series]:
    sc = scores(prices, asof, p)
    hurdle = np.mean([(1 + p.cash_rate) ** (lb / 252) - 1 for lb in p.lookbacks])
    chosen = [a for a in sc.index[: p.top_k] if sc[a] > hurdle]
    return (chosen or [p.cash]), sc


def sip_backtest(prices: pd.DataFrame, monthly: float, p: RotParams, start=None, end=None, mode="rotation"):
    """mode: 'rotation' | 'equal' (keep all assets equally weighted via new money) | an asset symbol (plain SIP)."""
    px = prices.loc[start:end].copy()
    if p.cash not in px:  # synthetic liquid fund
        px[p.cash] = 1000 * (1 + p.cash_rate) ** (np.arange(len(px)) / 252)
    days = px.index
    first_of_month = days[np.r_[True, days.month[1:] != days.month[:-1]]]
    c = p.costs
    cash, units, basis = 0.0, {}, {}        # basis: list of (units, cost/unit, date) lots per symbol
    invested, rows, log = 0.0, [], []
    nav_units, nav = 0.0, 1.0               # time-weighted return via unitised NAV
    gains = {"st": 0.0, "lt": 0.0}

    def value(d):
        return cash + sum(u * px.at[d, s] for s, u in units.items() if u)

    def sell_all(s, d):
        nonlocal cash
        u = units.pop(s, 0)
        if not u:
            return
        pr = c.fill_price("SELL", px.at[d, s])
        ch = c.charges("SELL", u, pr)
        cash += u * pr - ch
        for lu, cost, bd in basis.pop(s, []):
            g = lu * (pr - cost) - ch * lu / u
            gains["lt" if (d - bd).days >= 365 else "st"] += g
        log.append((d, "SELL", s, u, pr))

    def buy(s, d, amount):
        nonlocal cash
        pr = c.fill_price("BUY", px.at[d, s])
        u = int(min(amount, cash) / (pr * 1.002))
        if u <= 0:
            return
        ch = c.charges("BUY", u, pr)
        cash -= u * pr + ch
        units[s] = units.get(s, 0) + u
        basis.setdefault(s, []).append((u, pr + ch / u, d))
        log.append((d, "BUY", s, u, pr))

    prev_fy = None
    for d in days:
        fy = d.year if d.month >= 4 else d.year - 1
        if prev_fy is not None and fy != prev_fy:  # pay last FY's tax
            tax = max(gains["st"], 0) * p.stcg + max(gains["lt"] + min(gains["st"], 0) - 125000, 0) * p.ltcg
            cash -= tax
            gains = {"st": 0.0, "lt": 0.0}
        prev_fy = fy
        if d in first_of_month:
            v_before = value(d)
            nav = v_before / nav_units if nav_units else nav
            cash += monthly
            invested += monthly
            nav_units += monthly / nav
            sig_day = days[days < d][-1] if (days < d).any() else None
            if mode == "rotation" and sig_day is not None:
                target, _ = picks(prices, sig_day, p)
            elif mode == "equal":
                target = list(p.assets)
            else:
                target = [mode if sig_day is not None else p.cash]
            if mode == "rotation":
                for s in list(units):
                    if s not in target:
                        sell_all(s, d)
                per = value(d) / len(target)
                for s in target:   # top up toward equal weight within the picks
                    have = units.get(s, 0) * px.at[d, s]
                    if per - have > 0:
                        buy(s, d, per - have)
            elif mode == "equal":
                gaps = {s: value(d) / len(target) - units.get(s, 0) * px.at[d, s] for s in target}
                for s in sorted(gaps, key=gaps.get, reverse=True):
                    if gaps[s] > 0 and cash > 0:
                        buy(s, d, gaps[s])
            else:
                buy(target[0], d, cash)
        v = value(d)
        rows.append((d, v, invested, v / nav_units if nav_units else 1.0))
    df = pd.DataFrame(rows, columns=["date", "value", "invested", "nav"]).set_index("date")
    return df, pd.DataFrame(log, columns=["date", "side", "symbol", "units", "price"])


def xirr(df: pd.DataFrame, monthly: float) -> float:
    """Money-weighted annual return of a monthly SIP."""
    flows = df.invested.diff().fillna(df.invested.iloc[0])
    flows = flows[flows > 0]
    t = np.array([(d - flows.index[0]).days / 365.25 for d in flows.index] + [(df.index[-1] - flows.index[0]).days / 365.25])
    cf = np.r_[-flows.values, df.value.iloc[-1]]
    lo, hi = -0.9, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        npv = np.sum(cf / (1 + mid) ** t)
        lo, hi = (mid, hi) if npv > 0 else (lo, mid)
    return mid


# --------------------------------------------------------------------------- live paper account
def clean_prices(px: pd.DataFrame) -> pd.DataFrame:
    """Undo Yahoo glitches/splits: a one-day move beyond 2x either way rescales the history before it."""
    px = px.copy()
    for col in px:
        s = px[col]
        r = s / s.shift(1)
        for d, v in r[(r < 0.5) | (r > 2)].dropna().items():
            s.loc[s.index < d] *= v
        px[col] = s
    return px


def run_month(state_path, prices: pd.DataFrame, p: RotParams, monthly: float) -> dict:
    """Paper SIP account. Call daily; acts on the first run of each new month (signal = previous month-end)."""
    import json
    from pathlib import Path

    state_path = Path(state_path)
    st = {"cash": 0.0, "units": {}, "invested": 0.0, "last_month": None, "orders": [], "equity": [],
          "bench_units": 0.0, "bench_cash": 0.0}
    if state_path.exists():
        st |= json.loads(state_path.read_text())
    today = prices.index[-1]
    if st["equity"] and st["equity"][-1]["date"] >= str(today.date()):
        return {"status": "already_ran", "date": str(today.date())}
    c, month, orders = p.costs, today.strftime("%Y-%m"), []
    sc = pd.Series(dtype=float)
    pick = None
    if st["last_month"] != month:
        sig_day = prices.index[prices.index.strftime("%Y-%m") < month][-1]
        target, sc = picks(prices, sig_day, p)
        pick = target
        st["cash"] += monthly
        st["invested"] += monthly
        po = prices.loc[today]                     # we run after the close: fills at today's close as proxy
        for s in list(st["units"]):
            if s not in target and st["units"][s] > 0:
                u = st["units"].pop(s)
                pr = c.fill_price("SELL", float(po[s]))
                st["cash"] += u * pr - c.charges("SELL", u, pr)
                orders.append({"date": str(today.date()), "side": "SELL", "symbol": s, "units": u, "price": round(pr, 2)})
        for s in target:
            per = (st["cash"] + sum(u * float(po[x]) for x, u in st["units"].items())) / len(target)
            have = st["units"].get(s, 0) * float(po[s])
            pr = c.fill_price("BUY", float(po[s]))
            u = int(min(per - have, st["cash"]) / (pr * 1.002))
            if u > 0:
                st["cash"] -= u * pr + c.charges("BUY", u, pr)
                st["units"][s] = st["units"].get(s, 0) + u
                orders.append({"date": str(today.date()), "side": "BUY", "symbol": s, "units": u, "price": round(pr, 2)})
        # benchmark: the same SIP into NIFTYBEES only
        st["bench_cash"] += monthly
        bp = c.fill_price("BUY", float(po["NIFTYBEES"]))
        bu = int(st["bench_cash"] / (bp * 1.002))
        if bu > 0:
            st["bench_cash"] -= bu * bp + c.charges("BUY", bu, bp)
            st["bench_units"] += bu
        st["last_month"] = month
        st["last_pick"] = target
        st["last_scores"] = {k: round(float(v), 4) for k, v in sc.items()}
        st["orders"] += orders
    cl = prices.loc[today]
    value = st["cash"] + sum(u * float(cl[s]) for s, u in st["units"].items())
    bench = st["bench_cash"] + st["bench_units"] * float(cl["NIFTYBEES"])
    st["equity"].append({"date": str(today.date()), "value": round(value, 2), "invested": st["invested"],
                         "nifty_sip_value": round(bench, 2)})
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(st, indent=1))
    return {"status": "ok", "date": str(today.date()), "equity": round(value, 2), "invested": st["invested"],
            "nifty_sip_value": round(bench, 2), "orders": orders, "holding": st["units"],
            "pick": st.get("last_pick"), "scores": st.get("last_scores")}
