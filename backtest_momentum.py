#!/usr/bin/env python3
"""Backtest the monthly Nifty 500 momentum rotation (2006-2026) with Zerodha charges and Indian tax.

  python get_research_data.py        # once: Nifty 500 daily history into data_n500/
  python backtest_momentum.py

Caveat: the data covers stocks in the Nifty 500 TODAY (no delisted names), which flatters every
strategy. Compare against the equal-weight column (same bias) and the real Nifty200 Momentum 30
index (18.8%/yr vs 13.9% for Nifty 200 TRI, Apr 2005 - Jun 2026) rather than trusting the raw CAGR.
"""
import pandas as pd

from tradebot.momentum import MomParams, backtest, load_panel, perf

O, C, V = load_panel("data_n500")
idx = pd.read_csv("data_n500/_NIFTY500.idx", index_col=0, parse_dates=True).close
rows = {}
for name, kw in {"momentum top20 + regime filter": dict(hold_n=20, buffer_rank=40, regime_filter=True),
                 "momentum top20, no filter": dict(hold_n=20, buffer_rank=40, regime_filter=False),
                 "momentum top30 + regime filter": dict(hold_n=30, buffer_rank=60, regime_filter=True)}.items():
    eq, tr = backtest(O, C, V, idx, MomParams(**kw), start="2006-01-01")
    rows[name] = perf(eq) | {"trades/yr": (tr.side != "TAX").sum() / 20.8}
r = C.loc["2006-01-01":].pct_change(fill_method=None).clip(-0.5, 1)
rows["equal-weight same 500 (no costs/tax)"] = perf((1 + r.mean(axis=1).fillna(0)).cumprod())
rows["Nifty 500 index (price only)"] = perf(idx.loc["2006-01-01":])
t = pd.DataFrame(rows).T
for c in ["cagr", "max_dd", "vol"]:
    t[c] = t[c].map("{:.1%}".format)
t["sharpe"] = t["sharpe"].map("{:.2f}".format)
print(t.to_string())
