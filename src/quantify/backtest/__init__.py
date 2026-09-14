"""Backtesting engine (manual FR-009, sec 2.14 Phase 3, sec 3.7 stats/sec 1.6 validation).

Implementation note / deviation from the manual's sec 2.9 stack table: the
manual recommends `vectorbt` for fast parameter sweeps. As of this build,
PyPI's `vectorbt==1.0.0` is broken on import with current Plotly (it
hardcodes a `scattermapbox` theme property Plotly 7.x removed) -- confirmed
by actually installing and importing it, not assumed. That's the exact
"library rot" risk sec 4.4 warns about, just hitting vectorbt instead of
Backtrader. Rather than pin an old, incompatible Plotly (which would also
affect the Streamlit GEX chart) or depend on an unmaintained package, this
module implements an equivalent vectorized pandas/numpy backtest directly --
same inputs/outputs (signals in, equity curve + Sharpe/CAGR/max-DD/profit-
factor out), no fragile dependency.
"""
