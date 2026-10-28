"""Daily OHLCV data loaders.

- yfinance (default, free): NSE symbols get a ".NS" suffix, e.g. RELIANCE -> RELIANCE.NS
- kite: Zerodha historical API (needs the paid Kite Connect plan; the free Personal API has no data)
- csv: a folder of <SYMBOL>.csv files with date,open,high,low,close,volume columns
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

COLS = ["open", "high", "low", "close", "volume"]


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)[COLS].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df[~df.index.duplicated(keep="last")].sort_index()


def load_yfinance(symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
    import yfinance as yf

    t = symbol if "." in symbol or symbol.startswith("^") else f"{symbol}.NS"
    df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        raise RuntimeError(f"No data from Yahoo for {t}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return _clean(df)


def load_csv(symbol: str, folder: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(Path(folder) / f"{symbol}.csv", parse_dates=[0], index_col=0)
    df = _clean(df)
    return df.loc[start:end]


def load_kite(kite, symbol: str, start: str, end: str | None = None, exchange: str = "NSE") -> pd.DataFrame:
    token = _instrument_token(kite, symbol, exchange)
    start_d = pd.Timestamp(start).date()
    end_d = pd.Timestamp(end).date() if end else dt.date.today()
    frames, cur = [], start_d
    while cur <= end_d:  # Kite allows ~2000 days of daily candles per request
        stop = min(cur + dt.timedelta(days=1900), end_d)
        rows = kite.historical_data(token, cur, stop, "day")
        if rows:
            frames.append(pd.DataFrame(rows).set_index("date"))
        cur = stop + dt.timedelta(days=1)
    if not frames:
        raise RuntimeError(f"No Kite data for {symbol}")
    return _clean(pd.concat(frames))


_TOKENS: dict = {}


def _instrument_token(kite, symbol, exchange):
    if exchange not in _TOKENS:
        _TOKENS[exchange] = {i["tradingsymbol"]: i["instrument_token"] for i in kite.instruments(exchange)}
    return _TOKENS[exchange][symbol]


def load(symbol: str, cfg: dict, start: str, end: str | None = None, kite=None) -> pd.DataFrame:
    src = cfg.get("source", "yfinance")
    if src == "yfinance":
        return load_yfinance(symbol, start, end)
    if src == "csv":
        return load_csv(symbol, cfg["csv_folder"], start, end)
    if src == "kite":
        if kite is None:
            raise RuntimeError("data.source=kite needs a logged-in Kite session")
        return load_kite(kite, symbol, start, end)
    raise ValueError(f"Unknown data source {src}")
