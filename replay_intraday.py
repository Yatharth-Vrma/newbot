#!/usr/bin/env python3
"""Run the LIVE intraday bot code on past days (simulated exchange, real 1-minute data).

  python replay_intraday.py --from 2026-09-01 --to 2026-10-19
Writes state/replay/journal.csv (same format the live bot writes).
"""
import argparse
import logging
import shutil
from pathlib import Path

import pandas as pd

from backtest_intraday import load_universe
from tradebot.intraday.live import OrbConfig
from tradebot.intraday.sim import replay_day


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="intraday_data")
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", required=True)
    ap.add_argument("--capital", type=float, default=100000)
    ap.add_argument("--slip-bps", type=float, default=3.0)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(message)s")
    start = (pd.Timestamp(a.frm) - pd.Timedelta(days=45)).date().isoformat()
    uni = load_universe(a.data, start, a.to)
    state = Path("state/replay")
    shutil.rmtree(state, ignore_errors=True)
    days = sorted(set().union(*[set(d) for d, _ in uni.values()]))
    days = [d for d in days if d >= pd.Timestamp(a.frm)]
    equity = a.capital
    rows = []
    for d in days:
        cfg = OrbConfig(symbols=sorted(uni), capital=equity, state_dir=str(state))
        bot = replay_day(uni, d, cfg, slip_bps=a.slip_bps)
        pnl = getattr(bot, "day_pnl", 0.0)
        equity += pnl
        rows.append((d.date(), len([l for l in bot.legs.values() if l.status == "DONE"]), round(pnl), round(equity)))
        print(f"{d.date()}  trades {rows[-1][1]}  P&L {pnl:+8.0f}  equity {equity:10,.0f}" + (f"  HALT: {bot.halt_reason}" if bot.halt_reason else ""))
    j = state / "journal.csv"
    if j.exists():
        t = pd.read_csv(j)
        print(f"\n{len(t)} trades | net Rs {t.net.sum():,.0f} | gross Rs {t.gross.sum():,.0f} | charges Rs {t.charges.sum():,.0f} "
              f"| win rate {(t.net > 0).mean():.0%} | avg entry slippage {t.entry_slip_bps.mean():.1f} bps")
        print(t.reason.value_counts().to_string())


if __name__ == "__main__":
    main()
