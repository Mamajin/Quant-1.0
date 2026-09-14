"""Streamlit dashboard: chain viewer + scanner + flow feed + GEX/max-pain
(manual sec 2.9 'Streamlit (MVP)', FR-011/012/013, NFR-004 'every displayed
number has an info tooltip').

Run: uv run streamlit run src/quantify/ui/app.py
"""
from __future__ import annotations

import datetime as dt

import plotly.graph_objects as go
import streamlit as st

from quantify.config import load_config
from quantify.ingest.pipeline import run_ingestion
from quantify.scanner.gex import dollar_gex_by_strike
from quantify.service import get_chain, get_flow, get_gex_summary, get_scan
from quantify.storage.db import connect

st.set_page_config(page_title="Quantify", layout="wide")

config = load_config()
con = connect(config.storage)

st.sidebar.title("Quantify")
st.sidebar.caption("Local options-flow & quant research tool -- educational, not investment advice.")

watchlist = config.watchlist.validated_symbols()
symbol = st.sidebar.selectbox("Symbol", watchlist, help="From config/config.toml [watchlist].symbols (cap 50, FR-002)")

if st.sidebar.button("Refresh data now", help="Runs one ingestion pass for this symbol via the configured provider (yfinance by default)"):
    with st.spinner(f"Fetching {symbol} chain..."):
        rows = run_ingestion(con, config, symbols=[symbol])
    st.sidebar.success(f"Ingested {rows.get(symbol, 0)} rows for {symbol}")

st.sidebar.info(
    "Free data is delayed ~15 minutes and flow signals are noisy -- this is "
    "an edge-hunting research tool, not a money printer (manual sec 1.8/Appendix D)."
)

tab_chain, tab_scanner, tab_flow, tab_gex = st.tabs(["Chain Viewer", "Scanner", "Flow Feed", "GEX / Max Pain"])

with tab_chain:
    st.subheader(f"{symbol} option chain (latest snapshot)")
    chain_df = get_chain(con, symbol)
    if chain_df.is_empty():
        st.warning("No data yet -- click 'Refresh data now' in the sidebar.")
    else:
        expiries = sorted(chain_df["expiry"].unique().to_list())
        expiry_filter = st.selectbox("Expiry", ["All"] + [str(e) for e in expiries])
        display_df = chain_df if expiry_filter == "All" else chain_df.filter(
            chain_df["expiry"].cast(str) == expiry_filter
        )
        st.dataframe(
            display_df.select([
                "expiry", "strike", "right", "bid", "ask", "mid", "last",
                "volume", "open_interest", "iv", "delta", "gamma", "theta", "vega", "rho",
            ]).to_pandas(),
            width='stretch',
            column_config={
                "iv": st.column_config.NumberColumn("IV", help="Implied volatility (decimal), solved via Newton-Raphson/bisection from mid price (sec 3.6)", format="%.4f"),
                "delta": st.column_config.NumberColumn(help="Price change per $1 move in underlying (sec 3.3)"),
                "gamma": st.column_config.NumberColumn(help="How fast delta changes (sec 3.3)"),
                "theta": st.column_config.NumberColumn(help="Daily time decay, $/contract (sec 3.3)"),
                "vega": st.column_config.NumberColumn(help="Sensitivity per 1 vol point (sec 3.3)"),
                "rho": st.column_config.NumberColumn(help="Sensitivity per 1% rate change (sec 3.3)"),
                "open_interest": st.column_config.NumberColumn("OI", help="Contracts currently open (sec 1.3)"),
            },
        )

with tab_scanner:
    st.subheader(f"{symbol} scanner")
    scan = get_scan(con, config, symbol)
    col1, col2, col3 = st.columns(3)
    col1.metric("Unusual activity rows", scan["unusual_count"],
                help=f"Vol > {config.scanner.vol_oi_multiple}x OI and Vol >= {config.scanner.min_volume} (sec 1.5/3.8)")
    if scan["put_call_ratio"] is not None:
        col2.metric("Put/Call ratio (volume)", f"{scan['put_call_ratio']:.2f}",
                    help="<0.7 bullish, >1.3 bearish by common convention (sec 3.5) -- contrarian at extremes")
        col3.metric("Sentiment", scan["pc_sentiment"] or "n/a")
    if scan["net_premium"] is not None:
        st.metric("Net premium (calls - puts, $)", f"${scan['net_premium']:,.0f}",
                   help="Positive = bullish dollar tilt (sec 3.5)")
    if scan["unusual_activity"]:
        st.dataframe(scan["unusual_activity"], width='stretch')
    else:
        st.caption("No unusual-activity rows for this symbol's latest snapshot.")

with tab_flow:
    st.subheader(f"{symbol} inferred flow (snapshot diff)")
    st.caption(
        "Free/delayed data has no true tick-by-tick feed, so flow here is "
        "inferred from volume deltas between consecutive snapshots, with "
        "aggressor side classified via the quote/tick rule (~80% accurate "
        "proxy, sec 1.4/2.10)."
    )
    min_premium = st.number_input("Min premium ($)", min_value=0.0, value=0.0, step=1000.0)
    flow_df = get_flow(con, symbol, min_premium)
    if flow_df.is_empty():
        st.info("Need at least two ingestion snapshots for this symbol to infer flow -- refresh again later.")
    else:
        st.dataframe(flow_df.to_pandas(), width='stretch')

with tab_gex:
    st.subheader(f"{symbol} GEX & Max Pain")
    gex = get_gex_summary(con, config, symbol)
    if gex["spot"] is None:
        st.warning("No data yet -- click 'Refresh data now' in the sidebar.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spot", f"${gex['spot']:.2f}")
        c2.metric("Max pain", f"${gex['max_pain']:.2f}" if gex["max_pain"] else "n/a",
                   help="Strike minimizing total remaining option value at expiry (sec 3.5/3.6)")
        c3.metric("Call wall", f"${gex['call_wall']:.2f}" if gex["call_wall"] else "n/a",
                   help="Heaviest call OI strike -- resistance (sec 2.4)")
        c4.metric("Put wall", f"${gex['put_wall']:.2f}" if gex["put_wall"] else "n/a",
                   help="Heaviest put OI strike -- support (sec 2.4)")
        st.caption(
            "GEX sign convention: dealer_gamma = call_gamma*call_OI - put_gamma*put_OI. "
            "This is a modeling assumption about dealer inventory, not fact -- "
            "positive GEX suggests dampened moves, negative suggests amplified moves (sec 3.5 caveat)."
        )

        chain_df = get_chain(con, symbol)
        by_strike = dollar_gex_by_strike(chain_df, gex["spot"]).to_pandas()
        fig = go.Figure()
        fig.add_bar(x=by_strike["strike"], y=by_strike["dollar_gex"], name="Dollar GEX per 1% move")
        fig.add_vline(x=gex["spot"], line_dash="dash", annotation_text="spot")
        if gex["gamma_flip"]:
            fig.add_vline(x=gex["gamma_flip"], line_dash="dot", line_color="orange", annotation_text="gamma flip")
        fig.update_layout(xaxis_title="Strike", yaxis_title="Dollar GEX / 1% move", height=450)
        st.plotly_chart(fig, width='stretch')

st.sidebar.caption(f"Last render: {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
