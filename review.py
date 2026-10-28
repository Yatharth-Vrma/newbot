#!/usr/bin/env python3
"""Daily review numbers for the paper bots (used by Claude's daily review, or run it yourself).

  python review.py                # reads ./paper
  python review.py path/to/paper
"""
import json
import sys
from pathlib import Path

import pandas as pd

# What the backtests said to expect; live paper results are judged against these.
EXPECT = {
    "intraday": {"win_rate": (0.28, 0.40), "entry_slip_bps": 3.0, "avg_net_per_trade_rs": (-120, 40)},
    "momentum": {"max_dd": -0.45},
    "swing": {"max_dd": -0.30},
}


def main(root="paper"):
    root = Path(root)
    out = []
    h = pd.read_csv(root / "history.csv")
    h["date"] = pd.to_datetime(h["date"])
    last = h.iloc[-1]
    cap = {}
    cfgf = root.parent / "config_paper.yaml"
    if cfgf.exists():
        import yaml
        cap = yaml.safe_load(open(cfgf)).get("capital", {})
    stale_days = (pd.Timestamp.today().normalize() - last.date).days
    out.append(f"Last update {last.date.date()} ({stale_days} days ago){'  <-- STALE: check the GitHub Action' if stale_days > 4 else ''}")
    n = h.nifty50.dropna()
    nifty_ret = n.iloc[-1] / n.iloc[0] - 1 if len(n) > 1 else 0.0
    out.append(f"Nifty 50 since start: {nifty_ret:+.2%} | trading days tracked: {len(h)}")
    for bot in ("momentum", "swing", "intraday"):
        e = h[bot].dropna()
        if e.empty:
            continue
        start = float(cap.get(bot, e.iloc[0]))
        e = pd.concat([pd.Series([start]), e], ignore_index=True)
        dd = (e / e.cummax() - 1).min()
        d1 = e.iloc[-1] / e.iloc[-2] - 1 if len(e) > 1 else 0
        d5 = e.iloc[-1] / e.iloc[-6] - 1 if len(e) > 5 else float("nan")
        flag = ""
        lim = EXPECT.get(bot, {}).get("max_dd")
        if lim is not None and dd < lim:
            flag = "  <-- drawdown worse than backtest"
        out.append(f"{bot:9s} equity {e.iloc[-1]:>12,.0f} | total {e.iloc[-1] / e.iloc[0] - 1:+.2%} vs Nifty {nifty_ret:+.2%} "
                   f"| 1d {d1:+.2%} | 5d {d5:+.2%} | max DD {dd:.1%}{flag}")

    j = root / "intraday" / "journal.csv"
    if j.exists():
        t = pd.read_csv(j)
        if len(t):
            ex = EXPECT["intraday"]
            wr, slip, avg = (t.net > 0).mean(), t.entry_slip_bps.mean(), t.net.mean()
            out.append(f"intraday trades {len(t)} | win rate {wr:.0%} (backtest {ex['win_rate'][0]:.0%}-{ex['win_rate'][1]:.0%}) "
                       f"| avg net/trade Rs {avg:,.0f} | gross P&L Rs {t.gross.sum():,.0f}, charges Rs {t.charges.sum():,.0f} "
                       f"| entry slippage {slip:.1f} bps (assumed {ex['entry_slip_bps']})")
            out.append("  by exit: " + ", ".join(f"{k} {v}" for k, v in t.reason.value_counts().items()))
            last_day = t[t.date == t.date.max()]
            for _, r in last_day.iterrows():
                out.append(f"  {r.date} {r.side} {r.symbol} x{r.qty} {r.entry} -> {r.exit} {r.reason} net Rs {r.net:,.0f}")

    m = root / "momentum" / "state.json"
    if m.exists():
        s = json.loads(m.read_text())
        out.append(f"momentum: {s.get('last_regime')} | {len(s['positions'])} positions | cash Rs {s['cash']:,.0f} "
                   f"| last rebalance {s.get('last_rebalance_month')}")
        if s["positions"]:
            out.append("  holding: " + ", ".join(sorted(s["positions"])))
        sells = [f for f in s["fills"] if f["side"] == "SELL"]
        if sells:
            wins = sum(f["pnl"] > 0 for f in sells)
            out.append(f"  closed positions {len(sells)}, winners {wins} ({wins / len(sells):.0%}), "
                       f"realised Rs {sum(f['pnl'] for f in sells):,.0f}")

    ef = root / "etf" / "state.json"
    if ef.exists():
        s2 = json.loads(ef.read_text())
        if s2["equity"]:
            e = s2["equity"][-1]
            out.append(f"etf SIP: invested Rs {e['invested']:,.0f} -> Rs {e['value']:,.0f} ({e['value'] / e['invested'] - 1:+.2%}) "
                       f"vs same SIP in NIFTYBEES Rs {e['nifty_sip_value']:,.0f} | pick {s2.get('last_pick')} | holding {s2['units']}")
    sj = root / "swing" / "journal_paper.csv"
    if sj.exists():
        t = pd.read_csv(sj)
        if len(t):
            r = t.iloc[-1]
            longs = [x.split("=")[0] for x in str(r.signals).split(";") if x.endswith("=1")]
            out.append(f"swing: in {len(longs)} stocks ({', '.join(longs) or 'none'}) | last orders: {r.orders if isinstance(r.orders, str) else 'none'}")
    rep = root / "REPORT.md"
    if rep.exists() and "ERROR" in rep.read_text():
        out.append("ERRORS in the last run, see paper/REPORT.md")
    print("\n".join(out))


if __name__ == "__main__":
    main(*sys.argv[1:])
