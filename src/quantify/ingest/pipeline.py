"""Ingestion pipeline: provider -> Greeks/IV -> storage (manual sec 1.2 'full
quant pipeline': Ingestion -> Cleaning -> Feature engineering -> ...).
"""
from __future__ import annotations

import datetime as dt
import logging

import polars as pl

from ..config import QuantifyConfig
from ..corporate_actions.detector import detect_and_flag
from ..greeks.bsm import all_greeks
from ..greeks.iv import solve_iv
from ..storage import repo
from .alpaca_provider import AlpacaProvider
from .base import Provider
from .tradier_provider import TradierProvider
from .yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)

PROVIDERS: dict[str, type] = {
    "yfinance": YFinanceProvider,
    "tradier": TradierProvider,
    "alpaca": AlpacaProvider,
}


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown provider {name!r}; available: {list(PROVIDERS)}") from exc


def _years_to_expiry(expiry: dt.date, as_of: dt.date) -> float:
    return max((expiry - as_of).days, 0) / 365.0


def process_chain(raw: pl.DataFrame, spot: float, risk_free_rate: float,
                   as_of: dt.date | None = None) -> pl.DataFrame:
    """Clean raw provider rows and attach mid/IV/Greeks (sec 1.2 'Cleaning' +
    'Feature engineering'). Returns rows ready for repo.insert_chain_snapshots
    (contract_id still needs to be added by the caller, which also knows the
    underlying-independent contract_id format)."""
    as_of = as_of or dt.date.today()
    if raw.is_empty():
        return raw

    rows = raw.to_dicts()
    out_rows = []
    for r in rows:
        bid, ask, last = r["bid"], r["ask"], r["last"]
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else last
        T = _years_to_expiry(r["expiry"], as_of)
        flag = "c" if r["right"] == "C" else "p"

        iv = None
        greeks = {"delta": None, "gamma": None, "theta": None, "vega": None, "rho": None}
        if mid > 0 and T > 0:
            iv = solve_iv(flag, spot, r["strike"], T, risk_free_rate, mid)
            if iv is not None:
                g = all_greeks(flag, spot, r["strike"], T, risk_free_rate, iv)
                greeks = {k: float(v) for k, v in g.items()}

        out_rows.append({
            **r,
            "mid": mid,
            "iv": iv,
            **greeks,
        })

    # Explicit schema: many rows legitimately have iv/Greeks = None (illiquid
    # strikes with no mid price), which otherwise confuses Polars' schema
    # inference (it samples only the first N rows) once a later row turns up
    # a real float.
    numeric_cols = {"mid": pl.Float64, "iv": pl.Float64, "delta": pl.Float64,
                     "gamma": pl.Float64, "theta": pl.Float64, "vega": pl.Float64, "rho": pl.Float64}
    return pl.DataFrame(out_rows, schema_overrides=numeric_cols)


def ingest_symbol(con, config: QuantifyConfig, provider: Provider, symbol: str,
                   ts: dt.datetime | None = None) -> int:
    ts = ts or dt.datetime.now()
    spot = provider.fetch_spot(symbol)
    raw = provider.fetch_chain(symbol)
    if raw.is_empty():
        logger.warning("No option chain returned for %s", symbol)
        return 0

    processed = process_chain(raw, spot, config.greeks.risk_free_rate, as_of=ts.date())

    contracts = [
        {
            "contract_id": repo.make_contract_id(row["underlying"], row["expiry"], row["right"], row["strike"]),
            "underlying": row["underlying"],
            "expiry": row["expiry"],
            "strike": row["strike"],
            "right": row["right"],
        }
        for row in processed.to_dicts()
    ]
    repo.upsert_symbol(con, symbol)
    repo.upsert_contracts(con, contracts)
    repo.insert_underlying_quote(con, symbol, ts, spot)

    if repo.symbol_sector(con, symbol) is None:
        try:
            sector = provider.fetch_sector(symbol)
            if sector:
                repo.update_symbol_sector(con, symbol, sector)
        except Exception as exc:  # noqa: BLE001 - sector lookup (FR-012) must never break ingestion
            logger.warning("Sector lookup failed for %s: %s", symbol, exc)

    try:
        detect_and_flag(con, provider, symbol)
    except Exception as exc:  # noqa: BLE001 - corporate-action detection must never break ingestion
        logger.warning("Corporate-action detection failed for %s: %s", symbol, exc)

    snapshot_df = processed.with_columns([
        pl.Series("contract_id", [c["contract_id"] for c in contracts]),
        pl.lit(ts).alias("ts"),
    ])
    return repo.insert_chain_snapshots(con, snapshot_df)


def run_ingestion(con, config: QuantifyConfig, symbols: list[str] | None = None) -> dict[str, int]:
    provider = get_provider(config.provider.name)
    targets = symbols or config.watchlist.validated_symbols()
    results: dict[str, int] = {}
    for symbol in targets:
        try:
            results[symbol] = ingest_symbol(con, config, provider, symbol)
        except Exception as exc:  # noqa: BLE001 - one bad symbol shouldn't kill the run
            logger.error("Ingestion failed for %s: %s", symbol, exc)
            results[symbol] = 0
    return results
