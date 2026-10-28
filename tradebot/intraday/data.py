"""1-minute NSE data -> per-day minute grids.

Grid shape: (days, 375, 5) float32 with fields open, high, low, close, volume for minutes
09:15 .. 15:29. Missing minutes are forward-filled with zero volume. Special sessions
(Muhurat, half days with < 300 bars) are dropped.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MINUTES = 375  # 09:15 -> 15:29
O, H, L, C, V = range(5)


def minute_index(ts: pd.Series) -> np.ndarray:
    return ((ts.dt.hour - 9) * 60 + ts.dt.minute - 15).to_numpy()


def build_grid(csv_path: str | Path, cache_dir: str | Path = ".cache/grids"):
    cache = Path(cache_dir) / (Path(csv_path).name.split(".")[0] + ".npz")
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        return pd.DatetimeIndex(z["days"]), clean_grid(z["grid"].copy())
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df["date"] = df["date"].dt.floor("min")
    m = minute_index(df["date"])
    df = df[(m >= 0) & (m < MINUTES)].copy()
    df["m"] = minute_index(df["date"])
    df["day"] = df["date"].dt.normalize()
    counts = df.groupby("day").size()
    good = counts[counts >= 300].index
    df = df[df["day"].isin(good)].drop_duplicates(["day", "m"], keep="last")
    days = pd.DatetimeIndex(sorted(good))
    di = days.get_indexer(df["day"])
    grid = np.full((len(days), MINUTES, 5), np.nan, dtype=np.float32)
    grid[di, df["m"].to_numpy(), :] = df[["open", "high", "low", "close", "volume"]].to_numpy(np.float32)
    # forward-fill missing minutes inside each day
    for d in range(len(days)):
        g = grid[d]
        miss = np.isnan(g[:, C])
        if not miss.any():
            continue
        last = np.nan
        for i in range(MINUTES):
            if miss[i]:
                if np.isnan(last):  # leading gap: back-fill from first real bar
                    nxt = np.argmax(~miss)
                    last = g[nxt, O]
                g[i, :4] = last
                g[i, V] = 0
            else:
                last = g[i, C]
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, days=days.values.astype("datetime64[ns]"), grid=grid)
    return days, clean_grid(grid)


def clean_grid(grid: np.ndarray, max_dev: float = 0.12) -> np.ndarray:
    """Replace bad prints: any minute whose price is >12% away from that day's median close
    (Nifty 50 stocks essentially never move that far intraday) becomes a flat bar at the prior close."""
    med = np.nanmedian(grid[:, :, C], axis=1)[:, None, None]
    bad = (np.abs(grid[:, :, :4] / med - 1) > max_dev).any(axis=2)
    for d, i in zip(*np.nonzero(bad)):
        prev = grid[d, i - 1, C] if i > 0 else med[d, 0, 0]
        grid[d, i, :4] = prev
        grid[d, i, V] = 0
    return grid


def daily_from_grid(grid: np.ndarray) -> np.ndarray:
    """(days, 5) daily OHLCV built from the minute grid."""
    return np.stack([grid[:, 0, O], grid[:, :, H].max(1), grid[:, :, L].min(1), grid[:, -1, C], grid[:, :, V].sum(1)], 1)
