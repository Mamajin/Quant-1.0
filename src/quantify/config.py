"""TOML config loader -> typed models (manual sec 2.13: 'Config (TOML)')."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import BaseModel

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.toml"


class ProviderConfig(BaseModel):
    name: str = "yfinance"


class WatchlistConfig(BaseModel):
    symbols: list[str] = ["AAPL", "SPY"]
    max_symbols: int = 50

    def validated_symbols(self) -> list[str]:
        if len(self.symbols) > self.max_symbols:
            raise ValueError(
                f"watchlist has {len(self.symbols)} symbols, cap is {self.max_symbols} (FR-002)"
            )
        return self.symbols


class ScheduleConfig(BaseModel):
    refresh_minutes: int = 15
    market_hours_only: bool = True


class ScannerConfig(BaseModel):
    vol_oi_multiple: float = 3.0
    min_volume: int = 200
    pc_ratio_bullish_below: float = 0.7
    pc_ratio_bearish_above: float = 1.3


class GreeksConfig(BaseModel):
    risk_free_rate: float = 0.04


class StorageConfig(BaseModel):
    db_path: str = "data/quantify.duckdb"
    parquet_dir: str = "data/parquet"

    def resolved_db_path(self) -> Path:
        return REPO_ROOT / self.db_path

    def resolved_parquet_dir(self) -> Path:
        return REPO_ROOT / self.parquet_dir


class QuantifyConfig(BaseModel):
    provider: ProviderConfig = ProviderConfig()
    watchlist: WatchlistConfig = WatchlistConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    scanner: ScannerConfig = ScannerConfig()
    greeks: GreeksConfig = GreeksConfig()
    storage: StorageConfig = StorageConfig()


def load_config(path: str | Path | None = None) -> QuantifyConfig:
    config_path = Path(path) if path else Path(os.environ.get("QUANTIFY_CONFIG", DEFAULT_CONFIG_PATH))
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    return QuantifyConfig.model_validate(raw)
