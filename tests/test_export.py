"""Export tests (manual FR-014: CSV/Parquet export of any table)."""
import io

import duckdb
import polars as pl
import pytest

from quantify.export import to_bytes, to_csv_bytes, to_parquet_bytes
from quantify.storage import repo
from quantify.storage.db import SCHEMA_DDL


@pytest.fixture()
def con():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_DDL)
    yield con
    con.close()


def test_to_csv_bytes_roundtrips():
    df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    csv_bytes = to_csv_bytes(df)
    back = pl.read_csv(io.BytesIO(csv_bytes))
    assert back.to_dicts() == df.to_dicts()


def test_to_parquet_bytes_roundtrips():
    df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    parquet_bytes = to_parquet_bytes(df)
    back = pl.read_parquet(io.BytesIO(parquet_bytes))
    assert back.to_dicts() == df.to_dicts()


def test_to_bytes_dispatches_by_format():
    df = pl.DataFrame({"a": [1]})
    assert to_bytes(df, "csv") == to_csv_bytes(df)
    assert to_bytes(df, "parquet") == to_parquet_bytes(df)


def test_to_bytes_rejects_unknown_format():
    df = pl.DataFrame({"a": [1]})
    with pytest.raises(ValueError):
        to_bytes(df, "xlsx")


def test_export_table_rejects_disallowed_table(con):
    with pytest.raises(ValueError):
        repo.export_table(con, "sqlite_master")  # not in the allowlist


def test_export_table_returns_data(con):
    repo.upsert_symbol(con, "AAPL", name="Apple Inc.")
    df = repo.export_table(con, "symbols")
    assert df.height == 1
    assert df["symbol"][0] == "AAPL"


def test_export_table_respects_limit(con):
    for s in ["AAPL", "MSFT", "TSLA"]:
        repo.upsert_symbol(con, s)
    df = repo.export_table(con, "symbols", limit=2)
    assert df.height == 2
