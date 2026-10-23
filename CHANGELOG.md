# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [Semantic Versioning](https://semver.org/) (manual §4.8: "semantic
versioning; changelog discipline; tag releases").

## [0.1.0] — 2026-10-23

First feature-complete release: implements the full FR-001–FR-018 /
NFR-001–NFR-010 list and Part 4 (Maintenance Guide) of the design manual
(`Quantify.pdf`).

### Added

- Options chain ingestion (yfinance, Tradier, Alpaca), with retry-with-backoff
  on transient provider failures and corporate-action (split/dividend)
  detection that flags potentially-stale cached contracts
- Local Black-Scholes Greeks + implied volatility, computed independently of
  the data provider
- DuckDB + Parquet storage, with automated daily EOD archiving and a vacuum/
  compact maintenance command
- Scanner: unusual options activity, put/call ratio, net premium
- Inferred flow feed (snapshot-diff + quote/tick-rule aggressor classification)
- GEX, gamma flip, call/put walls, max pain
- Sector flow heatmap across the watchlist
- Vectorized backtesting engine (fees/slippage, no look-ahead) with Deflated
  Sharpe Ratio / Minimum Track Record Length overfitting checks
- Telegram/desktop alerting on unusual activity, with dedup
- Paper-trading journal (positions, reasons, P&L — no broker execution)
- Watchlist management, generic CSV/Parquet export, config hot-reload (UI)
- FastAPI service layer + 7-tab Streamlit dashboard
- Docker / Docker Compose packaging
- Structured JSON logging (rotated) and an ingestion health/metrics view
  (`GET /health`, dashboard sidebar)
- `pip-audit`-backed dependency vulnerability scanning, wired into CI
- GitHub Actions CI (test suite on every push/PR)
- `README.md` (developer-facing) and `USER_GUIDE.md` (end-user-facing,
  with inline definitions of every finance/options term used)

### Fixed

- A DuckDB reserved-keyword collision (`right` as a bare column name)
- Polars schema inference choking on nullable Greek columns during ingestion
- `pl.from_arrow()` throwing on a genuinely empty query result (switched to
  DuckDB's native `.pl()` conversion throughout)
- A DuckDB `COPY ... TO ?` statement incorrectly trying to bind the target
  filename as a query parameter (not supported; must be a SQL literal)
- A JSON-path SQL operator-precedence bug in the alert-dedup query
  (`payload->>'k' = ?` parsed as `payload ->> ('k' = ?)`)
- `urllib3` CVEs (2.7.0 → 2.8.0) found by the newly-added `pip-audit`
  integration

### Known limitations

- Tradier/Alpaca adapters are implemented against each API's documented
  shape but untested against a live account (no credentials available in
  development)
- Corporate-action and sector detection are yfinance-only
- Pillow stays on 12.3.0 (several CVEs, fixed in 13.0.0) because Streamlit
  itself pins `pillow<13` — blocked upstream, not fixable from here
- No real broker execution (paper trading only, by design)
