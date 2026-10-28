#!/usr/bin/env python3
"""Backtest all 10 strategies (+ ensemble) on your symbols and rank them.

  python backtest.py                       # all strategies, symbols/dates from config.yaml
  python backtest.py --only supertrend macd
  python backtest.py --start 2015-01-01 --oos 0.3
  python backtest.py --demo                # offline: synthetic prices, just to check the plumbing
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from tradebot import backtest as bt
from tradebot import data as data_mod
from tradebot import strategies
from tradebot.costs import CostModel


def synthetic(symbols, start, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, pd.Timestamp.today().normalize())
    out = {}
    for s in symbols:
        # regime-switching random walk so trend AND mean-reversion rules both get exercised
        drift = np.repeat(rng.choice([-0.0008, 0.0002, 0.0012], size=len(idx) // 120 + 1), 120)[: len(idx)]
        r = drift + rng.normal(0, 0.016, len(idx))
        close = 100 * np.exp(np.cumsum(r))
        open_ = close * np.exp(rng.normal(0, 0.004, len(idx)))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, len(idx))))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, len(idx))))
        out[s] = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                               "volume": rng.integers(1e5, 1e6, len(idx))}, index=idx)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--start", help="override backtest.start")
    ap.add_argument("--end")
    ap.add_argument("--only", nargs="*", help="strategy names to run")
    ap.add_argument("--oos", type=float, help="fraction of the period held out as out-of-sample (default from config)")
    ap.add_argument("--demo", action="store_true", help="use synthetic data (no internet needed)")
    a = ap.parse_args()

    cfg = yaml.safe_load(open(a.config))
    bcfg = cfg.get("backtest", {})
    start = a.start or bcfg.get("start", "2015-01-01")
    end = a.end or bcfg.get("end")
    capital = float(cfg["capital"])
    costs = CostModel.from_config(cfg.get("costs"))
    oos_frac = a.oos if a.oos is not None else bcfg.get("oos_fraction", 0.3)
    rf = bcfg.get("risk_free_rate", 0.065)

    if a.demo:
        data = synthetic(cfg["symbols"], start)
    else:
        data = {}
        for s in cfg["symbols"]:
            try:
                data[s] = data_mod.load(s, cfg.get("data", {}), start, end)
                print(f"loaded {s}: {len(data[s])} days {data[s].index[0].date()} -> {data[s].index[-1].date()}")
            except Exception as e:
                print(f"skip {s}: {e}")
    if not data:
        raise SystemExit("No data loaded.")

    dates = sorted(set().union(*[df.index for df in data.values()]))
    oos_start = dates[int(len(dates) * (1 - oos_frac))] if oos_frac else None

    names = a.only or list(strategies.ALL)
    rows = [bt.summarize("buy_and_hold", bt.buy_and_hold(data, capital, costs), oos_start, rf)]
    curves = {"buy_and_hold": None}
    for n in names:
        res = bt.run_portfolio(data, strategies.get(n, (cfg.get("strategy_params_all") or {}).get(n)), capital, costs)
        rows.append(bt.summarize(n, res, oos_start, rf))
        curves[n] = res.equity
    curves["buy_and_hold"] = bt.buy_and_hold(data, capital, costs).equity

    table = pd.DataFrame(rows).set_index("strategy").sort_values("sharpe", ascending=False)
    Path("results").mkdir(exist_ok=True)
    table.to_csv("results/backtest_summary.csv")
    pd.DataFrame(curves).to_csv("results/equity_curves.csv")

    fmt = table.copy()
    for c in ["total_return", "cagr", "max_drawdown", "win_rate", "exposure", "oos_cagr"]:
        if c in fmt:
            fmt[c] = fmt[c].map(lambda v: "" if pd.isna(v) else f"{v:.1%}")
    for c in ["sharpe", "oos_sharpe"]:
        if c in fmt:
            fmt[c] = fmt[c].map(lambda v: "" if pd.isna(v) else f"{v:.2f}")
    fmt["charges_rs"] = fmt["charges_rs"].map(lambda v: f"{v:,.0f}")
    print(f"\nCapital Rs {capital:,.0f} | {len(data)} symbols | {start} -> {dates[-1].date()} | "
          f"out-of-sample from {oos_start.date() if oos_start is not None else '-'}" + (" | DEMO DATA" if a.demo else ""))
    print(fmt.to_string())
    print("\nSaved results/backtest_summary.csv and results/equity_curves.csv")
    print("Pick a strategy on the in-sample columns, then check it still works in oos_* before trusting it.")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ax = pd.DataFrame(curves).plot(figsize=(12, 6), logy=True, lw=1)
        if oos_start is not None:
            ax.axvline(oos_start, color="k", ls="--", lw=1)
        ax.set_title("Equity curves (log scale), after Zerodha charges")
        plt.tight_layout()
        plt.savefig("results/equity_curves.png", dpi=120)
        print("Saved results/equity_curves.png")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
