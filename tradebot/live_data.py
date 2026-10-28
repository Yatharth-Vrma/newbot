"""Free live market data from Yahoo Finance (works on GitHub Actions, a VPS or your laptop).

NSE symbols are mapped to Yahoo with a ".NS" suffix (M&M -> M&M.NS, BAJAJ-AUTO -> BAJAJ-AUTO.NS).
Yahoo keeps 1-minute candles for the last ~7 days and 5-minute candles for ~60 days.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .intraday.data import MINUTES


def yahoo(sym: str) -> str:
    return sym if sym.startswith("^") or sym.endswith(".NS") else f"{sym}.NS"


def _download(tickers, retries=3, **kw):
    import yfinance as yf

    for k in range(retries):
        try:
            df = yf.download(tickers, group_by="ticker", auto_adjust=True, progress=False, threads=True, **kw)
            if not df.empty:
                return df
        except Exception as e:  # network hiccup: back off and retry
            print(f"yfinance error ({e}); retry {k + 1}/{retries}")
        time.sleep(5 * (k + 1))
    return pd.DataFrame()


def _split(df: pd.DataFrame, symbols, tz_naive=True) -> dict[str, pd.DataFrame]:
    out = {}
    if df.empty:
        return out
    for s in symbols:
        t = yahoo(s)
        if isinstance(df.columns, pd.MultiIndex):
            if t not in df.columns.get_level_values(0):
                continue
            d = df[t].copy()
        else:
            d = df.copy()
        d.columns = [c.lower() for c in d.columns]
        d = d[["open", "high", "low", "close", "volume"]].dropna(subset=["open", "close"])
        if d.empty:
            continue
        if tz_naive and d.index.tz is not None:
            d.index = d.index.tz_convert("Asia/Kolkata").tz_localize(None)
        out[s] = d
    return out


def daily(symbols, period="2y", chunk=100) -> dict[str, pd.DataFrame]:
    out = {}
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        out |= _split(_download([yahoo(s) for s in part], period=period, interval="1d"), part)
    for s, d in out.items():
        d.index = d.index.normalize()
    return out


def intraday(symbols, interval="1m", period="5d") -> dict[str, pd.DataFrame]:
    return _split(_download([yahoo(s) for s in symbols], period=period, interval=interval), symbols)


def minute_grid(df1m: pd.DataFrame, day: pd.Timestamp) -> np.ndarray | None:
    """One day's 1-minute candles -> (375, 5) grid (09:15..15:29), forward-filled."""
    d = df1m[df1m.index.normalize() == pd.Timestamp(day).normalize()]
    if len(d) < 300:
        return None
    m = (d.index.hour - 9) * 60 + d.index.minute - 15
    d = d[(m >= 0) & (m < MINUTES)]
    m = (d.index.hour - 9) * 60 + d.index.minute - 15
    g = np.full((MINUTES, 5), np.nan, dtype=np.float32)
    g[m] = d[["open", "high", "low", "close", "volume"]].to_numpy(np.float32)
    first = np.argmax(~np.isnan(g[:, 3]))
    last = g[first, 0]
    for i in range(MINUTES):
        if np.isnan(g[i, 3]):
            g[i, :4] = last
            g[i, 4] = 0
        else:
            last = g[i, 3]
    return g
