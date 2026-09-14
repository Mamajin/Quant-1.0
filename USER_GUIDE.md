# Quantify — User Guide

This guide walks through actually *using* the app: setting it up, reading
each dashboard screen, and understanding the numbers it shows you. It
assumes no finance background — every term is defined in plain English the
first time it shows up, with the formula behind it where that helps. If you
just want a fast reference for a term you've already seen, jump to the
[Glossary](#glossary) at the end.

**This app is an educational research tool, not investment advice.** It
helps you look at options data and test ideas; it does not tell you what to
buy or sell. See [Limitations & honest expectations](#limitations--honest-expectations)
before you trust anything it shows you.

## Contents

1. [Setup](#1-setup)
2. [Getting data in](#2-getting-data-in)
3. [The Dashboard](#3-the-dashboard)
4. [Alerts](#4-alerts)
5. [Keeping data fresh automatically](#5-keeping-data-fresh-automatically-the-scheduler)
6. [Using the API instead of the dashboard](#6-using-the-api-instead-of-the-dashboard)
7. [Running with Docker](#7-running-with-docker)
8. [Configuration reference](#8-configuration-reference)
9. [Glossary](#glossary)
10. [Limitations & honest expectations](#limitations--honest-expectations)
11. [Troubleshooting](#troubleshooting)

---

## 1. Setup

You need [uv](https://docs.astral.sh/uv/) (a Python package manager) installed.
Everything else installs automatically.

```bash
uv sync
```

This creates a local `.venv` folder with every dependency the app needs,
pinned to exact versions (so it behaves the same on any machine). No
options-data API key is required to get started — the default data source
(**yfinance**) is free and needs no sign-up.

## 2. Getting data in

Quantify doesn't come with data pre-loaded — you pull it yourself, on
demand, from a **provider** (a company/service that supplies market data;
by default, Yahoo Finance via the `yfinance` library).

Run one **ingestion** (the process of fetching data and saving it locally)
pass from the terminal:

```bash
uv run python -m quantify.ingest.cli run --once --symbols AAPL,SPY
```

This fetches the current **option chain** (see [Glossary](#glossary)) for
AAPL and SPY and saves it to a local database file at `data/quantify.duckdb`.
Leave off `--symbols` and it uses whatever's in your **watchlist** (the list
of tickers you're tracking — see [§8](#8-configuration-reference)) instead.

You can also trigger a refresh from inside the dashboard (below) — no need
to touch the terminal again once it's running.

**A note on freshness:** the free data used here is delayed roughly 15
minutes, and it's a snapshot at the moment you fetch it, not a live stream.
Every time you want current numbers, you need to refresh.

## 3. The Dashboard

Launch it with:

```bash
uv run streamlit run src/quantify/ui/app.py
```

This opens a browser tab (usually `http://localhost:8501`). The sidebar on
the left is shared across every tab; the main area changes per tab.

### Sidebar

- **Symbol** — pick which ticker the tabs are currently showing.
- **Refresh data now** — runs one ingestion pass for the selected symbol,
  right from the browser (same thing as the CLI command in §2).
- **Manage watchlist** — add or remove tickers. The list is capped (50 by
  default) so the app can't accidentally be asked to track an unmanageable
  number of symbols.
- **Export data** — download any underlying data table as a CSV or Parquet
  file (Parquet is a compact, columnar file format popular in data
  engineering — smaller and faster to read than CSV, but not human-readable
  in a text editor). Handy if you want to analyze the raw data in
  Excel/pandas/R yourself.

### Tab: Chain Viewer

Shows the full **option chain** for the selected symbol: every strike and
expiry currently listed, with pricing and computed **Greeks** (sensitivity
measures — defined below).

| Column | Meaning |
|---|---|
| **Expiry** | The date the contract stops existing. After this date it either gets exercised or expires worthless. |
| **Strike** | The fixed price at which the option lets you buy (**call**) or sell (**put**) the underlying stock. |
| **Right** | `C` = call (bet the price goes *up*), `P` = put (bet the price goes *down*). A call gives you the right to *buy* at the strike; a put gives you the right to *sell* at the strike. |
| **Bid / Ask** | Bid = the highest price a buyer is currently offering. Ask = the lowest price a seller will accept. You effectively buy at the ask and sell at the bid — the gap between them (the **spread**) is a hidden cost. |
| **Mid** | `(Bid + Ask) / 2` — a rough "fair value" estimate when there's no recent trade. |
| **Last** | The price of the most recent actual trade. |
| **Volume** | How many contracts traded *today*. High volume = a lot of fresh activity. |
| **OI (Open Interest)** | How many contracts are currently *open* (not yet closed out), across all history — not just today. Volume tells you about today's flow; OI tells you about existing positioning. |
| **IV (Implied Volatility)** | The market's built-in guess at how much the stock will move, expressed as an annualized percentage (e.g. `0.30` = the market is pricing in ~30% swings over a year). Solved backward from the option's price — see the [Glossary](#glossary) for how. |
| **Delta** | How much the option's price moves for every $1 move in the stock. A delta of `0.40` means the option gains about $0.40 when the stock rises $1. |
| **Gamma** | How fast delta itself changes as the stock moves. High gamma = the option's behavior can shift quickly. |
| **Theta** | How much value the option loses per day just from time passing, all else equal. Always working against you if you *own* the option. |
| **Vega** | How much the option's price changes for a 1-percentage-point change in IV. |
| **Rho** | How much the option's price changes for a 1-percentage-point change in interest rates — usually a minor effect for short-dated options. |
| **Adjusted?** | A checkbox that appears (and a warning banner) if this app detected a stock split after this contract's strike was first cached — meaning the strike/Greeks shown might be stale. See [Corporate actions](#corporate-actions-splits--dividends) below. |

**Worked example:** a call with delta `0.40` and the stock at $100 going to
$101 → the option's price should rise about $0.40 (before Greeks
themselves shift). This is why delta is sometimes called a rough
"probability the option finishes in-the-money" — a $0.40 delta is loosely
like a 40% chance, though that's an approximation, not a guarantee.

### Tab: Scanner

Looks for **unusual activity** — contracts trading far more than their
existing open interest would suggest, which often (not always) means
someone just took a *new* position rather than closing an old one.

The exact rule (configurable in `config.toml`, §8):

> **Volume > 3 × Open Interest**, and **Volume ≥ 200**

Both conditions have to be true — a contract with volume 250 and OI 10 has
a huge ratio, but the low absolute size might just be noise, so the
"≥ 200" floor filters that out.

Also shown on this tab:

- **Put/Call ratio** — total put volume ÷ total call volume, for the whole
  chain. Below 0.7 is conventionally read as *bullish* (more call buying),
  above 1.3 as *bearish* (more put buying). At extremes, some traders read
  this the opposite way ("contrarian") — if *everyone* is buying puts, the
  bad news may already be priced in.
- **Net premium** — total dollars spent on calls minus total dollars spent
  on puts today. Positive = more money flowing into calls.
- **Check & send alerts now** — manually triggers the same unusual-activity
  check the automated scheduler runs (see [§4](#4-alerts)).

**Important caveat:** a large call purchase is *not* proof someone thinks
the stock is going up. It could be a hedge against a short stock position,
one leg of a multi-part trade (a *spread*), or a market maker's own
inventory management. Treat this tab as a starting point for further
digging, not a signal to act on directly.

### Tab: Flow Feed

Options **flow** (industry term) means the stream of individual trades —
who bought what, and whether they were the aggressor (paid up to buy) or
not. True tick-by-tick flow requires an expensive real-time data license
this app doesn't have, so instead it *infers* flow by comparing two
consecutive snapshots of the same contract and looking at how much volume
changed between them.

- **Aggressor** — `B` (buy-side) if the trade happened at or above the
  midpoint of the bid/ask spread, `S` (sell-side) if at or below, `?` if it
  can't be determined. This is a well-known approximation from academic
  market-microstructure research (the "Lee-Ready" method) and is roughly
  80% accurate historically — a useful signal, not ground truth.
- **Premium** — dollar size of the inferred trade (price × 100 shares/contract
  × number of contracts).

You need at least two refreshes of a symbol (spaced apart in time) before
anything shows up here — the very first snapshot has nothing to compare
against.

### Tab: GEX / Max Pain

Two related concepts about how **market makers** (firms that stand ready to
buy/sell options and hedge their own risk by trading the underlying stock)
might influence price near expiry.

- **GEX (Gamma Exposure)** — an estimate of how much stock market makers as
  a group need to buy or sell to stay hedged as the price moves 1%.
  - **Positive GEX** → market-maker hedging tends to *dampen* price swings
    (they buy dips and sell rallies to stay hedged) — a "pinned," range-bound
    market.
  - **Negative GEX** → hedging tends to *amplify* swings instead.
  - This number depends on an assumption about which side of each trade
    market makers are on, which the app can't observe directly — treat it
    as a plausible estimate, not a measured fact.
- **Gamma flip** — the stock price where the GEX estimate crosses from
  negative to positive (or vice versa). Sometimes watched as a level where
  market behavior might change character.
- **Call wall / Put wall** — the strike prices with the single largest call
  or put open interest. Sometimes act as informal resistance (call wall)
  or support (put wall), since market makers hedging those large positions
  can create buying/selling pressure at those levels.
- **Max pain** — the strike price where, *if the stock closed there at
  expiry*, the total dollar value of all outstanding options would be
  smallest (i.e., option buyers as a group would lose the most, hence
  "max pain" for option holders). There's a folk theory that prices drift
  toward this level into expiration — real, but weak and not something to
  bet the farm on.

### Tab: Sector Heatmap

Aggregates the **net premium** (defined above, under Scanner) across your
whole watchlist, grouped by **sector** — the broad industry category a
company belongs to (Technology, Energy, Healthcare, etc.), looked up
automatically the first time a symbol is ingested. ETFs (funds that track a
basket of stocks, like SPY) don't have a single sector, so they show as
"Unknown" — that's expected, not an error.

Use this to get a rough sense of where options money is flowing across
your whole list at a glance, rather than symbol-by-symbol.

### Tab: Backtest

A **backtest** replays a trading strategy against historical price data to
see how it *would have* performed — a way to test an idea before risking
real money on it. This tab runs a simple **SMA crossover** strategy:

> Buy when the fast moving average crosses above the slow one; sell when it
> crosses back below. A **moving average** is just the average price over
> the last N days, recalculated each day — it smooths out day-to-day noise
> to reveal the underlying trend.

You control:

- **Fast MA / Slow MA** — the window sizes (in days) for the two moving
  averages, e.g. 10 and 30.
- **History** — how much past price data to test against.
- **Fees / Slippage** — trading costs, expressed as a fraction (0.001 =
  0.1%) applied every time the strategy buys or sells, so results aren't
  unrealistically optimistic.
- **Trials tried** — an honesty check, explained below.

Results shown:

| Metric | What it means |
|---|---|
| **CAGR** | Compound Annual Growth Rate — the strategy's average yearly return, accounting for compounding. |
| **Sharpe ratio** | Return per unit of risk taken: `(return − risk-free rate) ÷ volatility`. Above 1 is generally considered good, above 2 excellent, below 0 bad — you'd have been better off in a risk-free savings account. |
| **Sortino ratio** | Like Sharpe, but only penalizes *downside* volatility (dropping in value), not upside swings — arguably a fairer measure since nobody minds volatility that makes them money. |
| **Calmar ratio** | CAGR divided by the worst drawdown (below) — return per unit of "worst pain endured." |
| **Max drawdown** | The largest peak-to-trough loss the strategy experienced at any point in the test. A -25% max drawdown means at some point you were down 25% from your best-ever point before recovering. |
| **Profit factor** | Total dollars won ÷ total dollars lost. Above 1.5 is generally considered healthy. |
| **Win rate** | % of trades that were profitable. **On its own this is close to meaningless** — a strategy that wins small 90% of the time but loses big the other 10% can still lose money overall. Always look at it together with profit factor. |
| **Trades** | How many buy/sell round-trips happened during the test. Very few trades means the other statistics rest on a small, less trustworthy sample. |

**Deflated Sharpe Ratio (DSR)** — this is the app trying to keep you
honest. If you try 20 different strategy variants and pick the best-looking
Sharpe ratio, some of that apparent skill is just luck from trying so many
things (this is called **multiple-testing bias** or **overfitting**). The
**Trials tried** field tells the app how many variants you've tested, and
the DSR reports the probability your *true* edge is real after accounting
for that — below 95% is flagged as "likely overfit." Be honest about the
trials number; entering `1` when you actually tried ten combinations first
defeats the whole point of this check.

### Tab: Journal

A **paper-trading journal** — a record-keeping tool for practicing trade
decisions without real money changing hands. There's no broker connection
here; you manually log what you *would have* done.

- **Open a paper position** — record a symbol, quantity, entry price, and
  (importantly) *why* you're entering. Leave "Contract ID" blank to log a
  plain stock/share position instead of an option; fill it in (format:
  `SYMBOL_YYYYMMDD_RIGHT_STRIKE`, e.g. `AAPL_20260116_C_150` — copyable
  from the Chain Viewer tab) to log an options trade, which uses a 100×
  multiplier (one contract = 100 shares) when calculating profit/loss.
- **Close a position** — record the exit price and why you exited. P&L
  (profit and loss) is calculated automatically.
- Summary stats at the top (win rate, profit factor, total P&L) use the
  same formulas as the Backtest tab, applied to your own logged trades.

Writing down *why* you entered and exited is the actual point of a
journal — it's how you later tell whether a strategy has a real edge or
you were just reading randomness as a pattern.

## 4. Alerts

The scanner's unusual-activity check (§3, Scanner tab) can push a
notification instead of requiring you to check the dashboard. Two channels:

- **Desktop** — a native OS notification popup. Works out of the box, no
  setup beyond enabling it.
- **Telegram** — a message sent to a Telegram bot you control. Needs a bot
  token and chat ID; see `.env.example` for the exact variable names and
  [Telegram's own docs](https://core.telegram.org/bots#how-do-i-create-a-bot)
  for creating a bot (search "@BotFather" inside Telegram).

To turn alerts on, edit `config/config.toml`:

```toml
[alerts]
enabled = true
channels = ["desktop"]   # or ["telegram"], or both
dedup_hours = 24.0
```

`dedup_hours` prevents the same contract from re-alerting you every 15
minutes just because it's still unusual — once flagged, it stays quiet for
that many hours.

## 5. Keeping data fresh automatically (the scheduler)

Instead of manually clicking "Refresh data now," you can run a background
process that re-fetches your whole watchlist on a schedule:

```bash
uv run python -m quantify.ingest.scheduler
```

By default this runs every 15 minutes during US market hours (9:30 AM–4:00
PM Eastern, weekdays), plus a once-daily archive step after close that
saves the day's data to a compact Parquet file for long-term storage. Leave
this running in a terminal (or as a background service) and the dashboard
will always show reasonably fresh data without you doing anything.

## 6. Using the API instead of the dashboard

If you want to pull data into your own script, spreadsheet, or another
tool instead of using the browser dashboard, a small web API is available:

```bash
uv run uvicorn quantify.api.main:app --reload
```

Then visit `http://localhost:8000/docs` for an interactive list of every
endpoint (auto-generated — try things directly in the browser). Endpoints
mirror the dashboard tabs: `/chain/{symbol}`, `/scan`, `/flow`, `/gex/{symbol}`,
`/maxpain/{symbol}`, and `/export/{table}`.

## 7. Running with Docker

If you'd rather not install Python/uv locally, [Docker](https://www.docker.com/)
(a tool for running an app in an isolated, pre-configured environment) works
too:

```bash
cp .env.example .env        # only needed if you're using alerts/Tradier/Alpaca
docker compose up --build
```

Then open `http://localhost:8501` — same dashboard, running in a
container. See the comment at the top of `docker-compose.yml` for an
important note about not running multiple pieces (dashboard, API,
scheduler) against the same data folder at once.

## 8. Configuration reference

Everything lives in `config/config.toml`. Edit it in any text editor; the
dashboard picks up changes automatically the next time you interact with
it (no restart needed there — the API and scheduler do need a restart).

| Section | Field | Meaning |
|---|---|---|
| `[provider]` | `name` | Which data source to use: `yfinance` (default, free, no key), `tradier`, or `alpaca` (both need API credentials in `.env`). |
| `[watchlist]` | `symbols` | The tickers you're tracking. Easier to manage from the dashboard sidebar than by hand. |
| | `max_symbols` | Safety cap on watchlist size (default 50). |
| `[schedule]` | `refresh_minutes` | How often the scheduler re-fetches data. |
| | `market_hours_only` | If true, the scheduler skips refreshes outside 9:30–4:00 ET weekdays. |
| `[scanner]` | `vol_oi_multiple` | The "unusual activity" volume-to-open-interest ratio threshold (default 3.0×). |
| | `min_volume` | The minimum volume floor for the same rule (default 200). |
| | `pc_ratio_bullish_below` / `pc_ratio_bearish_above` | Put/call ratio thresholds for the bullish/bearish sentiment label. |
| `[greeks]` | `risk_free_rate` | The interest rate assumption used in option pricing math (default 4%) — see **risk-free rate** in the Glossary. |
| `[alerts]` | `enabled`, `channels`, `dedup_hours` | See [§4](#4-alerts). |
| `[storage]` | `db_path`, `parquet_dir` | Where the local database and archive files live. Rarely needs changing. |

## Glossary

Quick-reference definitions for every term used above, alphabetically.

- **Aggressor side** — whether a trade was initiated by the buyer or
  seller (i.e., who "crossed the spread" to make it happen). See Flow Feed
  above.
- **American-style option** — a contract that can be exercised (used) any
  time up to expiry. Almost all single-stock/ETF options are this style
  (as opposed to **European-style**, which can only be exercised exactly at
  expiry — used mainly by index options like SPX).
- **At-the-money (ATM)** — a strike price very close to the current stock
  price. See also in-the-money, out-of-the-money.
- **Backtest** — testing a strategy against historical data to estimate how
  it would have performed. See the Backtest tab section above.
- **Bid / Ask / Spread** — see the Chain Viewer table above.
- **Call option** — the right (not obligation) to *buy* 100 shares at a
  fixed price (the strike) before/at expiry. You'd buy a call if you think
  the price is going up.
- **CAGR** — Compound Annual Growth Rate. See Backtest tab.
- **Corporate actions (splits & dividends)** — events a company can take
  that change its stock's structure. A **stock split** (e.g. "4-for-1")
  multiplies your share count and divides the price proportionally, so
  option strikes on record before the split may no longer line up with
  standard contract terms. A **dividend** is a cash payment to
  shareholders, which affects option pricing (a small drag on call value,
  slight boost to put value) — this app records dividends but doesn't
  currently adjust prices for them, a known simplification.
- **Delta / Gamma / Theta / Vega / Rho ("the Greeks")** — see the Chain
  Viewer table above. Collectively, these describe how an option's price
  reacts to different things changing (stock price, time, volatility,
  interest rates).
- **Deflated Sharpe Ratio (DSR)** — see Backtest tab.
- **Delayed data** — market data that's a set number of minutes old (here,
  ~15 minutes) rather than truly live, because real-time data requires an
  expensive commercial license.
- **Expiry / DTE** — the date an option contract stops existing (expiry);
  **DTE** = "days to expiration," how many days remain until then. Shorter
  DTE options are cheaper but decay in value (see theta) much faster.
- **Flow** — the stream of individual option trades. See Flow Feed above.
- **Gamma exposure (GEX)** — see GEX / Max Pain tab above.
- **Implied volatility (IV)** — see Chain Viewer table above. "Implied"
  because it's backed out from the option's market price, rather than
  measured directly — the app solves for it iteratively (a numerical
  technique called Newton-Raphson, with a slower-but-always-works fallback
  called bisection when the fast method struggles, which happens for deep
  in/out-of-the-money contracts).
- **In-the-money (ITM) / Out-of-the-money (OTM)** — whether an option would
  currently be worth exercising. A call is ITM if the stock price is above
  the strike (OTM if below); a put is the reverse.
- **Journal** — see Journal tab above.
- **Market maker** — a firm that continuously quotes both a bid and ask
  price for a security, profiting from the spread while managing
  (hedging) the risk that creates.
- **Max drawdown** — see Backtest tab.
- **Max pain** — see GEX / Max Pain tab above.
- **Moving average** — the average price over a trailing window of days,
  recalculated daily. Smooths short-term noise to show trend direction.
- **Net premium** — see Scanner tab above.
- **Open interest (OI)** — see Chain Viewer table above.
- **Overfitting** — building a strategy (or a scanner rule) so specifically
  tuned to past data that it captures noise rather than a real, repeatable
  pattern, and so performs worse than expected going forward. The Deflated
  Sharpe Ratio (Backtest tab) is this app's built-in check against it.
- **Paper trading** — practicing trade decisions by recording them without
  real money. See Journal tab above.
- **Premium** — the price of an option (what you pay to buy it, or receive
  to sell it). One contract = 100 shares, so a $1.20 premium costs $120
  total, not $1.20.
- **Profit factor** — see Backtest tab.
- **Put option** — the right (not obligation) to *sell* 100 shares at a
  fixed price (the strike) before/at expiry. You'd buy a put if you think
  the price is going down.
- **Put/Call ratio (P/C ratio)** — see Scanner tab above.
- **Risk-free rate** — the theoretical return on a completely safe
  investment (in practice, usually approximated by short-term US Treasury
  yields). Used as a baseline in option pricing and in the Sharpe ratio
  calculation ("was this strategy's return actually better than doing
  nothing risky at all?").
- **Sector** — the broad industry a company belongs to. See Sector Heatmap
  tab above.
- **Sharpe / Sortino / Calmar ratio** — see Backtest tab.
- **Sweep** — an order split across multiple exchanges to fill quickly,
  often read as a sign of urgency from the trader placing it. A "golden
  sweep" is marketing terminology (used by some data vendors) for an
  especially large one.
- **Strike price** — see Chain Viewer table above.
- **Unusual activity** — see Scanner tab above.
- **Volume** — see Chain Viewer table above.
- **Volume/OI ratio (Vol/OI)** — today's volume divided by existing open
  interest. Above 1 suggests new positioning rather than existing
  positions being closed out; this app's unusual-activity rule uses a 3×
  threshold by default.
- **Watchlist** — the list of tickers you're actively tracking. See §8.

## Limitations & honest expectations

Worth reading once, seriously:

- **The data is delayed and noisy.** Free options data lags ~15 minutes
  behind reality, and a lot of "unusual" activity turns out to be hedging,
  spreads, or dealer inventory management — not a directional bet. This
  app surfaces *candidates* for further research, not conclusions.
- **This will not print money on its own.** Options volumes have grown a
  lot in recent years, which also means more noise, not necessarily more
  signal. Most of what a free, delayed data feed shows you has already had
  time to be priced in by the time you see it.
- **Backtests are not guarantees.** Past performance, even accounting for
  fees and slippage the way this app's backtester does, says nothing
  certain about future performance — market conditions change. The
  Deflated Sharpe Ratio helps you avoid fooling *yourself*, but it can't
  make a genuinely weak strategy good.
- **This is not tax, legal, or investment advice**, and nothing in this
  app or guide should be read as a recommendation to buy or sell anything.
  If you're trading with real money, that decision — and its consequences
  — are entirely yours.

If you want to go deeper on any of this, the original design manual
(`Quantify.pdf`) has a full section (Appendix B) of book/course
recommendations for building real background in this area.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Chain Viewer / Scanner tab says "No data yet" | You haven't ingested this symbol | Click "Refresh data now" in the sidebar, or run the CLI ingestion command (§2) |
| Flow Feed says it needs two snapshots | Only one refresh has happened so far | Refresh again later — needs two points in time to compare |
| Empty option chain from yfinance | Yahoo occasionally changes its site structure and breaks the free data path | Try again later, or switch `[provider].name` to `tradier`/`alpaca` if you have credentials |
| Alerts not arriving | Telegram token/chat ID missing, or `enabled = false` | Check `.env` and `config/config.toml [alerts]` |
| Greeks/IV show blank for a row | The contract has no valid bid/ask (illiquid), or is expiring today (0DTE) | Expected — no meaningful price means no meaningful IV to solve for |
| "Adjusted?" warning on Chain Viewer | A stock split was detected since this contract was first cached | Expected safety flag — treat that row's Greeks/IV with extra caution |
