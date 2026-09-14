"""Market-hours-aware scheduler (manual FR-001: 'fetch ... on a configurable
schedule (e.g., every 15 min during US market hours)').

`uv run python -m quantify.ingest.scheduler` runs continuously; Ctrl+C to stop.
"""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from ..alerts.dispatch import check_and_alert
from ..config import load_config
from ..storage import repo
from ..storage.db import connect
from .pipeline import run_ingestion

logger = logging.getLogger(__name__)
EASTERN = ZoneInfo("America/New_York")


def is_market_hours(now: dt.datetime | None = None) -> bool:
    now = (now or dt.datetime.now(EASTERN)).astimezone(EASTERN)
    if now.weekday() >= 5:  # Sat/Sun
        return False
    open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= now <= close_t


def build_scheduler(config, con) -> BlockingScheduler:
    """Build (but don't start) the scheduler with both jobs registered --
    split out from run_scheduler so job wiring/triggers are unit-testable
    without blocking on scheduler.start()."""

    def job() -> None:
        if config.schedule.market_hours_only and not is_market_hours():
            logger.info("Outside market hours, skipping ingestion")
            return
        results = run_ingestion(con, config)
        logger.info("Ingestion complete: %s", results)

        if config.alerts.enabled:
            for symbol in results:
                dispatched = check_and_alert(con, config, symbol)
                if dispatched:
                    logger.info("Alerts for %s: %s", symbol, dispatched)

    def archive_job() -> None:
        """FR-004: append today's chain snapshots to a partitioned Parquet
        file. Runs daily after market close (16:30 ET) regardless of
        market_hours_only, since it archives what already happened today."""
        today = dt.datetime.now(EASTERN).date()
        try:
            path = repo.export_daily_parquet(con, config.storage, today)
            logger.info("Archived %s snapshots to %s", today, path)
        except Exception as exc:  # noqa: BLE001 - archiving must never crash the scheduler
            logger.warning("EOD archiving failed for %s: %s", today, exc)

    scheduler = BlockingScheduler()
    scheduler.add_job(job, "interval", minutes=config.schedule.refresh_minutes, next_run_time=dt.datetime.now())
    scheduler.add_job(archive_job, CronTrigger(hour=16, minute=30, day_of_week="mon-fri", timezone=EASTERN))
    return scheduler


def run_scheduler(config_path: str | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config(config_path)
    con = connect(config.storage)
    scheduler = build_scheduler(config, con)
    logger.info("Starting scheduler: every %s min, market_hours_only=%s; EOD archive daily at 16:30 ET",
                config.schedule.refresh_minutes, config.schedule.market_hours_only)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        con.close()


if __name__ == "__main__":
    run_scheduler()
