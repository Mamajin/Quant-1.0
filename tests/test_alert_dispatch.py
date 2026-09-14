"""Alerting tests (manual FR-008): dedup, message formatting, channel wiring.
Uses an in-memory DuckDB and a fake notifier -- no real network calls."""
import datetime as dt

import polars as pl
import pytest

import quantify.alerts.dispatch as dispatch_mod
from quantify.alerts.channels import DesktopNotifier, TelegramNotifier, build_notifiers
from quantify.alerts.dispatch import check_and_alert, format_alert_message
from quantify.config import AlertsConfig, QuantifyConfig, ScannerConfig
from quantify.storage import repo
from quantify.storage.db import SCHEMA_DDL

import duckdb


class FakeNotifier:
    name = "fake"

    def __init__(self):
        self.sent = []

    def send(self, message: str) -> bool:
        self.sent.append(message)
        return True


@pytest.fixture()
def con():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_DDL)
    yield con
    con.close()


def seed_unusual_chain(con, symbol="AAPL"):
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
    return contract_id


def make_config(channels=("fake",)) -> QuantifyConfig:
    return QuantifyConfig(
        alerts=AlertsConfig(enabled=True, channels=list(channels), dedup_hours=24.0),
        scanner=ScannerConfig(vol_oi_multiple=3.0, min_volume=200),
    )


def test_format_alert_message_contains_key_fields():
    row = {"strike": 150.0, "right": "C", "expiry": "2026-01-16", "volume": 1000,
           "open_interest": 100, "vol_oi_ratio": 10.0, "mid": 1.05}
    msg = format_alert_message("AAPL", row)
    assert "AAPL" in msg and "150" in msg and "CALL" in msg and "1,000" in msg


def test_check_and_alert_disabled_returns_empty(con, monkeypatch):
    monkeypatch.setattr(dispatch_mod, "build_notifiers", lambda channels: [FakeNotifier()])
    seed_unusual_chain(con)
    config = make_config()
    config.alerts.enabled = False
    assert check_and_alert(con, config, "AAPL") == []


def test_check_and_alert_dispatches_and_dedupes(con, monkeypatch):
    fake = FakeNotifier()
    monkeypatch.setattr(dispatch_mod, "build_notifiers", lambda channels: [fake])
    seed_unusual_chain(con)
    config = make_config()

    dispatched = check_and_alert(con, config, "AAPL")
    assert len(dispatched) == 1
    assert dispatched[0]["channel"] == "fake"
    assert dispatched[0]["ok"] is True
    assert len(fake.sent) == 1

    # Same snapshot, same scan -> should be deduped this time (manual FR-008
    # shouldn't re-alert on every refresh interval for an unchanged contract)
    dispatched_again = check_and_alert(con, config, "AAPL")
    assert dispatched_again == []
    assert len(fake.sent) == 1


def test_check_and_alert_no_channels_configured_returns_empty(con, monkeypatch):
    seed_unusual_chain(con)
    config = make_config(channels=())
    assert check_and_alert(con, config, "AAPL") == []


def test_build_notifiers_skips_telegram_without_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    notifiers = build_notifiers(["telegram"])
    assert notifiers == []


def test_build_notifiers_desktop_and_unknown(monkeypatch):
    notifiers = build_notifiers(["desktop", "not_a_real_channel"])
    assert len(notifiers) == 1
    assert isinstance(notifiers[0], DesktopNotifier)


def test_telegram_notifier_send_success(monkeypatch):
    calls = {}

    class FakeResponse:
        ok = True
        status_code = 200
        text = ""

    def fake_post(url, data, timeout):
        calls["url"] = url
        calls["data"] = data
        return FakeResponse()

    monkeypatch.setattr("quantify.alerts.channels.requests.post", fake_post)
    notifier = TelegramNotifier(bot_token="TOKEN", chat_id="123")
    assert notifier.send("hello") is True
    assert "TOKEN" in calls["url"]
    assert calls["data"]["chat_id"] == "123"


def test_telegram_notifier_send_failure_returns_false(monkeypatch):
    class FakeResponse:
        ok = False
        status_code = 403
        text = "forbidden"

    monkeypatch.setattr("quantify.alerts.channels.requests.post", lambda url, data, timeout: FakeResponse())
    notifier = TelegramNotifier(bot_token="TOKEN", chat_id="123")
    assert notifier.send("hello") is False
