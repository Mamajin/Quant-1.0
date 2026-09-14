"""FastAPI endpoint tests, including /export (FR-014). Uses a scratch
config pointed at a temp DB/Parquet dir so the real data/ directory and
config/config.toml are never touched."""
import datetime as dt

import polars as pl
import pytest
import tomlkit
from fastapi.testclient import TestClient

from quantify.config import DEFAULT_CONFIG_PATH
from quantify.storage import repo


@pytest.fixture()
def scratch_env(tmp_path, monkeypatch):
    doc = tomlkit.parse(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    # Absolute paths here: StorageConfig.resolved_*() does REPO_ROOT / self.path,
    # and pathlib discards the left side when the right side is already absolute.
    doc["storage"]["db_path"] = str(tmp_path / "test.duckdb")
    doc["storage"]["parquet_dir"] = str(tmp_path / "parquet")
    config_path = tmp_path / "config.toml"
    config_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    monkeypatch.setenv("QUANTIFY_CONFIG", str(config_path))
    return config_path


@pytest.fixture()
def client(scratch_env):
    from quantify.api.main import app
    with TestClient(app) as c:
        yield c


def seed_chain(con, symbol="AAPL"):
    repo.upsert_symbol(con, symbol)
    expiry = dt.date.today() + dt.timedelta(days=30)
    contract_id = repo.make_contract_id(symbol, expiry, "C", 150.0)
    repo.upsert_contracts(con, [{
        "contract_id": contract_id, "underlying": symbol, "expiry": expiry, "strike": 150.0, "right": "C",
    }])
    snap = pl.DataFrame([{
        "contract_id": contract_id, "ts": dt.datetime.now(), "bid": 1.0, "ask": 1.1, "last": 1.05,
        "mid": 1.05, "volume": 1000, "open_interest": 100, "iv": 0.3, "delta": 0.4, "gamma": 0.02,
        "theta": -0.01, "vega": 0.1, "rho": 0.01,
    }])
    repo.insert_chain_snapshots(con, snap)
    repo.insert_underlying_quote(con, symbol, dt.datetime.now(), 150.0)


def test_chain_endpoint_404_when_empty(client):
    resp = client.get("/chain/AAPL")
    assert resp.status_code == 404


def test_chain_endpoint_returns_rows(client):
    from quantify.api.main import app
    seed_chain(app.state.con)
    resp = client.get("/chain/AAPL")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["strike"] == 150.0


def test_scan_endpoint(client):
    from quantify.api.main import app
    seed_chain(app.state.con)
    resp = client.get("/scan", params={"symbol": "AAPL"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert "unusual_count" in body


def test_gex_and_maxpain_endpoints(client):
    from quantify.api.main import app
    seed_chain(app.state.con)
    resp = client.get("/gex/AAPL")
    assert resp.status_code == 200
    assert resp.json()["spot"] == 150.0

    resp2 = client.get("/maxpain/AAPL")
    assert resp2.status_code == 200
    assert resp2.json()["symbol"] == "AAPL"


def test_export_endpoint_csv(client):
    from quantify.api.main import app
    seed_chain(app.state.con)
    resp = client.get("/export/symbols", params={"fmt": "csv"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert b"AAPL" in resp.content


def test_export_endpoint_parquet(client):
    from quantify.api.main import app
    seed_chain(app.state.con)
    resp = client.get("/export/symbols", params={"fmt": "parquet"})
    assert resp.status_code == 200
    df = pl.read_parquet(resp.content)
    assert df["symbol"][0] == "AAPL"


def test_export_endpoint_rejects_unknown_table(client):
    resp = client.get("/export/not_a_real_table")
    assert resp.status_code == 404


def test_export_endpoint_rejects_bad_format(client):
    resp = client.get("/export/symbols", params={"fmt": "xlsx"})
    assert resp.status_code == 422
