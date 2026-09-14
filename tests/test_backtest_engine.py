"""Backtest engine tests: no-lookahead guard, fees/slippage, trade extraction,
stats (manual FR-009, sec 1.6 look-ahead bias, sec 3.7 stats)."""
import numpy as np
import pandas as pd
import pytest

from quantify.backtest.engine import _to_position, run_backtest, sma_crossover_signals


def make_series(values):
    dates = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=dates, dtype=float)


def test_to_position_ignores_repeat_entries_and_exits_while_in_state():
    entries = pd.Series([True, True, False, False, False])
    exits = pd.Series([False, False, False, True, True])
    position = _to_position(entries, exits)
    assert list(position) == [1, 1, 1, 0, 0]


def test_signal_only_on_last_bar_never_executes_no_lookahead():
    """A signal on the final bar has no 'next bar' to execute on -- the
    strategy must never react to it within the observed window (manual sec
    1.6: no trading on same-bar information)."""
    prices = make_series([100, 101, 102, 103, 104])
    entries = pd.Series([False, False, False, False, True], index=prices.index)
    exits = pd.Series([False] * 5, index=prices.index)
    result = run_backtest(prices, entries, exits, fees=0.0, slippage=0.0)
    assert (result.strategy_returns == 0).all()
    assert result.trades == []


def test_one_trade_exits_before_a_later_crash():
    prices = make_series([100, 105, 110, 115, 90, 90])
    entries = pd.Series([False, True, False, False, False, False], index=prices.index)
    exits = pd.Series([False, False, False, True, False, False], index=prices.index)
    result = run_backtest(prices, entries, exits, fees=0.0005, slippage=0.0005, initial_cash=10_000.0)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_date == prices.index[2]
    assert trade.exit_date == prices.index[4]
    assert trade.pnl > 0  # captured the 100->115 run, exited before the 115->90 crash


def test_fees_reduce_final_equity():
    prices = make_series([100, 105, 110, 115, 120, 118])
    entries = pd.Series([False, True, False, False, False, False], index=prices.index)
    exits = pd.Series([False, False, False, False, False, True], index=prices.index)

    no_fees = run_backtest(prices, entries, exits, fees=0.0, slippage=0.0)
    with_fees = run_backtest(prices, entries, exits, fees=0.01, slippage=0.01)
    assert with_fees.equity_curve.iloc[-1] < no_fees.equity_curve.iloc[-1]


def test_flat_series_has_no_trades_and_zero_return():
    prices = make_series([100.0] * 20)
    entries, exits = sma_crossover_signals(prices, fast=3, slow=7)
    result = run_backtest(prices, entries, exits)
    assert result.trades == []
    assert result.stats["total_return"] == pytest.approx(0.0)


def test_sma_crossover_catches_an_uptrend():
    up = np.linspace(100, 150, 30)
    down = np.linspace(150, 100, 30)
    prices = make_series(np.concatenate([up, down]))
    entries, exits = sma_crossover_signals(prices, fast=3, slow=10)
    assert entries.sum() >= 1
    assert exits.sum() >= 1
    first_entry_idx = entries.to_numpy().nonzero()[0][0]
    first_exit_idx = exits.to_numpy().nonzero()[0][0]
    assert first_entry_idx < first_exit_idx


def test_stats_dict_has_expected_keys_and_matches_trade_count():
    up = np.linspace(100, 150, 30)
    down = np.linspace(150, 80, 30)
    up2 = np.linspace(80, 130, 30)
    prices = make_series(np.concatenate([up, down, up2]))
    entries, exits = sma_crossover_signals(prices, fast=3, slow=10)
    result = run_backtest(prices, entries, exits, fees=0.001, slippage=0.001)
    stats = result.stats
    for key in ["total_return", "cagr", "volatility", "sharpe", "sortino",
                "max_drawdown", "calmar", "profit_factor", "win_rate", "expectancy", "n_trades"]:
        assert key in stats
    assert stats["n_trades"] == len(result.trades)
