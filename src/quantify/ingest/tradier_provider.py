"""Tradier provider (manual sec 2.10: 'STRONG free-ish option: chains +
Greeks + T&S'). Needs TRADIER_TOKEN in .env (sandbox or production token).

Caveat, stated plainly: this is implemented against Tradier's documented
REST API shape (stable, versioned /v1 endpoints), but there is no Tradier
token available in this environment to exercise it live -- parsing is
covered by tests using mocked HTTP responses (tests/test_tradier_provider.py),
not a real account. Verify against a real sandbox token before relying on it.
"""
from __future__ import annotations

import datetime as dt
import logging
import os

import pandas as pd
import polars as pl
import requests

logger = logging.getLogger(__name__)

SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1"
PRODUCTION_BASE_URL = "https://api.tradier.com/v1"

PERIOD_TO_DAYS = {"1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 3650}


class TradierProvider:
    name = "tradier"

    def __init__(self, token: str | None = None, sandbox: bool = True):
        self.token = token or os.environ.get("TRADIER_TOKEN")
        if not self.token:
            raise RuntimeError("TradierProvider requires TRADIER_TOKEN (see .env.example)")
        self.base_url = SANDBOX_BASE_URL if sandbox else PRODUCTION_BASE_URL
        self.headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def _get(self, path: str, params: dict) -> dict:
        resp = requests.get(f"{self.base_url}{path}", headers=self.headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def fetch_spot(self, symbol: str) -> float:
        data = self._get("/markets/quotes", {"symbols": symbol})
        quote = data.get("quotes", {}).get("quote")
        if quote is None:
            raise RuntimeError(f"Tradier: no quote for {symbol!r}")
        if isinstance(quote, list):
            quote = quote[0]
        return float(quote["last"])

    def fetch_chain(self, symbol: str, max_expiries: int = 6) -> pl.DataFrame:
        exp_data = self._get("/markets/options/expirations", {"symbol": symbol, "includeAllRoots": "true"})
        expirations = (exp_data.get("expirations") or {}).get("date") or []
        if isinstance(expirations, str):
            expirations = [expirations]

        rows = []
        for expiry_str in expirations[:max_expiries]:
            chain_data = self._get(
                "/markets/options/chains", {"symbol": symbol, "expiration": expiry_str, "greeks": "false"}
            )
            options = (chain_data.get("options") or {}).get("option") or []
            if isinstance(options, dict):
                options = [options]
            expiry = dt.datetime.strptime(expiry_str, "%Y-%m-%d").date()
            for opt in options:
                rows.append({
                    "underlying": symbol, "expiry": expiry, "strike": float(opt["strike"]),
                    "right": "C" if opt["option_type"] == "call" else "P",
                    "bid": float(opt.get("bid") or 0.0), "ask": float(opt.get("ask") or 0.0),
                    "last": float(opt.get("last") or 0.0), "volume": int(opt.get("volume") or 0),
                    "open_interest": int(opt.get("open_interest") or 0),
                })

        if not rows:
            return pl.DataFrame(schema={
                "underlying": pl.Utf8, "expiry": pl.Date, "strike": pl.Float64, "right": pl.Utf8,
                "bid": pl.Float64, "ask": pl.Float64, "last": pl.Float64,
                "volume": pl.Int64, "open_interest": pl.Int64,
            })
        return pl.DataFrame(rows)

    def fetch_history(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        days = PERIOD_TO_DAYS.get(period, 730)
        end = dt.date.today()
        start = end - dt.timedelta(days=days)
        data = self._get(
            "/markets/history",
            {"symbol": symbol, "interval": "daily", "start": start.isoformat(), "end": end.isoformat()},
        )
        day_rows = (data.get("history") or {}).get("day") or []
        if isinstance(day_rows, dict):
            day_rows = [day_rows]
        if not day_rows:
            raise RuntimeError(f"Tradier: no price history for {symbol!r}")

        df = pd.DataFrame(day_rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_corporate_actions(self, symbol: str) -> pd.DataFrame:
        logger.info("TradierProvider: corporate-action detection not implemented (no simple endpoint), skipping")
        return pd.DataFrame(columns=["date", "action_type", "value"])
