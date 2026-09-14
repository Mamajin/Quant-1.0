"""TOML config loader -> typed models (manual sec 2.13: 'Config (TOML)')."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import tomlkit
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


class AlertsConfig(BaseModel):
    enabled: bool = False
    channels: list[str] = []  # subset of "telegram", "desktop"
    dedup_hours: float = 24.0  # don't re-alert the same contract within this window


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
    alerts: AlertsConfig = AlertsConfig()
    storage: StorageConfig = StorageConfig()


def resolve_config_path(path: str | Path | None = None) -> Path:
    return Path(path) if path else Path(os.environ.get("QUANTIFY_CONFIG", DEFAULT_CONFIG_PATH))


def load_config(path: str | Path | None = None) -> QuantifyConfig:
    config_path = resolve_config_path(path)
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    return QuantifyConfig.model_validate(raw)


def add_watchlist_symbol(symbol: str, path: str | Path | None = None) -> QuantifyConfig:
    """FR-002: add a symbol to the watchlist, enforcing the cap, and persist
    it back to config.toml (round-trips via tomlkit so comments/formatting
    survive)."""
    config_path = resolve_config_path(path)
    symbol = symbol.strip().upper()
    doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))

    symbols = list(doc["watchlist"]["symbols"])
    max_symbols = doc["watchlist"].get("max_symbols", WatchlistConfig().max_symbols)
    if symbol in symbols:
        return load_config(path)
    if len(symbols) >= max_symbols:
        raise ValueError(f"watchlist is at its cap of {max_symbols} symbols (FR-002)")

    symbols.append(symbol)
    doc["watchlist"]["symbols"] = symbols
    config_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return load_config(path)


def remove_watchlist_symbol(symbol: str, path: str | Path | None = None) -> QuantifyConfig:
    """FR-002: remove a symbol from the watchlist and persist the change."""
    config_path = resolve_config_path(path)
    symbol = symbol.strip().upper()
    doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))

    symbols = [s for s in doc["watchlist"]["symbols"] if s != symbol]
    doc["watchlist"]["symbols"] = symbols
    config_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return load_config(path)
