# Quantify

Local, free options-flow & quant-trading research app for US equities/ETFs.
Implements Phase 1 + Phase 2 + GEX/max-pain (Phase 3 analytics) of the design
manual (`Quantify.pdf`). Educational engineering reference — **not
investment, legal, or tax advice.**

## What's here

- Options chain ingestion via yfinance (free, delayed, no API key)
- Black-Scholes Greeks + implied volatility, computed locally (not trusted
  from the provider)
- Local storage in DuckDB + Parquet (`data/`, gitignored)
- Scanner: unusual activity (Vol > 3×OI & Vol ≥ 200), put/call ratio, net premium
- Inferred flow feed (snapshot-diff + quote/tick-rule aggressor classification)
- GEX (gamma exposure), gamma flip, call/put walls, max pain
- FastAPI service layer + Streamlit dashboard

## What's not here yet

Backtesting engine, Telegram/Discord alerting, paper-trading/journal, broker
execution, Docker packaging, Tradier/Alpaca adapters — see the plan / roadmap
in the manual (§2.14) for the phased order these are meant to land in.

## Setup

```bash
uv sync
```

## Run

```bash
# One-shot ingestion for the configured watchlist (config/config.toml)
uv run python -m quantify.ingest.cli run --once

# Or for specific symbols
uv run python -m quantify.ingest.cli run --once --symbols AAPL,SPY

# Continuous market-hours-aware scheduler
uv run python -m quantify.ingest.scheduler

# Dashboard
uv run streamlit run src/quantify/ui/app.py

# API
uv run uvicorn quantify.api.main:app --reload
```

## Test

```bash
uv run pytest
```

## Config

Edit `config/config.toml` — watchlist, refresh interval, scanner thresholds,
provider selection. No API keys are required for the default `yfinance`
provider; `.env.example` documents placeholders for future providers
(Tradier, Alpaca) and alerting (Telegram).
