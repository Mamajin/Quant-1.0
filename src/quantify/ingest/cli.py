"""One-shot ingestion entrypoint: `uv run python -m quantify.ingest.cli run --once`
(manual FR-001, and a manual-trigger complement to the APScheduler job)."""
from __future__ import annotations

import argparse
import logging

from ..alerts.dispatch import check_and_alert
from ..config import load_config
from ..storage.db import connect
from .pipeline import run_ingestion

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantify ingestion CLI")
    parser.add_argument("action", choices=["run"], help="Action to perform")
    parser.add_argument("--once", action="store_true", help="Run a single ingestion pass and exit")
    parser.add_argument("--symbols", type=str, default=None,
                         help="Comma-separated symbols; defaults to config watchlist")
    parser.add_argument("--config", type=str, default=None, help="Path to config.toml")
    parser.add_argument("--alert", action="store_true",
                         help="Also run the unusual-activity alert check after ingesting (FR-008)")
    args = parser.parse_args()

    config = load_config(args.config)
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    con = connect(config.storage)
    try:
        results = run_ingestion(con, config, symbols)
        for symbol, rows in results.items():
            print(f"{symbol}: {rows} snapshot rows ingested")
            if args.alert:
                dispatched = check_and_alert(con, config, symbol)
                for d in dispatched:
                    print(f"  alert -> {d['channel']}: {'OK' if d['ok'] else 'FAILED'}: {d['message']}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
