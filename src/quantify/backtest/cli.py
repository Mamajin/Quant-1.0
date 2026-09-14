"""Backtest CLI: `uv run python -m quantify.backtest.cli run --symbol AAPL`."""
from __future__ import annotations

import argparse
import logging

from ..config import load_config
from ..storage.db import connect
from .runner import run_and_store, summarize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantify backtest CLI")
    parser.add_argument("action", choices=["run"])
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--strategy", default="sma_crossover")
    parser.add_argument("--fast", type=int, default=10)
    parser.add_argument("--slow", type=int, default=30)
    parser.add_argument("--period", default="2y", help="yfinance history period, e.g. 1y, 2y, 5y")
    parser.add_argument("--fees", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.001)
    parser.add_argument("--n-trials", type=int, default=1,
                         help="How many strategy variants you tried before this one (for the Deflated Sharpe Ratio)")
    parser.add_argument("--config", type=str, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    con = connect(config.storage)
    try:
        report = run_and_store(
            con, config, args.symbol.upper(), strategy=args.strategy, period=args.period,
            fees=args.fees, slippage=args.slippage, n_trials=args.n_trials,
            fast=args.fast, slow=args.slow,
        )
        print(summarize(report))
    finally:
        con.close()


if __name__ == "__main__":
    main()
