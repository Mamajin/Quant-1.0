"""Vectorized signal backtester (manual FR-009, sec 3.7 'Statistics & backtest
outputs'). See package docstring for why this isn't built on vectorbt.

Look-ahead-bias guard (manual sec 1.6: "using data you wouldn't have had in
real time ... Fatal and common"): entries/exits computed from bar t's close
are only acted on starting bar t+1 (`position.shift(1)`), never the same bar.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


@dataclass
class Trade:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_equity: float
    exit_equity: float

    @property
    def pnl(self) -> float:
        return self.exit_equity - self.entry_equity

    @property
    def return_pct(self) -> float:
        return self.exit_equity / self.entry_equity - 1.0


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    strategy_returns: pd.Series
    trades: list[Trade] = field(default_factory=list)
    initial_cash: float = 10_000.0
    risk_free_rate: float = 0.04

    @property
    def stats(self) -> dict:
        equity = self.equity_curve
        returns = self.strategy_returns
        n_days = len(equity)
        years = n_days / TRADING_DAYS_PER_YEAR if n_days > 0 else 0.0

        total_return = equity.iloc[-1] / self.initial_cash - 1.0 if n_days else 0.0
        cagr = (equity.iloc[-1] / self.initial_cash) ** (1 / years) - 1.0 if years > 0 and equity.iloc[-1] > 0 else 0.0

        annual_vol = returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
        annual_return = returns.mean() * TRADING_DAYS_PER_YEAR
        sharpe = (annual_return - self.risk_free_rate) / annual_vol if annual_vol > 0 else 0.0

        downside = returns[returns < 0]
        downside_vol = downside.std() * np.sqrt(TRADING_DAYS_PER_YEAR) if len(downside) else 0.0
        sortino = (annual_return - self.risk_free_rate) / downside_vol if downside_vol > 0 else 0.0

        running_max = equity.cummax()
        drawdown = equity / running_max - 1.0
        max_drawdown = float(drawdown.min()) if n_days else 0.0
        calmar = cagr / abs(max_drawdown) if max_drawdown != 0 else 0.0

        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
        win_rate = len(wins) / len(self.trades) if self.trades else 0.0
        avg_win = gross_profit / len(wins) if wins else 0.0
        avg_loss = gross_loss / len(losses) if losses else 0.0
        expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

        return {
            "total_return": total_return,
            "cagr": cagr,
            "volatility": float(annual_vol),
            "sharpe": float(sharpe),
            "sortino": float(sortino),
            "max_drawdown": max_drawdown,
            "calmar": calmar,
            "profit_factor": float(profit_factor),
            "win_rate": win_rate,
            "expectancy": expectancy,
            "n_trades": len(self.trades),
        }


def sma_crossover_signals(prices: pd.Series, fast: int = 10, slow: int = 30) -> tuple[pd.Series, pd.Series]:
    """Fast/slow moving-average crossover (manual Appendix E sample #5)."""
    fast_ma = prices.rolling(fast).mean()
    slow_ma = prices.rolling(slow).mean()
    above = fast_ma > slow_ma
    prev_above = above.shift(1, fill_value=False)
    entries = above & ~prev_above
    exits = ~above & prev_above
    return entries, exits


def _to_position(entries: pd.Series, exits: pd.Series) -> pd.Series:
    """Collapse entry/exit signals into a 0/1 long-only position, ignoring
    entries while already in a trade and exits while already flat."""
    position = np.zeros(len(entries), dtype=float)
    in_trade = False
    for i in range(len(entries)):
        if not in_trade and bool(entries.iloc[i]):
            in_trade = True
        elif in_trade and bool(exits.iloc[i]):
            in_trade = False
        position[i] = 1.0 if in_trade else 0.0
    return pd.Series(position, index=entries.index)


def run_backtest(prices: pd.Series, entries: pd.Series, exits: pd.Series,
                  fees: float = 0.001, slippage: float = 0.001,
                  initial_cash: float = 10_000.0, risk_free_rate: float = 0.04) -> BacktestResult:
    """Long-only, single-position vectorized backtest with fees + slippage
    (manual FR-009). `fees`/`slippage` are fractional costs applied on every
    entry and exit (e.g. 0.001 = 10 bps each way)."""
    prices = prices.dropna()
    entries, exits = entries.reindex(prices.index).fillna(False), exits.reindex(prices.index).fillna(False)

    raw_position = _to_position(entries, exits)
    position = raw_position.shift(1).fillna(0.0)  # act on yesterday's signal -- no look-ahead

    daily_returns = prices.pct_change().fillna(0.0)
    strategy_returns = position * daily_returns

    position_changes = position.diff().abs().fillna(position.abs())
    strategy_returns = strategy_returns - position_changes * (fees + slippage)

    equity_curve = initial_cash * (1.0 + strategy_returns).cumprod()

    trades = _extract_trades(position, equity_curve, initial_cash)

    return BacktestResult(
        equity_curve=equity_curve,
        strategy_returns=strategy_returns,
        trades=trades,
        initial_cash=initial_cash,
        risk_free_rate=risk_free_rate,
    )


def _extract_trades(position: pd.Series, equity_curve: pd.Series, initial_cash: float) -> list[Trade]:
    trades: list[Trade] = []
    in_trade = False
    entry_idx = None
    for i in range(len(position)):
        pos = position.iloc[i]
        if not in_trade and pos == 1.0:
            in_trade = True
            entry_idx = i
        elif in_trade and pos == 0.0:
            in_trade = False
            entry_equity = equity_curve.iloc[entry_idx - 1] if entry_idx > 0 else initial_cash
            exit_equity = equity_curve.iloc[i]
            trades.append(Trade(
                entry_date=position.index[entry_idx],
                exit_date=position.index[i],
                entry_equity=float(entry_equity),
                exit_equity=float(exit_equity),
            ))
    if in_trade and entry_idx is not None:
        entry_equity = equity_curve.iloc[entry_idx - 1] if entry_idx > 0 else initial_cash
        trades.append(Trade(
            entry_date=position.index[entry_idx],
            exit_date=position.index[-1],
            entry_equity=float(entry_equity),
            exit_equity=float(equity_curve.iloc[-1]),
        ))
    return trades


def backtest_sma_crossover(prices: pd.Series, fast: int = 10, slow: int = 30,
                            fees: float = 0.001, slippage: float = 0.001,
                            initial_cash: float = 10_000.0, risk_free_rate: float = 0.04) -> BacktestResult:
    entries, exits = sma_crossover_signals(prices, fast, slow)
    return run_backtest(prices, entries, exits, fees, slippage, initial_cash, risk_free_rate)
