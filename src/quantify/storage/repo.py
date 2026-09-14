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
    # Use DuckDB's own .pl() rather than .arrow() + pl.from_arrow(): .arrow()
    # returns an unmaterialized RecordBatchReader, and polars' from_arrow()
    # errors on a genuinely empty result (0 record batches, e.g. before any
    # ingestion has run) with "Must pass schema, or at least one RecordBatch".
    return con.execute(
        """
        WITH latest AS (
            SELECT cs.*, ROW_NUMBER() OVER (PARTITION BY contract_id ORDER BY ts DESC) AS rn
            FROM chain_snapshots cs
            JOIN option_contracts oc USING (contract_id)
            WHERE oc.underlying = ?
        )
        SELECT oc.underlying, oc.expiry, oc.strike, oc."right", oc.is_adjusted, l.*
        FROM latest l
        JOIN option_contracts oc USING (contract_id)
        WHERE l.rn = 1
        ORDER BY oc.expiry, oc.strike, oc."right"
        """,
        [symbol],
    ).pl()


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
    return con.execute(
        """
        SELECT oc.underlying, oc.expiry, oc.strike, oc."right", oc.is_adjusted, cs.*
        FROM chain_snapshots cs
        JOIN option_contracts oc USING (contract_id)
        WHERE oc.underlying = ? AND cs.ts = ?
        ORDER BY oc.expiry, oc.strike, oc."right"
        """,
        [symbol, ts],
    ).pl()


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
    return con.execute(query, params).pl()


def signal_exists_since(con: duckdb.DuckDBPyConnection, symbol: str, rule_name: str,
                         contract_id: str, since: dt.datetime) -> bool:
    """Dedup check for alerting (manual FR-008): has this exact contract
    already fired this rule within the dedup window?"""
    row = con.execute(
        """
        SELECT 1 FROM signals
        WHERE symbol = ? AND rule_name = ? AND (payload->>'contract_id') = ? AND ts >= ?
        LIMIT 1
        """,
        [symbol, rule_name, contract_id, since],
    ).fetchone()
    return row is not None


def insert_signal(con: duckdb.DuckDBPyConnection, ts: dt.datetime, symbol: str,
                   rule_name: str, score: float, payload: dict) -> int:
    row = con.execute(
        "INSERT INTO signals (ts, symbol, rule_name, score, payload) VALUES (?, ?, ?, ?, CAST(? AS JSON)) RETURNING id",
        [ts, symbol, rule_name, score, json.dumps(payload)],
    ).fetchone()
    return int(row[0])


def insert_alert(con: duckdb.DuckDBPyConnection, signal_id: int, channel: str,
                  sent_ts: dt.datetime, status: str) -> None:
    con.execute(
        "INSERT INTO alerts (signal_id, channel, sent_ts, status) VALUES (?, ?, ?, ?)",
        [signal_id, channel, sent_ts, status],
    )


def corporate_action_exists(con: duckdb.DuckDBPyConnection, symbol: str,
                             action_date: dt.date, action_type: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM corporate_actions WHERE symbol = ? AND action_date = ? AND action_type = ? LIMIT 1",
        [symbol, action_date, action_type],
    ).fetchone()
    return row is not None


def insert_corporate_action(con: duckdb.DuckDBPyConnection, symbol: str, action_date: dt.date,
                             action_type: str, value: float, detected_ts: dt.datetime | None = None) -> int:
    row = con.execute(
        "INSERT INTO corporate_actions (symbol, action_date, action_type, value, detected_ts) "
        "VALUES (?, ?, ?, ?, ?) RETURNING id",
        [symbol, action_date, action_type, value, detected_ts or dt.datetime.now()],
    ).fetchone()
    return int(row[0])


def flag_contracts_adjusted(con: duckdb.DuckDBPyConnection, underlying: str, on_or_after: dt.date) -> int:
    """Flag existing option_contracts rows for `underlying` expiring on/after
    a detected split date as is_adjusted (FR-018): our locally cached
    strikes may predate the split and not reflect standard post-split
    deliverables. Returns the number of contracts flagged."""
    rows = con.execute(
        'UPDATE option_contracts SET is_adjusted = TRUE WHERE underlying = ? AND expiry >= ? '
        "AND is_adjusted = FALSE RETURNING contract_id",
        [underlying, on_or_after],
    ).fetchall()
    return len(rows)


def insert_position(con: duckdb.DuckDBPyConnection, symbol: str, contract_id: str | None,
                     qty: float, entry_price: float, entry_ts: dt.datetime) -> int:
    row = con.execute(
        "INSERT INTO positions (symbol, contract_id, qty, entry_price, entry_ts) VALUES (?, ?, ?, ?, ?) RETURNING id",
        [symbol, contract_id, qty, entry_price, entry_ts],
    ).fetchone()
    return int(row[0])


