#!/usr/bin/env python3
"""Intraday ORB bot for Zerodha (MIS). Start it at ~09:00 IST on a trading day; it exits by itself.

  python run_intraday.py --paper      # real Kite prices, simulated orders (DEFAULT RECOMMENDATION)
  TRADEBOT_LIVE=YES python run_intraday.py --live --capital 25000   # real money

Needs: KITE_API_KEY env var, today's token from `python kite_login.py`, a Kite Connect plan with
market data (Rs 500/month), and (live) your static IP whitelisted in the Kite app (SEBI rule).
Settings: config_intraday.yaml
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

from tradebot.intraday.live import KiteAdapter, OrbBot, OrbConfig, PaperAdapter, run_forever


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--paper", action="store_true")
    g.add_argument("--live", action="store_true")
    ap.add_argument("--config", default="config_intraday.yaml")
    ap.add_argument("--capital", type=float)
    a = ap.parse_args()

    raw = yaml.safe_load(open(a.config))
    if a.capital:
        raw["capital"] = a.capital
    mode = "live" if a.live else "paper"
    raw["state_dir"] = f"{raw.get('state_dir', 'state/intraday')}/{mode}"
    cfg = OrbConfig(**raw)
    Path(cfg.state_dir).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(Path(cfg.state_dir) / "bot.log")])

    if a.live and os.environ.get("TRADEBOT_LIVE") != "YES":
        sys.exit("Refusing live mode: set TRADEBOT_LIVE=YES to confirm real-money trading.")
    token_file = Path("state/access_token.txt")
    if not token_file.exists():
        sys.exit("No access token. Run `python kite_login.py` first (daily 2FA).")
    key, token = os.environ["KITE_API_KEY"], token_file.read_text().strip()
    adapter = KiteAdapter(key, token) if a.live else PaperAdapter(key, token)
    if (Path(cfg.state_dir) / "HALT").exists():
        sys.exit(f"{cfg.state_dir}/HALT exists; delete it to trade again.")
    run_forever(OrbBot(cfg, adapter))


if __name__ == "__main__":
    main()
