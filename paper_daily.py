#!/usr/bin/env python3
"""One daily paper-trading run on LIVE market data (run after 17:00 IST on trading days).

Three paper bots, each with fake money, all driven by real prices from Yahoo Finance:
  swing     : daily trend bot (config.yaml strategy) on 10 large caps
  momentum  : monthly Nifty 500 momentum rotation (top 20, 200-day regime filter)
  intraday  : the live ORB bot code replayed on TODAY's real 1-minute candles
Plus a Nifty 50 buy-and-hold benchmark started on the same day.

Writes everything under paper/: state per bot, trade journals, history.csv and REPORT.md.
Safe to re-run: each bot skips a day it has already processed.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from tradebot import live_data
from tradebot.intraday.data import MINUTES
from tradebot.intraday.live import OrbConfig
from tradebot.intraday.sim import replay_day
from tradebot.momentum import MomParams
from tradebot.paper_momentum import run_day as momentum_day
from tradebot.runner import run as swing_run

ROOT = Path("paper")
log = logging.getLogger("paper")


def _done(bot: str, day) -> bool:
    f = ROOT / bot / "last_day.txt"
    return f.exists() and f.read_text().strip() >= str(pd.Timestamp(day).date())


def _mark(bot: str, day):
    (ROOT / bot).mkdir(parents=True, exist_ok=True)
    (ROOT / bot / "last_day.txt").write_text(str(pd.Timestamp(day).date()))


# ------------------------------------------------------------------ bots
def swing(cfg_all) -> dict:
    cfg = yaml.safe_load(open("config.yaml"))
    cfg |= {"mode": "paper", "capital": cfg_all["capital"]["swing"], "state_dir": str(ROOT / "swing")}
    data = live_data.daily(cfg["symbols"], period="3y")
    if not data:
        return {"status": "no_data"}
    day = max(d.index[-1] for d in data.values())
    if _done("swing", day):
        return {"status": "already_done", "date": str(day.date())}
    out = swing_run(cfg, as_of=day, preloaded=data)
    _mark("swing", day)
    return out


def momentum(cfg_all) -> dict:
    syms = [s.strip() for s in open("universe_n500.txt") if s.strip()]
    data = live_data.daily(syms, period="2y")
    idx = live_data.daily(["^CRSLDX"], period="2y").get("^CRSLDX")
    if not data or idx is None:
        return {"status": "no_data"}
    opens = pd.DataFrame({s: d.open for s, d in data.items()})
    closes = pd.DataFrame({s: d.close for s, d in data.items()})
    vols = pd.DataFrame({s: d.volume for s, d in data.items()})
    day = closes.index[-1]
    if _done("momentum", day):
        return {"status": "already_done", "date": str(day.date())}
    out = momentum_day(ROOT / "momentum" / "state.json", opens, closes, vols, idx.close,
                       MomParams(**cfg_all.get("momentum_params", {})), cfg_all["capital"]["momentum"])
    _mark("momentum", day)
    return out


def intraday(cfg_all) -> dict:
    icfg = yaml.safe_load(open("config_intraday.yaml"))
    syms = icfg["symbols"]
    m1 = live_data.intraday(syms, "1m", "5d")
    m5 = live_data.intraday(syms, "5m", "60d")
    if not m1:
        return {"status": "no_data"}
    day = max(d.index[-1] for d in m1.values()).normalize()
    if _done("intraday", day):
        return {"status": "already_done", "date": str(day.date())}
    uni = {}
    for s in syms:
        if s not in m1 or s not in m5:
            continue
        g_today = live_data.minute_grid(m1[s], day)
        if g_today is None:
            continue
        prior = m5[s][m5[s].index.normalize() < day]
        days, grids = [], []
        for d, bars in prior.groupby(prior.index.normalize()):
            g = _grid_from_5m(bars)
            if g is not None:
                days.append(d)
                grids.append(g)
        if len(days) < 15:
            continue
        days.append(day)
        grids.append(g_today)
        uni[s] = (pd.DatetimeIndex(days), np.stack(grids))
    if not uni:
        return {"status": "no_data"}
    eq_file = ROOT / "intraday" / "equity.json"
    eq = json.loads(eq_file.read_text()) if eq_file.exists() else []
    capital = eq[-1]["equity"] if eq else cfg_all["capital"]["intraday"]
    fields = {k: v for k, v in icfg.items() if k in OrbConfig.__dataclass_fields__}
    fields |= {"symbols": sorted(uni), "capital": capital, "state_dir": str(ROOT / "intraday")}
    bot = replay_day(uni, day, OrbConfig(**fields), slip_bps=cfg_all.get("intraday_slip_bps", 3.0))
    pnl = getattr(bot, "day_pnl", 0.0)
    eq.append({"date": str(day.date()), "equity": round(capital + pnl, 2), "pnl": round(pnl, 2),
               "trades": sum(l.status == "DONE" for l in bot.legs.values()), "halt": bot.halt_reason})
    eq_file.parent.mkdir(parents=True, exist_ok=True)
    eq_file.write_text(json.dumps(eq, indent=1))
    _mark("intraday", day)
    return {"status": "ok", "date": str(day.date()), "pnl": round(pnl, 2), "equity": round(capital + pnl, 2),
            "trades": [{"symbol": l.symbol, "side": l.side, "qty": l.qty, "entry": l.entry_price, "exit": l.exit_price,
                        "reason": l.exit_reason} for l in bot.legs.values() if l.status == "DONE"]}


def _grid_from_5m(bars: pd.DataFrame):
    """Expand a day of 5-minute bars into a 375-minute grid (enough for daily OHLC + first-5-min volume)."""
    m = (bars.index.hour - 9) * 60 + bars.index.minute - 15
    bars = bars[(m >= 0) & (m < MINUTES)]
    if len(bars) < 60:
        return None
    m = (bars.index.hour - 9) * 60 + bars.index.minute - 15
    g = np.full((MINUTES, 5), np.nan, dtype=np.float32)
    for mi, (_, r) in zip(m, bars.iterrows()):
        g[mi:mi + 5, :4] = [r.open, r.high, r.low, r.close]
        g[mi:mi + 5, 4] = r.volume / 5
    last = g[0, 0] if np.isfinite(g[0, 0]) else bars.open.iloc[0]
    for i in range(MINUTES):
        if np.isnan(g[i, 3]):
            g[i, :4], g[i, 4] = last, 0
        else:
            last = g[i, 3]
    return g


def benchmark(cfg_all) -> dict:
    idx = live_data.daily(["^NSEI"], period="1mo").get("^NSEI")
    if idx is None:
        return {"status": "no_data"}
    f = ROOT / "benchmark.json"
    st = json.loads(f.read_text()) if f.exists() else {}
    if "start_close" not in st:
        st = {"start_date": str(idx.index[-1].date()), "start_close": float(idx.close.iloc[-1])}
    st["last_date"], st["last_close"] = str(idx.index[-1].date()), float(idx.close.iloc[-1])
    f.write_text(json.dumps(st, indent=1))
    return st


# ------------------------------------------------------------------ report
def report(cfg_all, results: dict):
    if not any(isinstance(r, dict) and r.get("status") in ("ok", "error", "killed", "no_new_bar") for k, r in results.items()
               if k != "benchmark"):
        print("Nothing new today (holiday/weekend or already processed); report unchanged.")
        return
    cap = cfg_all["capital"]
    rows = []
    hist_f = ROOT / "history.csv"
    hist = pd.read_csv(hist_f) if hist_f.exists() else pd.DataFrame()
    bm = results.get("benchmark", {})
    date = max([r.get("date", "") for r in results.values() if isinstance(r, dict)] + [bm.get("last_date", "")])
    def eq_of(name):
        r = results.get(name, {})
        if r.get("equity") is not None:
            return r["equity"]
        return hist[name].dropna().iloc[-1] if name in hist and hist[name].notna().any() else cap[name]
    row = {"date": date, "swing": eq_of("swing"), "momentum": eq_of("momentum"), "intraday": eq_of("intraday"),
           "nifty50": bm.get("last_close")}
    if not hist.empty and str(hist.date.iloc[-1]) == date:
        hist = hist.iloc[:-1]
    hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
    hist.to_csv(hist_f, index=False)

    n0 = bm.get("start_close")
    lines = [f"# Paper trading report: {date}", "",
             "Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund "
             f"since {bm.get('start_date')}.", "",
             "| Bot | Start capital | Equity now | Return | Nifty 50 same period |", "|---|---|---|---|---|"]
    nret = (bm["last_close"] / n0 - 1) if n0 else float("nan")
    for name in ("swing", "momentum", "intraday"):
        e = row[name]
        lines.append(f"| {name} | ₹{cap[name]:,.0f} | ₹{e:,.0f} | {e / cap[name] - 1:+.2%} | {nret:+.2%} |")
    lines += ["", "## Today", ""]
    for name in ("swing", "momentum", "intraday"):
        r = results.get(name, {})
        lines.append(f"**{name}**: {r.get('status')}")
        if name == "swing" and r.get("orders"):
            lines += [f"- {o['side']} {o['symbol']} x{o['qty']} (AMO limit {o['limit']})" for o in r["orders"]]
        if name == "momentum":
            if r.get("regime"):
                lines.append(f"- regime: {r['regime']}")
            lines += [f"- {o['side']} {o['symbol']} x{o['qty']} @ {o['price']}" for o in r.get("orders", [])]
            if r.get("positions"):
                lines.append(f"- holding {len(r['positions'])}: {', '.join(sorted(r['positions']))}")
        if name == "intraday":
            for t in r.get("trades", []):
                lines.append(f"- {t['side']} {t['symbol']} x{t['qty']} {t['entry']} -> {t['exit']} ({t['reason']})")
            if r.get("pnl") is not None:
                lines.append(f"- day P&L ₹{r['pnl']:,.0f}")
        if r.get("error"):
            lines.append(f"- ERROR: {r['error']}")
        lines.append("")
    lines += ["Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, "
              "`paper/intraday/journal.csv`."]
    (ROOT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config_paper.yaml")
    ap.add_argument("--only", nargs="*", choices=["swing", "momentum", "intraday"])
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    cfg_all = yaml.safe_load(open(a.config))
    ROOT.mkdir(exist_ok=True)
    results = {}
    for name, fn in (("swing", swing), ("momentum", momentum), ("intraday", intraday)):
        if a.only and name not in a.only:
            continue
        try:
            results[name] = fn(cfg_all)
        except Exception as e:  # one bot failing must not stop the others
            log.exception("%s failed", name)
            results[name] = {"status": "error", "error": repr(e)}
    try:
        results["benchmark"] = benchmark(cfg_all)
    except Exception as e:
        results["benchmark"] = {"status": "error", "error": repr(e)}
    report(cfg_all, results)


if __name__ == "__main__":
    main()
