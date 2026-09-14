# Quantify

Local, free options-flow & quant-trading research app for US equities/ETFs.
Implements the full roadmap (§2.14) of the design manual (`Quantify.pdf`):
Phase 1 through Phase 4. Educational engineering reference — **not
investment, legal, or tax advice.**

## What's here

- Options chain ingestion via yfinance (free, delayed, no API key), plus
  Tradier and Alpaca provider adapters (need credentials — see Config below)
- Black-Scholes Greeks + implied volatility, computed locally (not trusted
  from the provider)
- Local storage in DuckDB + Parquet (`data/`, gitignored)
- Scanner: unusual activity (Vol > 3×OI & Vol ≥ 200), put/call ratio, net premium
- Inferred flow feed (snapshot-diff + quote/tick-rule aggressor classification)
- GEX (gamma exposure), gamma flip, call/put walls, max pain
- Backtesting engine (vectorized, fees/slippage, no look-ahead) + Deflated
  Sharpe Ratio / Minimum Track Record Length overfitting checks
- Telegram/desktop alerting on unusual activity, with dedup
- Paper-trading journal (positions + reasons + P&L, no broker execution)
- Corporate-action detection (splits/dividends) that flags option contracts
  whose cached strikes may predate a split
- FastAPI service layer + Streamlit dashboard (6 tabs: Chain Viewer,
  Scanner, Flow Feed, GEX/Max Pain, Backtest, Journal)
- Docker / Docker Compose packaging

## What's not fully here

- Corporate-action detection only implemented for the yfinance provider
  (Tradier/Alpaca adapters return no actions — documented gap, not silent)
- Tradier/Alpaca adapters are implemented against each API's documented
  shape but untested live (no credentials available in development) —
  verify against a real account before relying on them
- No real broker execution (paper trading only, by design)

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

# Backtest a symbol (SMA crossover)
uv run python -m quantify.backtest.cli run --symbol AAPL --period 2y

# One-shot ingestion + alert check
uv run python -m quantify.ingest.cli run --once --alert
```

## Test

```bash
uv run pytest              # add --extra dev if you haven't `uv sync`'d dev deps
```

## Config

Edit `config/config.toml` — watchlist, refresh interval, scanner thresholds,
provider selection, alerting. No API keys are required for the default
`yfinance` provider; copy `.env.example` to `.env` and fill in what you
actually have for Tradier/Alpaca (data providers) or Telegram (alerts).

## Docker

```bash
cp .env.example .env        # only needed for alerts / Tradier / Alpaca
docker compose up --build   # dashboard at http://localhost:8501
```

`docker-compose.yml` also defines `api` and `scheduler` as opt-in profiles
(`docker compose --profile api up`). **Don't run more than one of
ui/api/scheduler against the same `./data` at once** — DuckDB is
single-writer (manual §2.9); see the comment at the top of the compose file.
