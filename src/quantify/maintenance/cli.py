"""Maintenance CLI: `uv run python -m quantify.maintenance.cli vacuum|audit`
(manual sec 4.3, sec 4.10)."""
from __future__ import annotations

import argparse
import logging
import sys

from ..config import load_config
from ..logging_config import configure_logging
from ..storage.db import connect
from .tasks import database_size_bytes, run_pip_audit, vacuum_database

configure_logging()
logger = logging.getLogger(__name__)


def _cmd_vacuum(config_path: str | None) -> None:
    config = load_config(config_path)
    before = database_size_bytes(config.storage)
    con = connect(config.storage)
    try:
        vacuum_database(con)
    finally:
        con.close()
    after = database_size_bytes(config.storage)
    logger.info("Vacuumed %s: %.1f MB -> %.1f MB", config.storage.resolved_db_path(),
                before / 1_000_000, after / 1_000_000)


def _cmd_audit() -> int:
    logger.info("Running pip-audit against the current environment...")
    result = run_pip_audit()
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        logger.warning("pip-audit found issues (exit code %d)", result.returncode)
    else:
        logger.info("pip-audit: no known vulnerabilities found")
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantify maintenance CLI")
    parser.add_argument("action", choices=["vacuum", "audit"])
    parser.add_argument("--config", type=str, default=None)
    args = parser.parse_args()

    if args.action == "vacuum":
        _cmd_vacuum(args.config)
    elif args.action == "audit":
        sys.exit(_cmd_audit())


if __name__ == "__main__":
    main()
