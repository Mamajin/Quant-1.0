"""yfinance provider -- the manual's documented zero-key MVP fallback
(sec 2.10: 'yfinance only as a fallback prototype'; sec 4.4: 'expect
yfinance to break -- test after each Yahoo change').

Delayed, unofficial, rate-limited. No Greeks/IV are trusted from yfinance;
they're recomputed locally (see greeks/) so all providers are consistent.
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd
import polars as pl
import yfinance as yf

logger = logging.getLogger(__name__)


class YFinanceProvider:
    name = "yfinance"

    def fetch_spot(self, symbol: str) -> float:
        ticker = yf.Ticker(symbol)
        try:
            price = ticker.fast_info.get("lastPrice")
            if price:
                return float(price)
        except Exception:  # noqa: BLE001 - yfinance internals are unstable
            pass
        hist = ticker.history(period="1d")
        if hist.empty:
            raise RuntimeError(f"yfinance: no spot price available for {symbol!r}")
        return float(hist["Close"].iloc[-1])

    def fetch_chain(self, symbol: str, max_expiries: int = 6) -> pl.DataFrame:
        ticker = yf.Ticker(symbol)
        try:
            expiries = ticker.options
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"yfinance: could not list expiries for {symbol!r}: {exc}") from exc

        frames: list[pd.DataFrame] = []
        for expiry_str in expiries[:max_expiries]:
            try:
                chain = ticker.option_chain(expiry_str)
            except Exception as exc:  # noqa: BLE001
                logger.warning("yfinance: skipping expiry %s for %s (%s)", expiry_str, symbol, exc)
                continue
            expiry = dt.datetime.strptime(expiry_str, "%Y-%m-%d").date()
            for right, df in (("C", chain.calls), ("P", chain.puts)):
                if df.empty:
                    continue
                sub = df[["strike", "bid", "ask", "lastPrice", "volume", "openInterest"]].copy()
                sub["underlying"] = symbol
                sub["expiry"] = expiry
                sub["right"] = right
                sub = sub.rename(columns={"lastPrice": "last", "openInterest": "open_interest"})
                frames.append(sub)

        if not frames:
            return pl.DataFrame(schema={
                "underlying": pl.Utf8, "expiry": pl.Date, "strike": pl.Float64, "right": pl.Utf8,
                "bid": pl.Float64, "ask": pl.Float64, "last": pl.Float64,
                "volume": pl.Int64, "open_interest": pl.Int64,
            })

        combined = pd.concat(frames, ignore_index=True)
        combined["volume"] = combined["volume"].fillna(0).astype("int64")
        combined["open_interest"] = combined["open_interest"].fillna(0).astype("int64")
        for col in ("bid", "ask", "last"):
            combined[col] = combined[col].fillna(0.0)

        return pl.from_pandas(combined)[
            ["underlying", "expiry", "strike", "right", "bid", "ask", "last", "volume", "open_interest"]
        ]

    def fetch_history(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval, auto_adjust=True)
        if hist.empty:
            raise RuntimeError(f"yfinance: no price history for {symbol!r}")
        hist = hist.rename(columns={"Open": "open", "High": "high", "Low": "low",
                                     "Close": "close", "Volume": "volume"})
        hist.index.name = "date"
        return hist[["open", "high", "low", "close", "volume"]]
