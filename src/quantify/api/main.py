"""FastAPI service layer -- thin wrapper over the same modules the Streamlit
UI calls directly (sec 2.11 architecture, sec 2.13 REST sketch).

Run: uv run uvicorn quantify.api.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from ..config import load_config
from ..export import to_bytes
from ..service import get_chain, get_flow, get_gex_summary, get_scan
from ..storage import repo
from ..storage.db import connect


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.config = load_config()
    app.state.con = connect(app.state.config.storage)
    yield
    app.state.con.close()


app = FastAPI(title="Quantify API", version="0.1.0", lifespan=lifespan)


@app.get("/chain/{symbol}")
def read_chain(symbol: str):
    df = get_chain(app.state.con, symbol.upper())
    if df.is_empty():
        raise HTTPException(status_code=404, detail=f"No chain data for {symbol!r} -- run ingestion first")
    return df.to_dicts()


@app.get("/scan")
def read_scan(symbol: str = Query(..., description="Underlying symbol, e.g. AAPL")):
    return get_scan(app.state.con, app.state.config, symbol.upper())


@app.get("/flow")
def read_flow(symbol: str = Query(...), min_premium: float = Query(0.0, ge=0.0)):
    df = get_flow(app.state.con, symbol.upper(), min_premium)
    return df.to_dicts()


@app.get("/gex/{symbol}")
def read_gex(symbol: str):
    return get_gex_summary(app.state.con, app.state.config, symbol.upper())


@app.get("/maxpain/{symbol}")
def read_max_pain(symbol: str):
    summary = get_gex_summary(app.state.con, app.state.config, symbol.upper())
    return {"symbol": summary["symbol"], "max_pain": summary["max_pain"]}


@app.get("/export/{table}")
def export_table(table: str, fmt: str = Query("csv", pattern="^(csv|parquet)$")):
    """FR-014: CSV/Parquet export of any known table."""
    if table not in repo.EXPORTABLE_TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table {table!r}; must be one of {repo.EXPORTABLE_TABLES}")
    df = repo.export_table(app.state.con, table)
    content = to_bytes(df, fmt)
    media_type = "text/csv" if fmt == "csv" else "application/octet-stream"
    return Response(
        content=content, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{table}.{fmt}"'},
    )
