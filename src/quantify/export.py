"""CSV/Parquet byte serialization for exports (manual FR-014), shared by the
Streamlit UI and the API's /export endpoint."""
from __future__ import annotations

import io

import polars as pl


def to_csv_bytes(df: pl.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.write_csv(buf)
    return buf.getvalue()


def to_parquet_bytes(df: pl.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def to_bytes(df: pl.DataFrame, fmt: str) -> bytes:
    if fmt == "csv":
        return to_csv_bytes(df)
    if fmt == "parquet":
        return to_parquet_bytes(df)
    raise ValueError(f"Unsupported export format {fmt!r}; use 'csv' or 'parquet'")
