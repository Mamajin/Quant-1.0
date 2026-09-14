"""Regression tests for export_daily_parquet (manual sec 2.12 Retention,
FR-004): DuckDB's COPY ... TO <target> does not accept a bound (?)
parameter for the target filename -- caught only by actually running this
function, not by any earlier unit test."""
import datetime as dt

import duckdb
import polars as pl
import pytest

from quantify.config import StorageConfig
from quantify.storage import repo
from quantify.storage.db import SCHEMA_DDL


@pytest.fixture()
def con():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_DDL)
    yield con
    con.close()


@pytest.fixture()
def storage(tmp_path):
    return StorageConfig(db_path=str(tmp_path / "t.duckdb"), parquet_dir=str(tmp_path / "parquet"))


def test_export_daily_parquet_zero_rows(con, storage):
    path = repo.export_daily_parquet(con, storage, dt.date.today())
    df = pl.read_parquet(path)
    assert df.height == 0


def test_export_daily_parquet_with_data(con, storage):
    symbol, today = "AAPL", dt.date.today()
    repo.upsert_symbol(con, symbol)
    expiry = today + dt.timedelta(days=30)
    contract_id = repo.make_contract_id(symbol, expiry, "C", 150.0)
    repo.upsert_contracts(con, [{
        "contract_id": contract_id, "underlying": symbol, "expiry": expiry, "strike": 150.0, "right": "C",
    }])
    snap = pl.DataFrame([{
        "contract_id": contract_id, "ts": dt.datetime.combine(today, dt.time(15, 30)), "bid": 1.0, "ask": 1.1,
        "last": 1.05, "mid": 1.05, "volume": 100, "open_interest": 50, "iv": 0.3, "delta": 0.4,
        "gamma": 0.02, "theta": -0.01, "vega": 0.1, "rho": 0.01,
    }])
    repo.insert_chain_snapshots(con, snap)

    path = repo.export_daily_parquet(con, storage, today)
    df = pl.read_parquet(path)
    assert df.height == 1
    assert df["underlying"][0] == symbol


def test_export_daily_parquet_only_includes_matching_date(con, storage):
    symbol = "AAPL"
    repo.upsert_symbol(con, symbol)
    expiry = dt.date.today() + dt.timedelta(days=30)
    contract_id = repo.make_contract_id(symbol, expiry, "C", 150.0)
    repo.upsert_contracts(con, [{
        "contract_id": contract_id, "underlying": symbol, "expiry": expiry, "strike": 150.0, "right": "C",
    }])
    yesterday = dt.datetime.now() - dt.timedelta(days=1)
    snap = pl.DataFrame([{
        "contract_id": contract_id, "ts": yesterday, "bid": 1.0, "ask": 1.1, "last": 1.05, "mid": 1.05,
        "volume": 100, "open_interest": 50, "iv": 0.3, "delta": 0.4, "gamma": 0.02, "theta": -0.01,
        "vega": 0.1, "rho": 0.01,
    }])
    repo.insert_chain_snapshots(con, snap)

    path = repo.export_daily_parquet(con, storage, dt.date.today())
    df = pl.read_parquet(path)
    assert df.height == 0  # yesterday's row shouldn't show up in today's export
