"""Run: python -m pytest -q   (from the project root)"""
import datetime as dt
import sys
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest import synthetic  # noqa: E402
from tradebot import backtest as bt, strategies, runner  # noqa: E402
from tradebot.costs import CostModel  # noqa: E402


@pytest.fixture(scope="module")
def df():
    return synthetic(["X"], "2016-01-01", seed=3)["X"]


@pytest.mark.parametrize("name", list(strategies.ALL))
def test_no_lookahead(df, name):
    """A signal on day t must not change when future candles are added."""
    fn = strategies.get(name)
    full = fn(df)
    cut = len(df) - 300
    partial = fn(df.iloc[:cut])
    pd.testing.assert_series_equal(full.iloc[:cut], partial, check_names=False)
    assert set(full.unique()) <= {0.0, 1.0}


def test_costs_round_trip():
    c = CostModel()
    buy = c.charges("BUY", 100, 1000)   # Rs 1 lakh
    sell = c.charges("SELL", 100, 1000)
    # STT 100 + stamp 15 + exchange ~3 + GST ~0.5 ; sell adds DP charge
    assert 115 < buy < 125
    assert 115 < sell < 125
    assert c.fill_price("BUY", 100) > 100 > c.fill_price("SELL", 100)


def test_backtest_never_negative_cash(df):
    res = bt.run_symbol(df, strategies.get("ema_cross")(df), 50_000, CostModel())
    assert (res.equity > 0).all()
    assert len(res.trades) > 5


def test_paper_bot_end_to_end(tmp_path, df):
    """Simulate 60 consecutive daily runs of the paper bot and check it trades and stays consistent."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    full = {s: synthetic([s], "2019-01-01", seed=i)[s] for i, s in enumerate(["AAA", "BBB", "CCC"])}
    cfg = {
        "mode": "paper", "capital": 300000, "symbols": list(full), "strategy": "ema_cross",
        "data": {"source": "csv", "csv_folder": str(data_dir)}, "lookback_days": 5000,
        "state_dir": str(tmp_path / "state"),
        "risk": {"max_position_pct": 0.4, "max_drawdown_pct": 0.9, "max_daily_loss_pct": 0.5},
    }
    days = full["AAA"].index[-60:]
    n_orders = 0
    for d in days:
        for s, frame in full.items():
            frame.loc[:d].to_csv(data_dir / f"{s}.csv", index_label="date")

        class FakeDT(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return dt.datetime(d.year, d.month, d.day, 16, 30, tzinfo=tz)

        with mock.patch.object(runner.dt, "datetime", FakeDT):
            out = runner.run(cfg)
        assert out["status"] == "ok", out
        assert out["cash"] >= 0
        n_orders += len(out["orders"])
    assert n_orders > 0
    journal = pd.read_csv(tmp_path / "state" / "journal_paper.csv")
    assert len(journal) == 60


def test_kill_switch(tmp_path):
    full = synthetic(["AAA"], "2019-01-01", seed=1)["AAA"]
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    full.to_csv(data_dir / "AAA.csv", index_label="date")
    state = tmp_path / "state"
    cfg = {"mode": "paper", "capital": 100000, "symbols": ["AAA"], "strategy": "ema_cross",
           "data": {"source": "csv", "csv_folder": str(data_dir)}, "lookback_days": 5000,
           "state_dir": str(state), "risk": {"max_drawdown_pct": 0.10}}
    state.mkdir()
    (state / "paper.json").write_text('{"cash": 80000, "positions": {}, "pending": [], "fills": [], "peak_equity": 100000}')
    out = runner.run(cfg, force=True)
    assert out["status"] == "killed"
    assert (state / "HALT").exists()
    assert runner.run(cfg, force=True)["status"] == "halted"
