"""Scanner rules: unusual activity, P/C ratio, net premium (manual sec 1.5,
3.2, 3.5, and the sec 3.8 cheat-sheet thresholds)."""
from __future__ import annotations

import polars as pl


def with_vol_oi_ratio(df: pl.DataFrame) -> pl.DataFrame:
    """Vol/OI > 1 -> likely new positioning (sec 1.5)."""
    return df.with_columns(
        (pl.col("volume") / pl.when(pl.col("open_interest") > 0).then(pl.col("open_interest")).otherwise(1))
        .alias("vol_oi_ratio")
    )


def unusual_activity(df: pl.DataFrame, vol_oi_multiple: float = 3.0, min_volume: int = 200) -> pl.DataFrame:
    """Reference-site rule (sec 1.5/2.4/3.8): Vol > vol_oi_multiple * OI AND Vol >= min_volume."""
    df = with_vol_oi_ratio(df) if "vol_oi_ratio" not in df.columns else df
    flagged = df.with_columns(
        ((pl.col("volume") > vol_oi_multiple * pl.col("open_interest")) & (pl.col("volume") >= min_volume))
        .alias("is_unusual")
    )
    return flagged.filter(pl.col("is_unusual")).sort("volume", descending=True)


def put_call_ratio(df: pl.DataFrame, by: str = "volume") -> float:
    """P/C ratio by volume or open_interest (sec 3.5). <0.7 bullish, >1.3 bearish (contrarian at extremes)."""
    col = "volume" if by == "volume" else "open_interest"
    call_total = df.filter(pl.col("right") == "C")[col].sum()
    put_total = df.filter(pl.col("right") == "P")[col].sum()
    if not call_total:
        return float("inf") if put_total else 0.0
    return float(put_total) / float(call_total)


def classify_pc_sentiment(ratio: float, bullish_below: float = 0.7, bearish_above: float = 1.3) -> str:
    if ratio < bullish_below:
        return "bullish"
    if ratio > bearish_above:
        return "bearish"
    return "neutral"


def net_premium(df: pl.DataFrame) -> float:
    """Net premium = call premium - put premium, in dollars (sec 3.5).
    Premium per contract = mid * 100 (multiplier) * volume traded today."""
    priced = df.with_columns((pl.col("mid") * 100 * pl.col("volume")).alias("premium"))
    call_premium = priced.filter(pl.col("right") == "C")["premium"].sum() or 0.0
    put_premium = priced.filter(pl.col("right") == "P")["premium"].sum() or 0.0
    return float(call_premium) - float(put_premium)


def scan_symbol(df: pl.DataFrame, vol_oi_multiple: float = 3.0, min_volume: int = 200,
                 bullish_below: float = 0.7, bearish_above: float = 1.3) -> dict:
    """Full per-symbol scan combining the rules above (manual sec 1.5)."""
    unusual = unusual_activity(df, vol_oi_multiple, min_volume)
    pc_ratio = put_call_ratio(df, by="volume")
    return {
        "unusual_activity": unusual,
        "unusual_count": unusual.height,
        "put_call_ratio": pc_ratio,
        "pc_sentiment": classify_pc_sentiment(pc_ratio, bullish_below, bearish_above),
        "net_premium": net_premium(df),
    }
