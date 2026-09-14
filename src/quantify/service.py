"""Shared query/analytics functions used by both the FastAPI layer and the
Streamlit UI, so the two front ends stay consistent (sec 2.11 architecture:
both sit on top of the same Greeks/Scanner/Backtester engines)."""
from __future__ import annotations

import duckdb
import polars as pl

from .config import QuantifyConfig
from .scanner import flow as flow_mod
from .scanner import gex as gex_mod
from .scanner import rules
from .storage import repo


def get_chain(con: duckdb.DuckDBPyConnection, symbol: str) -> pl.DataFrame:
    return repo.latest_chain(con, symbol)


def get_gex_summary(con: duckdb.DuckDBPyConnection, config: QuantifyConfig, symbol: str) -> dict:
    df = repo.latest_chain(con, symbol)
    spot = repo.latest_spot(con, symbol)
    if df.is_empty() or spot is None:
        return {"symbol": symbol, "spot": spot, "total_gex": None, "max_pain": None,
                "call_wall": None, "put_wall": None, "gamma_flip": None}

    walls = gex_mod.call_put_walls(df)
    return {
        "symbol": symbol,
        "spot": spot,
        "total_gex": gex_mod.total_gex(df, spot),
        "max_pain": gex_mod.max_pain(df),
        "call_wall": walls["call_wall"],
        "put_wall": walls["put_wall"],
        "gamma_flip": gex_mod.gamma_flip(df, spot, config.greeks.risk_free_rate),
    }


def get_scan(con: duckdb.DuckDBPyConnection, config: QuantifyConfig, symbol: str) -> dict:
    df = repo.latest_chain(con, symbol)
    if df.is_empty():
        return {"symbol": symbol, "unusual_count": 0, "put_call_ratio": None,
                "pc_sentiment": None, "net_premium": None, "unusual_activity": []}
    result = rules.scan_symbol(
        df,
        vol_oi_multiple=config.scanner.vol_oi_multiple,
        min_volume=config.scanner.min_volume,
        bullish_below=config.scanner.pc_ratio_bullish_below,
        bearish_above=config.scanner.pc_ratio_bearish_above,
    )
    result["symbol"] = symbol
    result["unusual_activity"] = result["unusual_activity"].to_dicts()
    return result


def get_flow(con: duckdb.DuckDBPyConnection, symbol: str, min_premium: float = 0.0) -> pl.DataFrame:
    timestamps = repo.recent_snapshot_timestamps(con, symbol, n=2)
    if len(timestamps) < 2:
        return pl.DataFrame()
    curr_ts, prev_ts = timestamps[0], timestamps[1]
    curr = repo.chain_snapshot_at(con, symbol, curr_ts)
    prev = repo.chain_snapshot_at(con, symbol, prev_ts)
    inferred = flow_mod.infer_flow_from_snapshots(prev, curr)
    if inferred.is_empty():
        return inferred
    return inferred.filter(pl.col("premium") >= min_premium)
