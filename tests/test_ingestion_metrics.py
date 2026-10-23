"""Ingestion-run tracking and metrics tests (manual sec 4.6: 'a simple local
metrics page (rows ingested, last run, error counts)')."""
import datetime as dt

import duckdb
import pandas as pd
import polars as pl
import pytest

from quantify.config import QuantifyConfig
from quantify.ingest.pipeline import run_ingestion
from quantify.storage import repo
from quantify.storage.db import SCHEMA_DDL

RAW_CHAIN_SCHEMA = {
    "underlying": pl.Utf8, "expiry": pl.Date, "strike": pl.Float64, "right": pl.Utf8,
    "bid": pl.Float64, "ask": pl.Float64, "last": pl.Float64, "volume": pl.Int64, "open_interest": pl.Int64,
}


class FakeProvider:
    name = "fake"

    def __init__(self, spot: float = 100.0, chain: pl.DataFrame | None = None, fail_symbols: set[str] | None = None):
        self._spot = spot
        self._chain = chain if chain is not None else pl.DataFrame(schema=RAW_CHAIN_SCHEMA)
        self._fail_symbols = fail_symbols or set()

    def fetch_spot(self, symbol: str) -> float:
        if symbol in self._fail_symbols:
            raise RuntimeError(f"provider down for {symbol}")
        return self._spot

    def fetch_chain(self, symbol: str, max_expiries: int = 6) -> pl.DataFrame:
        return self._chain

    def fetch_sector(self, symbol: str) -> str | None:
        return None

    def fetch_corporate_actions(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["date", "action_type", "value"])


@pytest.fixture()
def con():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_DDL)
    yield con
    con.close()


def test_insert_and_summarize_ingestion_runs(con):
    now = dt.datetime.now()
    repo.insert_ingestion_run(con, now, "AAPL", 100, success=True)
    repo.insert_ingestion_run(con, now, "MSFT", 0, success=False, error_message="boom")

    metrics = repo.ingestion_metrics(con)
    assert metrics["total_rows"] == 100
    assert metrics["error_count"] == 1
    assert metrics["symbols_touched"] == 2
    assert metrics["last_run"] is not None


def test_ingestion_metrics_respects_since_hours_window(con):
    old = dt.datetime.now() - dt.timedelta(hours=48)
    repo.insert_ingestion_run(con, old, "AAPL", 500, success=True)
    metrics = repo.ingestion_metrics(con, since_hours=24.0)
    assert metrics["total_rows"] == 0
    assert metrics["symbols_touched"] == 0


def test_ingestion_metrics_per_symbol_breakdown(con):
    now = dt.datetime.now()
    repo.insert_ingestion_run(con, now, "AAPL", 100, success=True)
    repo.insert_ingestion_run(con, now, "AAPL", 50, success=False, error_message="rate limited")
    metrics = repo.ingestion_metrics(con)
    aapl = next(row for row in metrics["per_symbol"] if row["symbol"] == "AAPL")
    assert aapl["rows_ingested"] == 150
    assert aapl["error_count"] == 1


def test_ingestion_metrics_empty(con):
    metrics = repo.ingestion_metrics(con)
    assert metrics["total_rows"] == 0
    assert metrics["error_count"] == 0
    assert metrics["last_run"] is None
    assert metrics["per_symbol"] == []


def test_run_ingestion_records_success_and_failure(con, monkeypatch):
    # Bypass the real retry delay (already covered by tests/test_retry.py) --
    # we're testing run_ingestion's bookkeeping here, not retry timing.
    monkeypatch.setattr("quantify.ingest.pipeline.retry_with_backoff", lambda fn, **kwargs: fn())

    expiry = dt.date.today() + dt.timedelta(days=30)
    chain_df = pl.DataFrame([{
        "underlying": "AAPL", "expiry": expiry, "strike": 150.0, "right": "C",
        "bid": 1.0, "ask": 1.1, "last": 1.05, "volume": 10, "open_interest": 5,
    }])
    provider = FakeProvider(spot=150.0, chain=chain_df, fail_symbols={"BADSYM"})
    monkeypatch.setattr("quantify.ingest.pipeline.get_provider", lambda name: provider)

    config = QuantifyConfig()
    results = run_ingestion(con, config, symbols=["AAPL", "BADSYM"])

    assert results["AAPL"] == 1
    assert results["BADSYM"] == 0

    metrics = repo.ingestion_metrics(con)
    assert metrics["error_count"] == 1
    assert metrics["total_rows"] == 1

    by_symbol = {r["symbol"]: r for r in metrics["per_symbol"]}
    assert by_symbol["AAPL"]["error_count"] == 0
    assert by_symbol["BADSYM"]["error_count"] == 1
    assert by_symbol["BADSYM"]["rows_ingested"] == 0
