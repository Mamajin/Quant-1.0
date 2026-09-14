"""Typed read/write helpers over the DuckDB schema (manual sec 2.12)."""
from __future__ import annotations

import datetime as dt
import json

import duckdb
import polars as pl

from ..config import StorageConfig


def make_contract_id(underlying: str, expiry: dt.date, right: str, strike: float) -> str:
    return f"{underlying}_{expiry:%Y%m%d}_{right}_{strike:g}"


def upsert_symbol(con: duckdb.DuckDBPyConnection, symbol: str, name: str | None = None,
                   type_: str = "stock", sector: str | None = None) -> None:
    con.execute(
        """
        INSERT INTO symbols (symbol, name, type, sector, active)
        VALUES (?, ?, ?, ?, TRUE)
        ON CONFLICT (symbol) DO UPDATE SET name = excluded.name, type = excluded.type,
            sector = excluded.sector, active = TRUE
        """,
        [symbol, name, type_, sector],
    )


def upsert_contracts(con: duckdb.DuckDBPyConnection, contracts: list[dict]) -> None:
    if not contracts:
        return
    rows = [
        (c["contract_id"], c["underlying"], c["expiry"], c["strike"], c["right"],
         c.get("multiplier", 100), c.get("style", "american"))
        for c in contracts
    ]
    con.executemany(
        """
        INSERT INTO option_contracts (contract_id, underlying, expiry, strike, "right", multiplier, style)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (contract_id) DO NOTHING
        """,
        rows,
    )


def insert_chain_snapshots(con: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    """df columns: contract_id, ts, bid, ask, last, mid, volume, open_interest,
    iv, delta, gamma, theta, vega, rho."""
    if df.is_empty():
        return 0
    cols = ["contract_id", "ts", "bid", "ask", "last", "mid", "volume",
            "open_interest", "iv", "delta", "gamma", "theta", "vega", "rho"]
    arrow_tbl = df.select(cols).to_arrow()
    con.register("_snap_df", arrow_tbl)
    con.execute(f"INSERT INTO chain_snapshots ({', '.join(cols)}) SELECT {', '.join(cols)} FROM _snap_df")
    con.unregister("_snap_df")
    return df.height


def latest_chain(con: duckdb.DuckDBPyConnection, symbol: str) -> pl.DataFrame:
    """Most recent snapshot per contract for a symbol, joined with contract metadata."""
    result = con.execute(
        """
        WITH latest AS (
            SELECT cs.*, ROW_NUMBER() OVER (PARTITION BY contract_id ORDER BY ts DESC) AS rn
            FROM chain_snapshots cs
            JOIN option_contracts oc USING (contract_id)
            WHERE oc.underlying = ?
        )
        SELECT oc.underlying, oc.expiry, oc.strike, oc."right", l.*
        FROM latest l
        JOIN option_contracts oc USING (contract_id)
        WHERE l.rn = 1
        ORDER BY oc.expiry, oc.strike, oc."right"
        """,
        [symbol],
    ).arrow()
    return pl.from_arrow(result)


def insert_underlying_quote(con: duckdb.DuckDBPyConnection, symbol: str, ts: dt.datetime, spot: float) -> None:
    con.execute(
        "INSERT INTO underlying_quotes (symbol, ts, spot) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
        [symbol, ts, spot],
    )


def latest_spot(con: duckdb.DuckDBPyConnection, symbol: str) -> float | None:
    row = con.execute(
        "SELECT spot FROM underlying_quotes WHERE symbol = ? ORDER BY ts DESC LIMIT 1",
        [symbol],
    ).fetchone()
    return float(row[0]) if row else None


def recent_snapshot_timestamps(con: duckdb.DuckDBPyConnection, symbol: str, n: int = 2) -> list:
    result = con.execute(
        """
        SELECT DISTINCT cs.ts
        FROM chain_snapshots cs
        JOIN option_contracts oc USING (contract_id)
        WHERE oc.underlying = ?
        ORDER BY cs.ts DESC
        LIMIT ?
        """,
        [symbol, n],
    ).fetchall()
    return [row[0] for row in result]


def chain_snapshot_at(con: duckdb.DuckDBPyConnection, symbol: str, ts) -> pl.DataFrame:
    result = con.execute(
        """
        SELECT oc.underlying, oc.expiry, oc.strike, oc."right", cs.*
        FROM chain_snapshots cs
        JOIN option_contracts oc USING (contract_id)
        WHERE oc.underlying = ? AND cs.ts = ?
        ORDER BY oc.expiry, oc.strike, oc."right"
        """,
        [symbol, ts],
    ).arrow()
    return pl.from_arrow(result)


def insert_signals(con: duckdb.DuckDBPyConnection, signals: list[dict]) -> None:
    if not signals:
        return
    rows = [(s["ts"], s["symbol"], s["rule_name"], s["score"], json.dumps(s.get("payload", {})))
            for s in signals]
    con.executemany(
        """
        INSERT INTO signals (ts, symbol, rule_name, score, payload)
        VALUES (?, ?, ?, ?, CAST(? AS JSON))
        """,
        rows,
    )


def latest_signals(con: duckdb.DuckDBPyConnection, symbol: str | None = None,
                    rule_name: str | None = None, limit: int = 200) -> pl.DataFrame:
    query = "SELECT * FROM signals WHERE 1=1"
    params: list = []
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    if rule_name:
        query += " AND rule_name = ?"
        params.append(rule_name)
    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    return pl.from_arrow(con.execute(query, params).arrow())


def export_daily_parquet(con: duckdb.DuckDBPyConnection, storage: StorageConfig,
                          trade_date: dt.date) -> str:
    """Export one day's chain snapshots to a partitioned Parquet file
    (manual sec 2.12 'Retention', sec 4.3 storage math)."""
    out_dir = storage.resolved_parquet_dir() / f"dt={trade_date:%Y-%m-%d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "chain_snapshots.parquet"
    con.execute(
        """
        COPY (
            SELECT cs.*, oc.underlying, oc.expiry, oc.strike, oc."right"
            FROM chain_snapshots cs
            JOIN option_contracts oc USING (contract_id)
            WHERE CAST(cs.ts AS DATE) = ?
        ) TO ? (FORMAT PARQUET)
        """,
        [trade_date, str(out_path)],
    )
    return str(out_path)
