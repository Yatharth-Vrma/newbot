#!/usr/bin/env python3
"""Backtest intraday ORB strategies on 1-minute NSE data.

  python backtest_intraday.py                       # default grid of variants, 2015-2026
  python backtest_intraday.py --strategy orb5_sip --top-n 5 --stop-atr 0.1
  python backtest_intraday.py --data intraday_data --start 2019-01-01

Data: folder of <SYMBOL>.csv(.gz) with date,open,high,low,close,volume 1-minute rows
(the bundled set is 33 Nifty 50 stocks from Zerodha Kite, Feb 2015 - Oct 2026).
"""
import argparse
import itertools
from pathlib import Path

import pandas as pd

from tradebot.intraday import engine
from tradebot.intraday.data import build_grid


def load_universe(folder, start=None, end=None):
    uni = {}
    for f in sorted(Path(folder).glob("*.csv*")):
        days, grid = build_grid(f)
        m = (days >= pd.Timestamp(start)) if start else slice(None)
        if start or end:
            mask = pd.Series(True, index=days)
            if start: mask &= days >= pd.Timestamp(start)
            if end: mask &= days <= pd.Timestamp(end)
            days, grid = days[mask.values], grid[mask.values]
        uni[f.name.split(".")[0]] = (days, grid)
    return uni


def fmt(row):
    return {k: (f"{v:.1%}" if k in ("cagr", "max_dd", "win_rate", "oos_cagr") else
                f"{v:.2f}" if k in ("sharpe", "oos_sharpe") else
                f"{v:+.3f}" if k.startswith("avg_r") else
                f"{v:,.0f}" if k in ("charges_rs", "gross_rs") else v) for k, v in row.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="intraday_data")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--strategy"); ap.add_argument("--top-n", type=int)
    ap.add_argument("--stop-atr", type=float); ap.add_argument("--target-r", type=float)
    ap.add_argument("--capital", type=float, default=100000)
    ap.add_argument("--oos-start", default="2023-01-01", help="results after this date are out-of-sample")
    ap.add_argument("--entry-bar-rule", default="close", choices=["close", "conservative"])
    a = ap.parse_args()

    uni = load_universe(a.data, a.start, a.end)
    print(f"{len(uni)} stocks loaded")
    if a.strategy:
        variants = [dict(strategy=a.strategy, top_n=a.top_n or 5, stop_atr=a.stop_atr or 0.10, target_r=a.target_r or 2.0)]
    else:
        variants = [dict(strategy="orb5_sip", top_n=n, stop_atr=k) for n, k in itertools.product([3, 5], [0.10, 0.25, 0.50])]
        variants += [dict(strategy="orb15", top_n=n, target_r=r) for n, r in itertools.product([3, 5], [1.5, 2.0, 3.0])]

    rows = []
    out = Path("results/intraday"); out.mkdir(parents=True, exist_ok=True)
    for v in variants:
        p = engine.Params(**v, entry_bar_rule=a.entry_bar_rule)
        eq, tr = engine.run(uni, p, a.capital)
        st = engine.stats(eq, tr)
        oos = engine.stats(eq.loc[a.oos_start:], tr[tr.date >= a.oos_start] if len(tr) else tr)
        name = "_".join(f"{k}={val}" for k, val in v.items())
        rows.append({"variant": name, **st, "oos_cagr": oos["cagr"], "oos_sharpe": oos["sharpe"]})
        tr.to_csv(out / f"trades_{name}.csv", index=False)
        eq.to_csv(out / f"equity_{name}.csv")
        print(fmt(rows[-1]), flush=True)
    t = pd.DataFrame(rows).set_index("variant").sort_values("sharpe", ascending=False)
    t.to_csv(out / "summary.csv")
    print("\n" + pd.DataFrame([fmt(r) for r in t.reset_index().to_dict("records")]).set_index("variant").to_string())


if __name__ == "__main__":
    main()
