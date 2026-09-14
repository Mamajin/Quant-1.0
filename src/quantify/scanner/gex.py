"""GEX (gamma exposure) and max pain (manual sec 3.5, 1.7, FR-017).

GEX caveat, straight from the manual: "GEX depends on a modeling assumption
about the sign of dealer inventory and describes volatility sensitivity, not
direction." We use the common retail convention -- dealers are modeled as
net long the gamma from calls they've sold (they hedge by buying the
underlying as it rises) and net short the gamma from puts they've sold
(hedge by selling as it falls) -- i.e. dealer_gamma = call_gamma*call_OI -
put_gamma*put_OI. Positive total GEX -> dealer hedging dampens moves
(range-bound); negative -> amplifies moves (sec 3.5).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl

from ..greeks.bsm import gamma as bsm_gamma

CONTRACT_MULTIPLIER = 100


def dollar_gex_by_strike(df: pl.DataFrame, spot: float) -> pl.DataFrame:
    """Net dollar GEX per 1% move, aggregated by strike (sec 3.5 formula:
    Dollar GEX per 1% move = Gamma x dealer position x 100 x spot^2 x 0.01)."""
    signed = df.with_columns(
        pl.when(pl.col("right") == "C").then(pl.col("open_interest")).otherwise(-pl.col("open_interest"))
        .alias("signed_oi")
    ).with_columns(
        (pl.col("gamma") * pl.col("signed_oi") * CONTRACT_MULTIPLIER * spot**2 * 0.01).alias("dollar_gex")
    )
    return (
        signed.group_by("strike")
        .agg(pl.col("dollar_gex").sum())
        .sort("strike")
    )


def total_gex(df: pl.DataFrame, spot: float) -> float:
    by_strike = dollar_gex_by_strike(df, spot)
    return float(by_strike["dollar_gex"].sum()) if not by_strike.is_empty() else 0.0


def call_put_walls(df: pl.DataFrame) -> dict:
    """Heaviest-OI strikes: call wall = resistance, put wall = support (sec 2.4, 3.5)."""
    calls = df.filter(pl.col("right") == "C")
    puts = df.filter(pl.col("right") == "P")
    call_wall = None
    put_wall = None
    if not calls.is_empty():
        by_strike = calls.group_by("strike").agg(pl.col("open_interest").sum()).sort("open_interest", descending=True)
        call_wall = float(by_strike["strike"][0])
    if not puts.is_empty():
        by_strike = puts.group_by("strike").agg(pl.col("open_interest").sum()).sort("open_interest", descending=True)
        put_wall = float(by_strike["strike"][0])
    return {"call_wall": call_wall, "put_wall": put_wall}


def max_pain(df: pl.DataFrame) -> float | None:
    """Strike minimizing total remaining option value at expiry (Option Pain
    theory, sec 3.5/3.6)."""
    strikes = df["strike"].unique().sort().to_list()
    if not strikes:
        return None
    calls = df.filter(pl.col("right") == "C").select(["strike", "open_interest"])
    puts = df.filter(pl.col("right") == "P").select(["strike", "open_interest"])

    call_strikes = calls["strike"].to_numpy()
    call_oi = calls["open_interest"].to_numpy()
    put_strikes = puts["strike"].to_numpy()
    put_oi = puts["open_interest"].to_numpy()

    best_strike, best_value = None, float("inf")
    for candidate in strikes:
        call_value = float(np.sum(np.maximum(candidate - call_strikes, 0.0) * call_oi))
        put_value = float(np.sum(np.maximum(put_strikes - candidate, 0.0) * put_oi))
        total = call_value + put_value
        if total < best_value:
            best_value, best_strike = total, candidate
    return float(best_strike) if best_strike is not None else None


def gamma_flip(df: pl.DataFrame, spot: float, risk_free_rate: float, as_of: dt.date | None = None,
               spot_range_pct: float = 0.15, n_points: int = 61) -> float | None:
    """Spot price where net dealer gamma crosses zero (sec 3.5), found by
    recomputing gamma across a spot grid using each contract's own strike/IV/T."""
    as_of = as_of or dt.date.today()
    needed = {"strike", "right", "iv", "open_interest", "expiry"}
    if df.is_empty() or not needed.issubset(df.columns):
        return None

    rows = df.filter(pl.col("iv").is_not_null() & (pl.col("open_interest") > 0)).to_dicts()
    if not rows:
        return None

    strikes = np.array([r["strike"] for r in rows])
    ivs = np.array([r["iv"] for r in rows])
    ois = np.array([r["open_interest"] for r in rows])
    signs = np.array([1.0 if r["right"] == "C" else -1.0 for r in rows])
    T = np.array([max((r["expiry"] - as_of).days, 0) / 365.0 for r in rows])
    T = np.where(T <= 0, 1e-6, T)

    grid = np.linspace(spot * (1 - spot_range_pct), spot * (1 + spot_range_pct), n_points)
    net_gex = np.empty_like(grid)
    for i, s in enumerate(grid):
        g = bsm_gamma("c", s, strikes, T, risk_free_rate, ivs)
        net_gex[i] = np.sum(g * signs * ois * CONTRACT_MULTIPLIER * s**2 * 0.01)

    sign_changes = np.where(np.diff(np.sign(net_gex)) != 0)[0]
    if len(sign_changes) == 0:
        return None
    idx = sign_changes[0]
    x0, x1 = grid[idx], grid[idx + 1]
    y0, y1 = net_gex[idx], net_gex[idx + 1]
    if y1 == y0:
        return float(x0)
    return float(x0 - y0 * (x1 - x0) / (y1 - y0))
