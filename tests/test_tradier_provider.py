"""Tradier provider tests -- mocked HTTP only (no real Tradier account
available in this environment; see the module docstring's caveat)."""
import datetime as dt

import pytest

from quantify.ingest.tradier_provider import TradierProvider


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def make_provider(monkeypatch, responses: dict):
    """responses: {path -> json payload}, matched by path suffix."""
    def fake_get(url, headers, params, timeout):
        for path, payload in responses.items():
            if url.endswith(path):
                return FakeResponse(payload)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("quantify.ingest.tradier_provider.requests.get", fake_get)
    return TradierProvider(token="FAKE_TOKEN", sandbox=True)


def test_requires_token(monkeypatch):
    monkeypatch.delenv("TRADIER_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        TradierProvider(token=None)


def test_fetch_spot(monkeypatch):
    provider = make_provider(monkeypatch, {
        "/markets/quotes": {"quotes": {"quote": {"symbol": "AAPL", "last": 234.56}}},
    })
    assert provider.fetch_spot("AAPL") == 234.56


def test_fetch_chain_parses_calls_and_puts(monkeypatch):
    provider = make_provider(monkeypatch, {
        "/markets/options/expirations": {"expirations": {"date": ["2026-01-16"]}},
        "/markets/options/chains": {"options": {"option": [
            {"strike": 150.0, "option_type": "call", "bid": 5.0, "ask": 5.2, "last": 5.1,
             "volume": 100, "open_interest": 500},
            {"strike": 150.0, "option_type": "put", "bid": 1.0, "ask": 1.2, "last": 1.1,
             "volume": 50, "open_interest": 300},
        ]}},
    })
    df = provider.fetch_chain("AAPL", max_expiries=1)
    assert df.height == 2
    rights = set(df["right"].to_list())
    assert rights == {"C", "P"}
    call_row = df.filter(df["right"] == "C").to_dicts()[0]
    assert call_row["strike"] == 150.0
    assert call_row["expiry"] == dt.date(2026, 1, 16)
    assert call_row["open_interest"] == 500


def test_fetch_chain_empty_expirations_returns_empty_df(monkeypatch):
    provider = make_provider(monkeypatch, {
        "/markets/options/expirations": {"expirations": {}},
    })
    df = provider.fetch_chain("AAPL")
    assert df.is_empty()


def test_fetch_history_parses_daily_bars(monkeypatch):
    provider = make_provider(monkeypatch, {
        "/markets/history": {"history": {"day": [
            {"date": "2026-01-02", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            {"date": "2026-01-03", "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1200},
        ]}},
    })
    hist = provider.fetch_history("AAPL", period="1y")
    assert len(hist) == 2
    assert list(hist.columns) == ["open", "high", "low", "close", "volume"]
    assert hist["close"].iloc[-1] == 101.5


def test_fetch_corporate_actions_returns_empty(monkeypatch):
    provider = make_provider(monkeypatch, {})
    df = provider.fetch_corporate_actions("AAPL")
    assert df.empty
