"""Sector flow heatmap tests (manual sec 2.4, FR-012)."""
import datetime as dt

import duckdb
import polars as pl
import pytest

from quantify.scanner.heatmap import sector_flow, sector_summary
from quantify.storage import repo
from quantify.storage.db import SCHEMA_DDL


@pytest.fixture()
def con():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_DDL)
    yield con
    con.close()


def seed_symbol_with_chain(con, symbol, sector, call_volume, put_volume, mid=1.0):
    repo.upsert_symbol(con, symbol)
    if sector:
        repo.update_symbol_sector(con, symbol, sector)
    expiry = dt.date.today() + dt.timedelta(days=30)
    call_id = repo.make_contract_id(symbol, expiry, "C", 100.0)
    put_id = repo.make_contract_id(symbol, expiry, "P", 100.0)
    repo.upsert_contracts(con, [
        {"contract_id": call_id, "underlying": symbol, "expiry": expiry, "strike": 100.0, "right": "C"},
        {"contract_id": put_id, "underlying": symbol, "expiry": expiry, "strike": 100.0, "right": "P"},
    ])
    snap = pl.DataFrame([
        {"contract_id": call_id, "ts": dt.datetime.now(), "bid": mid, "ask": mid, "last": mid, "mid": mid,
         "volume": call_volume, "open_interest": 10, "iv": 0.3, "delta": 0.4, "gamma": 0.02,
         "theta": -0.01, "vega": 0.1, "rho": 0.01},
        {"contract_id": put_id, "ts": dt.datetime.now(), "bid": mid, "ask": mid, "last": mid, "mid": mid,
         "volume": put_volume, "open_interest": 10, "iv": 0.3, "delta": -0.4, "gamma": 0.02,
         "theta": -0.01, "vega": 0.1, "rho": 0.01},
    ])
    repo.insert_chain_snapshots(con, snap)


def test_sector_flow_includes_symbol_with_no_data_as_unknown(con):
    flow = sector_flow(con, ["NODATA"])
    assert flow.height == 1
    row = flow.to_dicts()[0]
    assert row["sector"] == "Unknown"
    assert row["net_premium"] is None


def test_sector_flow_computes_net_premium_and_pc_ratio(con):
    seed_symbol_with_chain(con, "AAPL", "Technology", call_volume=100, put_volume=50, mid=2.0)
    flow = sector_flow(con, ["AAPL"])
    row = flow.to_dicts()[0]
    assert row["sector"] == "Technology"
    # net premium = call premium - put premium = 2*100*100 - 2*50*100 = 10000
    assert row["net_premium"] == pytest.approx(10_000.0)
    assert row["put_call_ratio"] == pytest.approx(0.5)


def test_sector_summary_aggregates_by_sector():
    flow_df = pl.DataFrame({
        "symbol": ["A", "B", "C"],
        "sector": ["Tech", "Tech", "Energy"],
        "net_premium": [1000.0, 2000.0, -500.0],
        "put_call_ratio": [0.5, 0.6, 1.5],
    })
    summary = sector_summary(flow_df)
    by_sector = {row["sector"]: row for row in summary.to_dicts()}
    assert by_sector["Tech"]["total_net_premium"] == pytest.approx(3000.0)
    assert by_sector["Tech"]["n_symbols"] == 2
    assert by_sector["Energy"]["total_net_premium"] == pytest.approx(-500.0)


def test_sector_summary_excludes_symbols_with_no_data():
    flow_df = pl.DataFrame({
        "symbol": ["A", "B"],
        "sector": ["Tech", "Unknown"],
        "net_premium": [1000.0, None],
        "put_call_ratio": [0.5, None],
    }, schema_overrides={"net_premium": pl.Float64, "put_call_ratio": pl.Float64})
    summary = sector_summary(flow_df)
    assert summary.height == 1
    assert summary["sector"][0] == "Tech"


def test_sector_summary_empty_input():
    flow_df = pl.DataFrame(schema={
        "symbol": pl.Utf8, "sector": pl.Utf8, "net_premium": pl.Float64, "put_call_ratio": pl.Float64,
    })
    summary = sector_summary(flow_df)
    assert summary.is_empty()


def test_sector_summary_sorted_descending_by_net_premium():
    flow_df = pl.DataFrame({
        "symbol": ["A", "B"],
        "sector": ["Low", "High"],
        "net_premium": [100.0, 5000.0],
        "put_call_ratio": [1.0, 1.0],
    })
    summary = sector_summary(flow_df)
    assert summary["sector"].to_list() == ["High", "Low"]
