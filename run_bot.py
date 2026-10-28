#!/usr/bin/env python3
"""Run the bot.

  python run_bot.py                         # one run for today (schedule daily ~16:30 IST)
  python run_bot.py --catch-up              # paper: replay every trading day since the last run
  python run_bot.py --catch-up --since 2026-01-01   # paper: start a paper account on a past date
  python run_bot.py --force                 # run even if today's candle isn't there (testing)
  TRADEBOT_LIVE=YES python run_bot.py --config config.live.yaml   # real money (daily only)

Catch-up gives exactly the same result as running every evening, because each replayed
day only sees candles up to that day and orders fill at the next day's open.
"""
import argparse
import datetime as dt
import logging
from pathlib import Path

import pandas as pd
import yaml

from tradebot import data as data_mod
from tradebot.runner import run


def catch_up(cfg, since):
    if cfg["mode"] != "paper":
        raise SystemExit("--catch-up is for paper mode only (live orders can't be placed in the past).")
    state = Path(cfg.get("state_dir", "state"))
    journal = state / "journal_paper.csv"
    if journal.exists():
        last = pd.read_csv(journal)["date"].iloc[-1]
        begin = pd.Timestamp(last) + pd.Timedelta(days=1)
    elif since:
        begin = pd.Timestamp(since)
    else:
        raise SystemExit("No paper history yet: pass --since YYYY-MM-DD to choose the paper start date.")
    load_from = (begin - pd.Timedelta(days=int(cfg.get("lookback_days", 800)))).date().isoformat()
    data = {}
    for s in cfg["symbols"]:
        try:
            data[s] = data_mod.load(s, cfg.get("data", {}), load_from)
        except Exception as e:
            logging.warning("skip %s: %s", s, e)
    days = sorted(set().union(*[df.index for df in data.values()]))
    days = [d for d in days if d >= begin]
    if not days:
        logging.info("Already up to date (latest candle %s).", max(df.index[-1] for df in data.values()).date())
        return
    logging.info("Replaying %d trading days %s -> %s", len(days), days[0].date(), days[-1].date())
    out = None
    for d in days:
        out = run(cfg, as_of=d, preloaded=data)
        if out["status"] in ("halted", "killed"):
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--catch-up", action="store_true")
    ap.add_argument("--since")
    ap.add_argument("--quiet", action="store_true", help="only log warnings and the final summary")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config))
    Path(cfg.get("state_dir", "state")).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.WARNING if a.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(Path(cfg.get("state_dir", "state")) / "bot.log")],
    )
    out = catch_up(cfg, a.since) if a.catch_up else run(cfg, force=a.force)
    if a.quiet and out:
        print(out)


if __name__ == "__main__":
    main()
