"""Aggressor-side classification and snapshot-diff-based inferred flow
(manual sec 1.4 'Aggressor side / trade-side classification' and sec 2.10:
free data uses 'EOD chain snapshots, volume/OI deltas, delayed quotes, and
snapshot-diff-based inferred flow' since there's no true tick-by-tick feed).

Accuracy caveat straight from the manual: Lee-Ready-style inference is a
"useful-but-imperfect ~80% signal, not ground truth" (sec 1.4).
"""
from __future__ import annotations

import polars as pl


def classify_aggressor(price: float, bid: float, ask: float, prev_price: float | None = None) -> str:
    """Quote rule (trade vs mid) with tick-rule fallback for midpoint trades
    -- the Lee-Ready proxy from Appendix E's sample `aggressor()`."""
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        if price > mid:
            return "B"
        if price < mid:
            return "S"
    if prev_price is None:
        return "?"
    if price > prev_price:
        return "B"
    if price < prev_price:
        return "S"
    return "?"


def infer_flow_from_snapshots(prev: pl.DataFrame, curr: pl.DataFrame) -> pl.DataFrame:
    """Diff two consecutive chain snapshots (same contracts) to approximate a
    trade-level flow row per contract: how many new contracts traded since
    the last snapshot, and the inferred aggressor side. This is the
    snapshot-diff proxy described in sec 2.10 -- not real time-and-sales."""
    joined = curr.join(
        prev.select(["contract_id", "volume", "last"]).rename({"volume": "prev_volume", "last": "prev_last"}),
        on="contract_id",
        how="left",
    ).with_columns(pl.col("prev_volume").fill_null(0))

    joined = joined.with_columns(
        (pl.col("volume") - pl.col("prev_volume")).clip(lower_bound=0).alias("volume_delta")
    )
    joined = joined.filter(pl.col("volume_delta") > 0)
    if joined.is_empty():
        return joined

    rows = joined.to_dicts()
    for r in rows:
        r["aggressor"] = classify_aggressor(r["last"], r["bid"], r["ask"], r.get("prev_last"))
        r["premium"] = r["volume_delta"] * r["mid"] * 100

    return pl.DataFrame(rows).sort("premium", descending=True)
