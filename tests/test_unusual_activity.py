"""Scanner rule tests (manual sec 1.5/3.8: Vol > 3xOI and Vol >= 200)."""
import polars as pl
import pytest

from quantify.scanner.rules import classify_pc_sentiment, net_premium, put_call_ratio, unusual_activity


def make_chain(rows):
    return pl.DataFrame(rows)


def test_unusual_activity_flags_high_vol_oi_and_min_volume():
    df = make_chain([
        {"strike": 100.0, "right": "C", "volume": 1000, "open_interest": 100, "mid": 1.0},  # unusual: 10x OI, vol>=200
        {"strike": 105.0, "right": "C", "volume": 50, "open_interest": 5, "mid": 1.0},       # 10x OI but vol<200 -> not unusual
        {"strike": 110.0, "right": "P", "volume": 300, "open_interest": 200, "mid": 1.0},    # 1.5x OI -> not unusual
    ])
    flagged = unusual_activity(df, vol_oi_multiple=3.0, min_volume=200)
    assert flagged.height == 1
    assert flagged["strike"][0] == 100.0


def test_unusual_activity_handles_zero_open_interest():
    df = make_chain([{"strike": 100.0, "right": "C", "volume": 500, "open_interest": 0, "mid": 1.0}])
    flagged = unusual_activity(df, vol_oi_multiple=3.0, min_volume=200)
    assert flagged.height == 1  # new positioning, no prior OI


def test_put_call_ratio_and_sentiment():
    df = make_chain([
        {"strike": 100.0, "right": "C", "volume": 800, "open_interest": 100, "mid": 1.0},
        {"strike": 100.0, "right": "P", "volume": 200, "open_interest": 100, "mid": 1.0},
    ])
    ratio = put_call_ratio(df, by="volume")
    assert ratio == pytest.approx(0.25)
    assert classify_pc_sentiment(ratio) == "bullish"
    assert classify_pc_sentiment(1.5) == "bearish"
    assert classify_pc_sentiment(1.0) == "neutral"


def test_net_premium_positive_when_calls_dominate():
    df = make_chain([
        {"strike": 100.0, "right": "C", "volume": 100, "mid": 2.0},
        {"strike": 100.0, "right": "P", "volume": 50, "mid": 1.0},
    ])
    # call premium = 2.0*100*100 = 20000; put premium = 1.0*100*50 = 5000
    assert net_premium(df) == pytest.approx(15000.0)
