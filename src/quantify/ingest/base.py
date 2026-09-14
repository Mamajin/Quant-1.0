"""Provider plugin interface (manual NFR-008: 'plugin interface for new data
providers'). Concrete adapters (Tradier, Alpaca, ...) can be added later
without touching ingestion/storage/scanner code -- they just implement this
Protocol.
"""
from __future__ import annotations

from typing import Protocol

import polars as pl

RAW_CHAIN_COLUMNS = [
    "underlying", "expiry", "strike", "right",  # 'C' | 'P'
    "bid", "ask", "last", "volume", "open_interest",
]


class Provider(Protocol):
    name: str

    def fetch_spot(self, symbol: str) -> float:
        """Latest/last-close price for the underlying."""
        ...

    def fetch_chain(self, symbol: str, max_expiries: int = 6) -> pl.DataFrame:
        """Raw option chain rows for the nearest `max_expiries` expiries.
        Columns: RAW_CHAIN_COLUMNS. No Greeks/IV -- those are computed
        locally in the greeks module so results are consistent across
        providers."""
        ...
