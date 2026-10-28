"""The 10 classic, widely used systematic strategies (long-only, daily bars).

Each strategy takes a daily OHLCV DataFrame (columns: open, high, low, close, volume)
and returns a Series of target positions: 1 = hold the stock, 0 = stay in cash.
The signal on bar t uses only data up to the close of bar t; it is executed at the
open of bar t+1 (in the backtest and in the live bot, which places AMO orders after close).

Long-only because Indian cash-equity delivery (CNC) can't be held short overnight.
There is no official "top 10 in the world" list; these are the most widely taught and
traded rule-based systems across trend-following, momentum and mean-reversion.
"""
import numpy as np
import pandas as pd

from . import indicators as ind


def _stateful(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    """Go long on entry, go flat on exit, otherwise keep the previous state."""
    e, x = entry.fillna(False).to_numpy(), exit_.fillna(False).to_numpy()
    pos = np.zeros(len(e))
    state = 0.0
    for i in range(len(e)):
        if state == 0 and e[i]:
            state = 1.0
        elif state == 1 and x[i]:
            state = 0.0
        pos[i] = state
    return pd.Series(pos, index=entry.index)


def _bool(s: pd.Series) -> pd.Series:
    return s.fillna(False).astype(float)


# 1. Golden cross (trend following) ------------------------------------------
def sma_cross(df, fast=50, slow=200):
    return _bool(ind.sma(df.close, fast) > ind.sma(df.close, slow))


# 2. EMA crossover (faster trend following) ---------------------------------
def ema_cross(df, fast=9, slow=21):
    return _bool(ind.ema(df.close, fast) > ind.ema(df.close, slow))


# 3. MACD signal-line crossover (Gerald Appel) ------------------------------
def macd(df, fast=12, slow=26, signal=9):
    line, sig = ind.macd(df.close, fast, slow, signal)
    return _bool(line > sig)


# 4. RSI(2) mean reversion (Larry Connors) ----------------------------------
def rsi2(df, n=2, entry_level=10, trend=200, exit_ma=5):
    r = ind.rsi(df.close, n)
    entry = (r < entry_level) & (df.close > ind.sma(df.close, trend))
    exit_ = df.close > ind.sma(df.close, exit_ma)
    return _stateful(entry, exit_)


# 5. Bollinger Band mean reversion ------------------------------------------
def bollinger(df, n=20, k=2.0):
    lower, mid, _ = ind.bollinger(df.close, n, k)
    return _stateful(df.close < lower, df.close > mid)


# 6. Donchian channel breakout (Turtle Traders, System 2) -------------------
def donchian(df, entry_n=55, exit_n=20):
    hi = df.high.rolling(entry_n).max().shift(1)
    lo = df.low.rolling(exit_n).min().shift(1)
    return _stateful(df.close > hi, df.close < lo)


# 7. Supertrend (very popular on NSE) ---------------------------------------
def supertrend(df, n=10, mult=3.0):
    return _bool(ind.supertrend(df, n, mult) == 1)


# 8. Time-series momentum, 12-1 month (Moskowitz/Ooi/Pedersen, AQR) --------
def momentum(df, lookback=252, skip=21):
    past = df.close.shift(skip)
    ret = past / past.shift(lookback - skip) - 1
    return _bool(ret > 0)


# 9. ADX + DMI trend strength (Welles Wilder) -------------------------------
def adx_dmi(df, n=14, threshold=25):
    adx, pdi, mdi = ind.adx_dmi(df, n)
    return _stateful((adx > threshold) & (pdi > mdi), pdi < mdi)


# 10. Ichimoku cloud (Goichi Hosoda) ----------------------------------------
def ichimoku(df):
    tenkan, kijun, a, b = ind.ichimoku(df)
    top = pd.concat([a, b], axis=1).max(axis=1)
    bottom = pd.concat([a, b], axis=1).min(axis=1)
    entry = (df.close > top) & (tenkan > kijun)
    exit_ = (df.close < bottom) | (tenkan < kijun)
    return _stateful(entry, exit_)


STRATEGIES = {
    "sma_cross": sma_cross,
    "ema_cross": ema_cross,
    "macd": macd,
    "rsi2": rsi2,
    "bollinger": bollinger,
    "donchian": donchian,
    "supertrend": supertrend,
    "momentum": momentum,
    "adx_dmi": adx_dmi,
    "ichimoku": ichimoku,
}


# Ensemble: hold when at least `min_votes` of the chosen strategies say hold.
def ensemble(df, members=None, min_votes=6):
    members = members or list(STRATEGIES)
    votes = sum(STRATEGIES[m](df) for m in members)
    return _bool(votes >= min_votes)


ALL = {**STRATEGIES, "ensemble": ensemble}


def get(name: str, params: dict | None = None):
    if name not in ALL:
        raise ValueError(f"Unknown strategy '{name}'. Choose from: {', '.join(ALL)}")
    fn = ALL[name]
    params = params or {}
    return lambda df: fn(df, **params)
