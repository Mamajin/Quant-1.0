"""Ties provider -> engine -> validation -> storage together (manual FR-009)."""
from __future__ import annotations

import datetime as dt

from scipy.stats import kurtosis as sample_kurtosis
from scipy.stats import skew as sample_skew

from ..config import QuantifyConfig
from ..ingest.pipeline import get_provider
from ..storage import repo
from .engine import BacktestResult, backtest_sma_crossover
from .validation import deflated_sharpe_ratio

STRATEGIES = {"sma_crossover": backtest_sma_crossover}


def run_and_store(con, config: QuantifyConfig, symbol: str, strategy: str = "sma_crossover",
                   period: str = "2y", fees: float = 0.001, slippage: float = 0.001,
                   n_trials: int = 1, **strategy_kwargs) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy {strategy!r}; available: {list(STRATEGIES)}")

    provider = get_provider(config.provider.name)
    history = provider.fetch_history(symbol, period=period)
    prices = history["close"]

    result: BacktestResult = STRATEGIES[strategy](
        prices, fees=fees, slippage=slippage, risk_free_rate=config.greeks.risk_free_rate, **strategy_kwargs
    )
    stats = result.stats

    returns = result.strategy_returns[result.strategy_returns != 0]
    skew = float(sample_skew(returns)) if len(returns) > 2 else 0.0
    kurt = float(sample_kurtosis(returns, fisher=False)) if len(returns) > 2 else 3.0
    dsr = deflated_sharpe_ratio(stats["sharpe"], n_obs=len(prices), n_trials=n_trials, skew=skew, kurtosis=kurt)

    params = {"symbol": symbol, "period": period, "fees": fees, "slippage": slippage, **strategy_kwargs}
    run_id = repo.insert_backtest_run(
        con, strategy=strategy, params=params,
        start=prices.index[0].date(), end=prices.index[-1].date(), stats=stats,
    )

    return {"run_id": run_id, "symbol": symbol, "strategy": strategy, "params": params,
            "n_trials": n_trials, "stats": stats, "deflated_sharpe": dsr,
            "equity_curve": result.equity_curve, "trades": result.trades}


def summarize(report: dict) -> str:
    stats = report["stats"]
    dsr = report["deflated_sharpe"]
    lines = [
        f"{report['symbol']} / {report['strategy']} {report['params']}",
        f"  CAGR {stats['cagr']:.2%}  Sharpe {stats['sharpe']:.2f}  Sortino {stats['sortino']:.2f}  "
        f"Calmar {stats['calmar']:.2f}",
        f"  Max DD {stats['max_drawdown']:.2%}  Profit factor {stats['profit_factor']:.2f}  "
        f"Win rate {stats['win_rate']:.2%}  Trades {stats['n_trades']}",
        f"  Deflated Sharpe: SR0 (noise floor, {report['n_trials']} trials) = "
        f"{dsr['sr0_noise_floor']:.2f}, DSR = {dsr['dsr']:.2%}"
        + ("  [LIKELY OVERFIT]" if dsr["likely_overfit"] else ""),
    ]
    return "\n".join(lines)
