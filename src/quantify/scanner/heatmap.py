"""Sector flow heatmap (manual sec 2.4: 'Market Tide / Sector Flow heatmap',
FR-012 'Watchlist/heatmap views')."""
from __future__ import annotations

import polars as pl

from ..storage import repo
from . import rules


def sector_flow(con, symbols: list[str]) -> pl.DataFrame:
    """Per-symbol net premium + P/C ratio + sector. Symbols with no chain
    data yet, or an unknown sector (fetch_sector best-effort/not
    implemented for every provider), are included with sector='Unknown'
    rather than silently dropped."""
    rows = []
    for symbol in symbols:
        chain_df = repo.latest_chain(con, symbol)
        sector = repo.symbol_sector(con, symbol) or "Unknown"
        if chain_df.is_empty():
            rows.append({"symbol": symbol, "sector": sector, "net_premium": None, "put_call_ratio": None})
            continue
        rows.append({
            "symbol": symbol,
            "sector": sector,
            "net_premium": rules.net_premium(chain_df),
            "put_call_ratio": rules.put_call_ratio(chain_df),
        })
    return pl.DataFrame(rows, schema_overrides={"net_premium": pl.Float64, "put_call_ratio": pl.Float64})


def sector_summary(flow_df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate per-symbol flow rows into per-sector totals, sorted by
    total net premium (most bullish tilt first)."""
    valid = flow_df.filter(pl.col("net_premium").is_not_null())
    if valid.is_empty():
        return pl.DataFrame(schema={"sector": pl.Utf8, "total_net_premium": pl.Float64, "n_symbols": pl.UInt32})
    return (
        valid.group_by("sector")
        .agg([
            pl.col("net_premium").sum().alias("total_net_premium"),
            pl.col("symbol").count().alias("n_symbols"),
        ])
        .sort("total_net_premium", descending=True)
    )
