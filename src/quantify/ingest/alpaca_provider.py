"""Alpaca provider (manual sec 2.10: 'STRONG: brokerage + options data +
paper trading'). Needs ALPACA_API_KEY / ALPACA_SECRET_KEY in .env.

Caveat, stated plainly: implemented against Alpaca's documented Market Data
API v2 (stock bars) and v1beta1 (options snapshots) response shapes, but
there are no Alpaca credentials available in this environment to exercise it
live -- parsing is covered by tests using mocked HTTP responses
(tests/test_alpaca_provider.py), not a real account. Alpaca's options feed
may not report open_interest (defaults to 0 if absent); verify field names
against Alpaca's current docs and a real key before relying on this for
anything beyond a starting point.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import re

import pandas as pd
import polars as pl
import requests

logger = logging.getLogger(__name__)

DATA_BASE_URL = "https://data.alpaca.markets"
PERIOD_TO_DAYS = {"1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 3650}

# OCC-style option symbol: ROOT + YYMMDD + C/P + strike*1000, zero-padded to 8 digits
# e.g. "AAPL260116C00150000" -> AAPL, 2026-01-16, call, strike 150.0
OCC_SYMBOL_RE = re.compile(r"^(?P<root>[A-Z]+)(?P<date>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")


def _parse_occ_symbol(occ_symbol: str) -> dict | None:
    m = OCC_SYMBOL_RE.match(occ_symbol)
    if not m:
        return None
    return {
        "expiry": dt.datetime.strptime(m.group("date"), "%y%m%d").date(),
        "right": m.group("right"),
        "strike": int(m.group("strike")) / 1000.0,
    }


class AlpacaProvider:
    name = "alpaca"

    def __init__(self, api_key: str | None = None, secret_key: str | None = None):
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY")
        self.secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY")
        if not self.api_key or not self.secret_key:
            raise RuntimeError("AlpacaProvider requires ALPACA_API_KEY and ALPACA_SECRET_KEY (see .env.example)")
        self.headers = {"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.secret_key}

    def _get(self, path: str, params: dict) -> dict:
        resp = requests.get(f"{DATA_BASE_URL}{path}", headers=self.headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def fetch_spot(self, symbol: str) -> float:
        data = self._get(f"/v2/stocks/{symbol}/trades/latest", {})
        trade = data.get("trade")
        if not trade or "p" not in trade:
            raise RuntimeError(f"Alpaca: no latest trade for {symbol!r}")
        return float(trade["p"])

    def fetch_chain(self, symbol: str, max_expiries: int = 6) -> pl.DataFrame:
        rows = []
        page_token = None
        seen_expiries: set[dt.date] = set()

        while True:
            params = {"feed": "indicative", "limit": 1000}
            if page_token:
                params["page_token"] = page_token
            data = self._get(f"/v1beta1/options/snapshots/{symbol}", params)
            snapshots = data.get("snapshots") or {}

            for occ_symbol, snap in snapshots.items():
                parsed = _parse_occ_symbol(occ_symbol)
                if parsed is None:
                    continue
                if parsed["expiry"] not in seen_expiries and len(seen_expiries) >= max_expiries:
                    continue
                seen_expiries.add(parsed["expiry"])

                quote = snap.get("latestQuote") or {}
                trade = snap.get("latestTrade") or {}
                rows.append({
                    "underlying": symbol, "expiry": parsed["expiry"], "strike": parsed["strike"],
                    "right": parsed["right"],
                    "bid": float(quote.get("bp") or 0.0), "ask": float(quote.get("ap") or 0.0),
                    "last": float(trade.get("p") or 0.0),
                    "volume": int(trade.get("s") or 0),
                    # Alpaca's options feed may not report open interest at all.
                    "open_interest": int(snap.get("openInterest") or 0),
                })

            page_token = data.get("next_page_token")
            if not page_token or len(seen_expiries) >= max_expiries:
                break

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
            f"/v2/stocks/{symbol}/bars",
            {"timeframe": "1Day", "start": start.isoformat(), "end": end.isoformat(), "limit": 10000},
        )
        bars = data.get("bars") or []
        if not bars:
            raise RuntimeError(f"Alpaca: no price history for {symbol!r}")

        df = pd.DataFrame(bars)
        df["date"] = pd.to_datetime(df["t"])
        df = df.set_index("date").rename(
            columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
        )
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_corporate_actions(self, symbol: str) -> pd.DataFrame:
        logger.info("AlpacaProvider: corporate-action detection not implemented, skipping")
        return pd.DataFrame(columns=["date", "action_type", "value"])

    def fetch_sector(self, symbol: str) -> str | None:
        logger.info("AlpacaProvider: sector lookup not implemented, skipping")
        return None
