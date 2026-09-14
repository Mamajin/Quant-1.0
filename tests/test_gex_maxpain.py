"""GEX and max-pain tests (manual sec 3.5/3.6/FR-017)."""
import polars as pl
import pytest

from quantify.scanner.gex import call_put_walls, dollar_gex_by_strike, max_pain, total_gex

ROWS = [
    {"strike": 90.0, "right": "C", "open_interest": 10, "gamma": 0.02},
    {"strike": 100.0, "right": "C", "open_interest": 50, "gamma": 0.02},
    {"strike": 110.0, "right": "C", "open_interest": 5, "gamma": 0.02},
    {"strike": 90.0, "right": "P", "open_interest": 5, "gamma": 0.02},
    {"strike": 100.0, "right": "P", "open_interest": 20, "gamma": 0.02},
    {"strike": 110.0, "right": "P", "open_interest": 80, "gamma": 0.02},
]


def make_chain():
    return pl.DataFrame(ROWS)


def test_max_pain_picks_strike_minimizing_total_payout():
    assert max_pain(make_chain()) == pytest.approx(110.0)


def test_call_put_walls_pick_heaviest_oi_strikes():
    walls = call_put_walls(make_chain())
    assert walls["call_wall"] == pytest.approx(100.0)
    assert walls["put_wall"] == pytest.approx(110.0)


def test_dollar_gex_by_strike():
    by_strike = dollar_gex_by_strike(make_chain(), spot=100.0).sort("strike")
    values = dict(zip(by_strike["strike"].to_list(), by_strike["dollar_gex"].to_list()))
    assert values[90.0] == pytest.approx(1000.0)
    assert values[100.0] == pytest.approx(6000.0)
    assert values[110.0] == pytest.approx(-15000.0)


def test_total_gex_sums_by_strike():
    assert total_gex(make_chain(), spot=100.0) == pytest.approx(-8000.0)


def test_max_pain_empty_df_returns_none():
    empty = pl.DataFrame(schema={"strike": pl.Float64, "right": pl.Utf8, "open_interest": pl.Int64})
    assert max_pain(empty) is None
