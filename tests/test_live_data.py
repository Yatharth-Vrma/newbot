"""Yahoo response parsing (offline, synthetic frames shaped like yfinance output)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradebot import live_data  # noqa: E402


def yf_like(tickers, index):
    cols = pd.MultiIndex.from_product([tickers, ["Open", "High", "Low", "Close", "Volume"]], names=["Ticker", "Price"])
    data = np.tile([100.0, 101.0, 99.0, 100.5, 1000.0], (len(index), len(tickers)))
    return pd.DataFrame(data, index=index, columns=cols)


def test_split_daily():
    idx = pd.date_range("2026-10-01", periods=5, freq="B")
    out = live_data._split(yf_like(["RELIANCE.NS", "M&M.NS"], idx), ["RELIANCE", "M&M", "MISSING"])
    assert set(out) == {"RELIANCE", "M&M"}
    assert list(out["RELIANCE"].columns) == ["open", "high", "low", "close", "volume"]


def test_complete_days_drops_unfinished_today():
    idx = pd.date_range("2026-10-27", periods=3, freq="D")  # 27, 28, 29 Oct
    d = pd.DataFrame({"close": [1.0, 2.0, 3.0]}, index=idx)
    assert live_data.complete_days(d, pd.Timestamp("2026-10-29 11:00")).index[-1] == pd.Timestamp("2026-10-28")
    assert live_data.complete_days(d, pd.Timestamp("2026-10-29 17:15")).index[-1] == pd.Timestamp("2026-10-29")


def test_minute_grid_tz():
    idx = pd.date_range("2026-10-28 09:15", periods=375, freq="min", tz="Asia/Kolkata")
    out = live_data._split(yf_like(["INFY.NS"], idx), ["INFY"])
    g = live_data.minute_grid(out["INFY"].drop(out["INFY"].index[[10, 11]]), pd.Timestamp("2026-10-28"))
    assert g.shape == (375, 5) and not np.isnan(g).any()
    assert g[10, 4] == 0  # filled gap has zero volume
