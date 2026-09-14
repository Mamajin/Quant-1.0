"""DuckDB connection + schema DDL (manual sec 2.12: 'Database schema (suggested)').

DuckDB is the local, zero-server, single-file store (sec 2.9). EOD chain
snapshots are additionally exported to partitioned Parquet under
storage.parquet_dir for archival/portability (sec 2.12 'Retention').
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from ..config import StorageConfig

SCHEMA_DDL = """
CREATE SEQUENCE IF NOT EXISTS seq_chain_snapshots START 1;
CREATE SEQUENCE IF NOT EXISTS seq_trades_flow START 1;
CREATE SEQUENCE IF NOT EXISTS seq_signals START 1;
CREATE SEQUENCE IF NOT EXISTS seq_alerts START 1;
CREATE SEQUENCE IF NOT EXISTS seq_backtest_runs START 1;
CREATE SEQUENCE IF NOT EXISTS seq_positions START 1;
CREATE SEQUENCE IF NOT EXISTS seq_journal START 1;

CREATE TABLE IF NOT EXISTS symbols (
    symbol VARCHAR PRIMARY KEY,
    name VARCHAR,
    type VARCHAR,        -- 'stock' | 'etf'
    sector VARCHAR,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS option_contracts (
    contract_id VARCHAR PRIMARY KEY,
    underlying VARCHAR REFERENCES symbols(symbol),
    expiry DATE,
    strike DOUBLE,
    "right" VARCHAR,      -- 'C' | 'P' (quoted: RIGHT is a reserved SQL keyword)
    multiplier INTEGER DEFAULT 100,
    style VARCHAR DEFAULT 'american'
);

-- Not in the manual's schema sketch verbatim, but "suggested" (sec 2.12) and
-- clearly needed: a time series of underlying spot prices, since GEX/max-pain
-- need "current spot" and it's identical for every contract of a symbol at a
-- given ts (no sense duplicating it onto every chain_snapshots row).
CREATE TABLE IF NOT EXISTS underlying_quotes (
    symbol VARCHAR REFERENCES symbols(symbol),
    ts TIMESTAMP,
    spot DOUBLE,
    PRIMARY KEY (symbol, ts)
);

CREATE TABLE IF NOT EXISTS chain_snapshots (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_chain_snapshots'),
    contract_id VARCHAR REFERENCES option_contracts(contract_id),
    ts TIMESTAMP,
    bid DOUBLE,
    ask DOUBLE,
    last DOUBLE,
    mid DOUBLE,
    volume BIGINT,
    open_interest BIGINT,
    iv DOUBLE,
    delta DOUBLE,
    gamma DOUBLE,
    theta DOUBLE,
    vega DOUBLE,
    rho DOUBLE
);

CREATE TABLE IF NOT EXISTS trades_flow (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_trades_flow'),
    contract_id VARCHAR REFERENCES option_contracts(contract_id),
    ts TIMESTAMP,
    price DOUBLE,
    size BIGINT,
    premium DOUBLE,
    exchange VARCHAR,
    aggressor VARCHAR,    -- 'B' | 'S' | '?'
    type VARCHAR,          -- 'sweep' | 'block' | 'split' | NULL
    is_unusual BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS signals (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_signals'),
    ts TIMESTAMP,
    symbol VARCHAR,
    rule_name VARCHAR,
    score DOUBLE,
    payload JSON
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_alerts'),
    signal_id BIGINT REFERENCES signals(id),
    channel VARCHAR,
    sent_ts TIMESTAMP,
    status VARCHAR
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_backtest_runs'),
    strategy VARCHAR,
    params JSON,
    start DATE,
    "end" DATE,
    sharpe DOUBLE,
    cagr DOUBLE,
    max_dd DOUBLE,
    profit_factor DOUBLE,
    created_ts TIMESTAMP
);

CREATE TABLE IF NOT EXISTS positions (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_positions'),
    symbol VARCHAR,
    contract_id VARCHAR,
    qty DOUBLE,
    entry_price DOUBLE,
    entry_ts TIMESTAMP,
    exit_price DOUBLE,
    exit_ts TIMESTAMP,
    pnl DOUBLE
);

CREATE TABLE IF NOT EXISTS journal (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_journal'),
    position_id BIGINT REFERENCES positions(id),
    reason_entry VARCHAR,
    reason_exit VARCHAR,
    tags VARCHAR,
    notes VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_chain_snapshots_contract_ts ON chain_snapshots(contract_id, ts);
CREATE INDEX IF NOT EXISTS idx_chain_snapshots_ts ON chain_snapshots(ts);
"""


def connect(storage: StorageConfig) -> duckdb.DuckDBPyConnection:
    db_path = storage.resolved_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    storage.resolved_parquet_dir().mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(SCHEMA_DDL)
    return con
