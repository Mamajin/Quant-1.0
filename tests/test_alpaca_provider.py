"""Alpaca provider tests -- mocked HTTP only (no real Alpaca account
available in this environment; see the module docstring's caveat)."""
import datetime as dt

import pytest

from quantify.ingest.alpaca_provider import AlpacaProvider, _parse_occ_symbol


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def make_provider(monkeypatch, responses: dict):
    def fake_get(url, headers, params, timeout):
        for path, payload in responses.items():
            if url.endswith(path):
                return FakeResponse(payload)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("quantify.ingest.alpaca_provider.requests.get", fake_get)
    return AlpacaProvider(api_key="KEY", secret_key="SECRET")


def test_requires_credentials(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        AlpacaProvider(api_key=None, secret_key=None)


def test_parse_occ_symbol():
    parsed = _parse_occ_symbol("AAPL260116C00150000")
    assert parsed == {"expiry": dt.date(2026, 1, 16), "right": "C", "strike": 150.0}


def test_parse_occ_symbol_put_with_fractional_strike():
    parsed = _parse_occ_symbol("SPY260320P00512500")
    assert parsed["right"] == "P"
    assert parsed["strike"] == 512.5


def test_parse_occ_symbol_invalid_returns_none():
    assert _parse_occ_symbol("not-a-real-symbol") is None


def test_fetch_spot(monkeypatch):
    provider = make_provider(monkeypatch, {
        "/trades/latest": {"trade": {"p": 234.56}},
    })
    assert provider.fetch_spot("AAPL") == 234.56


def test_fetch_chain_parses_snapshots(monkeypatch):
    provider = make_provider(monkeypatch, {
        "/v1beta1/options/snapshots/AAPL": {
            "snapshots": {
                "AAPL260116C00150000": {
                    "latestQuote": {"bp": 5.0, "ap": 5.2},
                    "latestTrade": {"p": 5.1, "s": 10},
                },
                "AAPL260116P00150000": {
                    "latestQuote": {"bp": 1.0, "ap": 1.2},
                    "latestTrade": {"p": 1.1, "s": 5},
                },
            },
            "next_page_token": None,
        },
    })
    df = provider.fetch_chain("AAPL", max_expiries=1)
    assert df.height == 2
    call_row = df.filter(df["right"] == "C").to_dicts()[0]
    assert call_row["strike"] == 150.0
    assert call_row["bid"] == 5.0
    assert call_row["last"] == 5.1


def test_fetch_chain_no_snapshots_returns_empty_df(monkeypatch):
    provider = make_provider(monkeypatch, {
        "/v1beta1/options/snapshots/AAPL": {"snapshots": {}, "next_page_token": None},
    })
    df = provider.fetch_chain("AAPL")
    assert df.is_empty()


def test_fetch_history_parses_bars(monkeypatch):
    provider = make_provider(monkeypatch, {
        "/bars": {"bars": [
            {"t": "2026-01-02T00:00:00Z", "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5, "v": 1000},
            {"t": "2026-01-03T00:00:00Z", "o": 100.5, "h": 102.0, "l": 100.0, "c": 101.5, "v": 1200},
        ]},
    })
    hist = provider.fetch_history("AAPL", period="1y")
    assert len(hist) == 2
    assert list(hist.columns) == ["open", "high", "low", "close", "volume"]
    assert hist["close"].iloc[-1] == 101.5


def test_fetch_corporate_actions_returns_empty(monkeypatch):
    provider = make_provider(monkeypatch, {})
    df = provider.fetch_corporate_actions("AAPL")
    assert df.empty
