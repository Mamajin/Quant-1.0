"""Aggressor classification tests (manual sec 1.4: quote rule + tick-rule fallback)."""
import polars as pl

from quantify.scanner.flow import classify_aggressor, infer_flow_from_snapshots


def test_classify_aggressor_quote_rule():
    assert classify_aggressor(price=10.10, bid=10.00, ask=10.10) == "B"  # at ask
    assert classify_aggressor(price=10.00, bid=10.00, ask=10.10) == "S"  # at bid
    assert classify_aggressor(price=10.05, bid=10.00, ask=10.10) == "?"  # exact midpoint, no prev_price


def test_classify_aggressor_tick_rule_fallback_on_midpoint():
    assert classify_aggressor(price=10.05, bid=10.00, ask=10.10, prev_price=10.00) == "B"  # uptick
    assert classify_aggressor(price=10.05, bid=10.00, ask=10.10, prev_price=10.10) == "S"  # downtick
    assert classify_aggressor(price=10.05, bid=10.00, ask=10.10, prev_price=10.05) == "?"  # no change


def test_infer_flow_from_snapshots_computes_positive_volume_delta():
    prev = pl.DataFrame([
        {"contract_id": "AAPL_C_100", "volume": 100, "last": 1.00, "bid": 0.95, "ask": 1.05, "mid": 1.00, "open_interest": 50},
    ])
    curr = pl.DataFrame([
        {"contract_id": "AAPL_C_100", "volume": 500, "last": 1.10, "bid": 1.00, "ask": 1.10, "mid": 1.05, "open_interest": 50},
    ])
    flow = infer_flow_from_snapshots(prev, curr)
    assert flow.height == 1
    row = flow.to_dicts()[0]
    assert row["volume_delta"] == 400
    assert row["aggressor"] == "B"  # 1.10 == ask -> buy
    assert row["premium"] == 400 * 1.05 * 100


def test_infer_flow_ignores_unchanged_or_decreasing_volume():
    prev = pl.DataFrame([{"contract_id": "X", "volume": 100, "last": 1.0, "bid": 0.9, "ask": 1.1, "mid": 1.0, "open_interest": 10}])
    curr = pl.DataFrame([{"contract_id": "X", "volume": 100, "last": 1.0, "bid": 0.9, "ask": 1.1, "mid": 1.0, "open_interest": 10}])
    assert infer_flow_from_snapshots(prev, curr).is_empty()
