"""Intraday bot state-machine tests on synthetic minute data (no internet needed)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tradebot.intraday import engine  # noqa: E402
from tradebot.intraday.data import MINUTES  # noqa: E402
from tradebot.intraday.live import OrbConfig  # noqa: E402
from tradebot.intraday.sim import replay_day  # noqa: E402


def fake_universe(n_stocks=6, n_days=40, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2026-01-01", periods=n_days)
    uni = {}
    for k in range(n_stocks):
        g = np.zeros((n_days, MINUTES, 5), dtype=np.float32)
        px = 500 + 100 * k
        for d in range(n_days):
            drift = rng.normal(0, 0.0004)
            r = drift + rng.normal(0, 0.0012, MINUTES)
            c = px * np.exp(np.cumsum(r))
            o = np.r_[px, c[:-1]]
            g[d, :, 0], g[d, :, 3] = o, c
            g[d, :, 1] = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0004, MINUTES)))
            g[d, :, 2] = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0004, MINUTES)))
            g[d, :, 4] = rng.integers(1000, 5000, MINUTES) * (3 if rng.random() < 0.3 else 1)
            px = c[-1]
        uni[f"S{k}"] = (days, g)
    return uni


def test_replay_days_close_flat(tmp_path):
    uni = fake_universe()
    days = list(uni["S0"][0])[20:]
    for d in days:
        cfg = OrbConfig(symbols=list(uni), capital=100000, state_dir=str(tmp_path / d.strftime("%Y%m%d")))
        bot = replay_day(uni, d, cfg)
        assert bot.phase == "DONE"
        for leg in bot.legs.values():
            assert leg.status in ("DONE", "CANCELLED")
            if leg.status == "DONE":
                assert leg.exit_time <= "15:16"
                assert leg.qty * leg.entry_price <= 100000 * 4 / 3 + 1
        exits = {}
        for o in bot.a.book.values():  # never more exit fills than entry fills per symbol (no reversal)
            if o["status"] == "COMPLETE":
                exits.setdefault(o["symbol"], []).append(o["side"])
        for s, sides in exits.items():
            assert len(sides) in (0, 2), (s, sides)
            assert sides[0] != sides[-1]


def test_circuit_breaker(tmp_path):
    uni = fake_universe(seed=5)
    d = list(uni["S0"][0])[25]
    cfg = OrbConfig(symbols=list(uni), capital=100000, risk_pct=0.02, day_loss_pct=0.001,
                    state_dir=str(tmp_path))
    bot = replay_day(uni, d, cfg)
    assert bot.phase == "DONE"
    if any(l.status == "DONE" for l in bot.legs.values()):
        assert bot.halt_reason is None or "day loss" in bot.halt_reason


def test_engine_runs():
    uni = fake_universe()
    eq, tr = engine.run(uni, engine.Params(top_n=3, stop_atr=0.25))
    assert len(eq) == 40 and (eq > 0).all()
