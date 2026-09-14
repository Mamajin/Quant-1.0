"""Paper-trading journal tests (manual FR-010)."""
import datetime as dt

import duckdb
import pytest

from quantify.journal.manager import close_position, journal_stats, open_position
from quantify.storage.db import SCHEMA_DDL


@pytest.fixture()
def con():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_DDL)
    yield con
    con.close()


def test_open_and_close_option_position_uses_100_multiplier(con):
    pos_id = open_position(con, "AAPL", qty=2, entry_price=1.00,
                            contract_id="AAPL_20260116_C_150", reason_entry="unusual call sweep")
    pnl = close_position(con, pos_id, exit_price=1.50, reason_exit="target hit")
    assert pnl == pytest.approx((1.50 - 1.00) * 2 * 100)


def test_open_and_close_share_position_uses_1x_multiplier(con):
    pos_id = open_position(con, "AAPL", qty=100, entry_price=150.0, contract_id=None)
    pnl = close_position(con, pos_id, exit_price=155.0)
    assert pnl == pytest.approx((155.0 - 150.0) * 100 * 1)


def test_cannot_close_unknown_position(con):
    with pytest.raises(ValueError):
        close_position(con, 999, exit_price=1.0)


def test_cannot_close_already_closed_position(con):
    pos_id = open_position(con, "AAPL", qty=1, entry_price=1.0, contract_id="X")
    close_position(con, pos_id, exit_price=2.0)
    with pytest.raises(ValueError):
        close_position(con, pos_id, exit_price=3.0)


def test_open_positions_excludes_closed(con):
    from quantify.storage import repo

    open_id = open_position(con, "AAPL", qty=1, entry_price=1.0, contract_id="OPEN")
    closed_id = open_position(con, "AAPL", qty=1, entry_price=1.0, contract_id="CLOSED")
    close_position(con, closed_id, exit_price=1.5)

    open_df = repo.open_positions(con)
    assert open_df.height == 1
    assert open_df["id"][0] == open_id


def test_journal_stats_empty(con):
    stats = journal_stats(con)
    assert stats["n_closed"] == 0
    assert stats["win_rate"] == 0.0


def test_journal_stats_computes_win_rate_and_expectancy(con):
    # One winner (+100), one loser (-50)
    win_id = open_position(con, "AAPL", qty=1, entry_price=1.0, contract_id="A")
    close_position(con, win_id, exit_price=2.0)  # +100
    loss_id = open_position(con, "AAPL", qty=1, entry_price=1.0, contract_id="B")
    close_position(con, loss_id, exit_price=0.5)  # -50

    stats = journal_stats(con)
    assert stats["n_closed"] == 2
    assert stats["win_rate"] == pytest.approx(0.5)
    assert stats["total_pnl"] == pytest.approx(50.0)
    assert stats["profit_factor"] == pytest.approx(100.0 / 50.0)
    assert stats["expectancy"] == pytest.approx(0.5 * 100.0 - 0.5 * 50.0)