def close_position(con: duckdb.DuckDBPyConnection, position_id: int, exit_price: float,
                    exit_ts: dt.datetime, pnl: float) -> None:
    con.execute(
        'UPDATE positions SET exit_price = ?, exit_ts = ?, pnl = ? WHERE id = ?',
        [exit_price, exit_ts, pnl, position_id],
    )


def insert_journal_entry(con: duckdb.DuckDBPyConnection, position_id: int, reason_entry: str | None,
                          tags: str | None = None, notes: str | None = None) -> int:
    row = con.execute(
        "INSERT INTO journal (position_id, reason_entry, tags, notes) VALUES (?, ?, ?, ?) RETURNING id",
        [position_id, reason_entry, tags, notes],
    ).fetchone()
    return int(row[0])


def update_journal_exit_reason(con: duckdb.DuckDBPyConnection, position_id: int, reason_exit: str | None) -> None:
    con.execute("UPDATE journal SET reason_exit = ? WHERE position_id = ?", [reason_exit, position_id])


def open_positions(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    return con.execute(
        """
        SELECT p.*, j.reason_entry, j.tags, j.notes
        FROM positions p
        LEFT JOIN journal j ON j.position_id = p.id
        WHERE p.exit_ts IS NULL
        ORDER BY p.entry_ts DESC
        """
    ).pl()


def closed_positions(con: duckdb.DuckDBPyConnection, limit: int = 200) -> pl.DataFrame:
    return con.execute(
        """
        SELECT p.*, j.reason_entry, j.reason_exit, j.tags, j.notes
        FROM positions p
        LEFT JOIN journal j ON j.position_id = p.id
        WHERE p.exit_ts IS NOT NULL
        ORDER BY p.exit_ts DESC
        LIMIT ?
        """,
        [limit],
    ).pl()


def position_by_id(con: duckdb.DuckDBPyConnection, position_id: int) -> dict | None:
    row = con.execute("SELECT * FROM positions WHERE id = ?", [position_id]).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in con.description]
    return dict(zip(cols, row))


def insert_backtest_run(con: duckdb.DuckDBPyConnection, strategy: str, params: dict,
                         start: dt.date, end: dt.date, stats: dict) -> int:
    row = con.execute(
        """
        INSERT INTO backtest_runs (strategy, params, start, "end", sharpe, cagr, max_dd, profit_factor, created_ts)
        VALUES (?, CAST(? AS JSON), ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [strategy, json.dumps(params), start, end, stats.get("sharpe"), stats.get("cagr"),
         stats.get("max_drawdown"), stats.get("profit_factor"), dt.datetime.now()],
    ).fetchone()
    return int(row[0])


def latest_backtest_runs(con: duckdb.DuckDBPyConnection, limit: int = 50) -> pl.DataFrame:
    return con.execute("SELECT * FROM backtest_runs ORDER BY created_ts DESC LIMIT ?", [limit]).pl()


EXPORTABLE_TABLES = (
    "symbols", "option_contracts", "chain_snapshots", "trades_flow", "signals",
    "alerts", "backtest_runs", "positions", "journal", "corporate_actions", "underlying_quotes",
)


def export_table(con: duckdb.DuckDBPyConnection, table_name: str, limit: int | None = None) -> pl.DataFrame:
    """FR-014: fetch any known table for CSV/Parquet export. `table_name` is
    checked against an allowlist (EXPORTABLE_TABLES) since it's interpolated
    into SQL -- never pass through unvalidated user input."""
    if table_name not in EXPORTABLE_TABLES:
        raise ValueError(f"Unknown/disallowed table {table_name!r}; must be one of {EXPORTABLE_TABLES}")
    query = f"SELECT * FROM {table_name}"  # noqa: S608 - table_name is allowlist-checked above
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    return con.execute(query).pl()


def export_daily_parquet(con: duckdb.DuckDBPyConnection, storage: StorageConfig,
                          trade_date: dt.date) -> str:
    """Export one day's chain snapshots to a partitioned Parquet file
    (manual sec 2.12 'Retention', sec 4.3 storage math)."""
    out_dir = storage.resolved_parquet_dir() / f"dt={trade_date:%Y-%m-%d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "chain_snapshots.parquet"

    # DuckDB's COPY ... TO <target> does not accept a bound (?) parameter
    # for the target filename -- it must be a literal in the SQL text.
    # trade_date/out_path are internally constructed (not user input), so
    # embed them directly with SQL-literal escaping rather than binding.
    escaped_path = str(out_path).replace("'", "''")
    con.execute(
        f"""
        COPY (
            SELECT cs.*, oc.underlying, oc.expiry, oc.strike, oc."right"
            FROM chain_snapshots cs
            JOIN option_contracts oc USING (contract_id)
            WHERE CAST(cs.ts AS DATE) = DATE '{trade_date.isoformat()}'
        ) TO '{escaped_path}' (FORMAT PARQUET)
        """
    )
    return str(out_path)
