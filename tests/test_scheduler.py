"""Scheduler tests (manual FR-001 market-hours gating, FR-004 EOD archive job)."""
import datetime as dt

import duckdb

from quantify.config import QuantifyConfig
from quantify.ingest.scheduler import EASTERN, build_scheduler, is_market_hours
from quantify.storage.db import SCHEMA_DDL


def eastern(y, m, d, h, mi):
    return dt.datetime(y, m, d, h, mi, tzinfo=EASTERN)


def test_is_market_hours_during_session():
    tuesday_open = eastern(2026, 1, 6, 10, 0)  # a Tuesday
    assert is_market_hours(tuesday_open) is True


def test_is_market_hours_before_open():
    assert is_market_hours(eastern(2026, 1, 6, 9, 0)) is False


def test_is_market_hours_after_close():
    assert is_market_hours(eastern(2026, 1, 6, 16, 30)) is False


def test_is_market_hours_weekend():
    saturday = eastern(2026, 1, 10, 10, 0)
    assert is_market_hours(saturday) is False


def test_is_market_hours_boundaries_are_inclusive():
    assert is_market_hours(eastern(2026, 1, 6, 9, 30)) is True
    assert is_market_hours(eastern(2026, 1, 6, 16, 0)) is True


def test_build_scheduler_registers_both_jobs():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_DDL)
    config = QuantifyConfig()
    scheduler = build_scheduler(config, con)
    jobs = scheduler.get_jobs()
    assert len(jobs) == 2

    triggers = {type(j.trigger).__name__ for j in jobs}
    assert "IntervalTrigger" in triggers
    assert "CronTrigger" in triggers
    con.close()


def test_build_scheduler_interval_matches_config_refresh_minutes():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_DDL)
    config = QuantifyConfig()
    config.schedule.refresh_minutes = 7
    scheduler = build_scheduler(config, con)
    interval_job = next(j for j in scheduler.get_jobs() if type(j.trigger).__name__ == "IntervalTrigger")
    assert interval_job.trigger.interval == dt.timedelta(minutes=7)
    con.close()
