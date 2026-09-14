"""Corporate-action detection tests (manual FR-018, sec 4.2)."""
import datetime as dt

import duckdb
import pandas as pd
import pytest

from quantify.corporate_actions.detector import detect_and_flag
from quantify.storage import repo
from quantify.storage.db import SCHEMA_DDL


class FakeProvider:
    def __init__(self, actions_df: pd.DataFrame):
        self._actions_df = actions_df

    def fetch_corporate_actions(self, symbol: str) -> pd.DataFrame:
        return self._actions_df


@pytest.fixture()
def con():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_DDL)
    yield con
    con.close()


def seed_contracts(con, symbol="AAPL"):
    repo.upsert_symbol(con, symbol)
    before_split = dt.date.today() - dt.timedelta(days=5)  # expired before the split
    after_split = dt.date.today() + dt.timedelta(days=30)  # still listed after the split
    repo.upsert_contracts(con, [
        {"contract_id": "OLD", "underlying": symbol, "expiry": before_split, "strike": 100.0, "right": "C"},
        {"contract_id": "NEW", "underlying": symbol, "expiry": after_split, "strike": 100.0, "right": "C"},
    ])
    return before_split, after_split


def test_detect_and_flag_flags_only_contracts_expiring_after_split(con):
    seed_contracts(con)
    split_date = dt.date.today() - dt.timedelta(days=1)
    actions = pd.DataFrame([{"date": split_date, "action_type": "split", "value": 4.0}])
    provider = FakeProvider(actions)

    detected = detect_and_flag(con, provider, "AAPL")
    assert len(detected) == 1
    assert detected[0]["action_type"] == "split"

    contracts = con.execute("SELECT contract_id, is_adjusted FROM option_contracts ORDER BY contract_id").fetchall()
    flags = dict(contracts)
    assert flags["OLD"] is False
    assert flags["NEW"] is True


def test_detect_and_flag_dividend_does_not_flag_contracts(con):
    seed_contracts(con)
    div_date = dt.date.today() - dt.timedelta(days=1)
    actions = pd.DataFrame([{"date": div_date, "action_type": "dividend", "value": 0.25}])
    provider = FakeProvider(actions)

    detected = detect_and_flag(con, provider, "AAPL")
    assert len(detected) == 1
    assert detected[0]["action_type"] == "dividend"

    flags = dict(con.execute("SELECT contract_id, is_adjusted FROM option_contracts").fetchall())
    assert not any(flags.values())


def test_detect_and_flag_dedupes_already_seen_actions(con):
    seed_contracts(con)
    split_date = dt.date.today() - dt.timedelta(days=1)
    actions = pd.DataFrame([{"date": split_date, "action_type": "split", "value": 4.0}])
    provider = FakeProvider(actions)

    first = detect_and_flag(con, provider, "AAPL")
    second = detect_and_flag(con, provider, "AAPL")
    assert len(first) == 1
    assert second == []


def test_detect_and_flag_ignores_actions_outside_lookback_window(con):
    seed_contracts(con)
    old_split = dt.date.today() - dt.timedelta(days=400)
    actions = pd.DataFrame([{"date": old_split, "action_type": "split", "value": 2.0}])
    provider = FakeProvider(actions)

    detected = detect_and_flag(con, provider, "AAPL", lookback_days=30)
    assert detected == []


def test_detect_and_flag_empty_actions_returns_empty(con):
    seed_contracts(con)
    provider = FakeProvider(pd.DataFrame(columns=["date", "action_type", "value"]))
    assert detect_and_flag(con, provider, "AAPL") == []
