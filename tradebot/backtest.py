"""Daily-bar backtester with realistic Indian delivery costs.

Execution model (same as the live bot): signal computed at close of day t,
order filled at the OPEN of day t+1 with slippage + Zerodha charges, whole shares only.
Capital is split equally across symbols; each symbol is traded as its own sleeve.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .costs import CostModel

TRADING_DAYS = 252


@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    qty: int
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None
    pnl: float = 0.0  # net of all charges


@dataclass
class Result:
    equity: pd.Series
    trades: list[Trade] = field(default_factory=list)
    exposure: float = 0.0
    charges: float = 0.0


def run_symbol(df: pd.DataFrame, signal: pd.Series, capital: float, costs: CostModel, symbol="") -> Result:
    sig = signal.reindex(df.index).fillna(0).to_numpy()
    o, c = df.open.to_numpy(), df.close.to_numpy()
    cash, qty = capital, 0
    eq = np.empty(len(df))
    trades: list[Trade] = []
    open_trade: Trade | None = None
    total_charges, days_in = 0.0, 0
    buy_cost_basis = 0.0

    for i in range(len(df)):
        want = sig[i - 1] if i > 0 else 0  # yesterday's signal, filled at today's open
        if want == 1 and qty == 0:
            px = costs.fill_price("BUY", o[i])
            n = math.floor(cash / px)
            while n > 0 and n * px + costs.charges("BUY", n, px) > cash:
                n -= 1
            if n > 0:
                ch = costs.charges("BUY", n, px)
                cash -= n * px + ch
                total_charges += ch
                qty = n
                buy_cost_basis = n * px + ch
                open_trade = Trade(symbol, df.index[i], px, n)
        elif want == 0 and qty > 0:
            px = costs.fill_price("SELL", o[i])
            ch = costs.charges("SELL", qty, px)
            cash += qty * px - ch
            total_charges += ch
            open_trade.exit_date, open_trade.exit_price = df.index[i], px
            open_trade.pnl = qty * px - ch - buy_cost_basis
            trades.append(open_trade)
            open_trade, qty = None, 0
        if qty > 0:
            days_in += 1
        eq[i] = cash + qty * c[i]

    if open_trade is not None:  # mark open trade to last close for stats
        open_trade.pnl = qty * c[-1] - buy_cost_basis
        trades.append(open_trade)
    return Result(pd.Series(eq, index=df.index), trades, days_in / max(len(df), 1), total_charges)


def run_portfolio(data: dict[str, pd.DataFrame], strategy_fn, capital: float, costs: CostModel) -> Result:
    per = capital / len(data)
    parts = [run_symbol(df, strategy_fn(df), per, costs, sym) for sym, df in data.items()]
    eq = pd.concat([p.equity for p in parts], axis=1).ffill().bfill().sum(axis=1)
    return Result(
        eq,
        [t for p in parts for t in p.trades],
        float(np.mean([p.exposure for p in parts])),
        sum(p.charges for p in parts),
    )


def buy_and_hold(data, capital, costs):
    ones = lambda df: pd.Series(1.0, index=df.index)
    return run_portfolio(data, ones, capital, costs)


def metrics(eq: pd.Series, rf_annual: float = 0.065) -> dict:
    eq = eq.dropna()
    if len(eq) < 2 or eq.iloc[0] <= 0:
        return {}
    rets = eq.pct_change().dropna()
    years = len(eq) / TRADING_DAYS
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    ex = rets - rf_annual / TRADING_DAYS
    sharpe = ex.mean() / ex.std() * math.sqrt(TRADING_DAYS) if ex.std() > 0 else 0.0
    dd = eq / eq.cummax() - 1
    return {
        "total_return": eq.iloc[-1] / eq.iloc[0] - 1,
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": dd.min(),
        "volatility": rets.std() * math.sqrt(TRADING_DAYS),
    }


def summarize(name: str, res: Result, oos_start: pd.Timestamp | None, rf: float) -> dict:
    m = metrics(res.equity, rf)
    closed = [t for t in res.trades if t.exit_date is not None]
    wins = [t for t in closed if t.pnl > 0]
    row = {
        "strategy": name,
        "total_return": m.get("total_return"),
        "cagr": m.get("cagr"),
        "sharpe": m.get("sharpe"),
        "max_drawdown": m.get("max_drawdown"),
        "trades": len(closed),
        "win_rate": len(wins) / len(closed) if closed else np.nan,
        "exposure": res.exposure,
        "charges_rs": res.charges,
    }
    if oos_start is not None:
        oos = metrics(res.equity.loc[oos_start:], rf)
        row["oos_cagr"] = oos.get("cagr")
        row["oos_sharpe"] = oos.get("sharpe")
    return row
