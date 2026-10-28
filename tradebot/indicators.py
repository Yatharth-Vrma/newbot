"""Technical indicators. All take pandas Series/DataFrames of daily OHLCV and use only past data."""
import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(dn != 0, 100.0).where(up.notna())


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    return pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, sig


def bollinger(close: pd.Series, n=20, k=2.0):
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std()
    return mid - k * sd, mid, mid + k * sd


def supertrend(df: pd.DataFrame, n=10, mult=3.0) -> pd.Series:
    """Returns +1 (uptrend) / -1 (downtrend), NaN during warm-up."""
    a = atr(df, n).to_numpy()
    hl2 = ((df["high"] + df["low"]) / 2).to_numpy()
    c = df["close"].to_numpy()
    upper, lower = hl2 + mult * a, hl2 - mult * a
    fu, fl = upper.copy(), lower.copy()
    trend = np.full(len(c), np.nan)
    for i in range(len(c)):
        if np.isnan(a[i]):
            continue
        if i == 0 or np.isnan(trend[i - 1]):
            trend[i] = 1.0
            continue
        fu[i] = upper[i] if (upper[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lower[i] if (lower[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        if trend[i - 1] == 1 and c[i] < fl[i]:
            trend[i] = -1.0
        elif trend[i - 1] == -1 and c[i] > fu[i]:
            trend[i] = 1.0
        else:
            trend[i] = trend[i - 1]
    return pd.Series(trend, index=df.index)


def adx_dmi(df: pd.DataFrame, n=14):
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / tr
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return adx, pdi, mdi


def ichimoku(df: pd.DataFrame, t=9, k=26, s=52):
    h, l = df["high"], df["low"]
    tenkan = (h.rolling(t).max() + l.rolling(t).min()) / 2
    kijun = (h.rolling(k).max() + l.rolling(k).min()) / 2
    # Senkou spans are plotted k bars ahead -> the cloud "today" was computed k bars ago (no look-ahead).
    span_a = ((tenkan + kijun) / 2).shift(k)
    span_b = ((h.rolling(s).max() + l.rolling(s).min()) / 2).shift(k)
    return tenkan, kijun, span_a, span_b
