"""Deflated Sharpe Ratio / Minimum Track Record Length tests (manual sec 1.6,
Bailey & Lopez de Prado 2014)."""
import math

from scipy.stats import norm

from quantify.backtest.validation import (
    deflated_sharpe_ratio,
    expected_max_sharpe_under_null,
    minimum_track_record_length,
    probabilistic_sharpe_ratio,
)


def test_psr_matches_simple_zscore_formula_for_normal_returns():
    sharpe_hat, benchmark, n_obs = 1.2, 0.5, 252
    psr = probabilistic_sharpe_ratio(sharpe_hat, benchmark, n_obs, skew=0.0, kurtosis=3.0)
    expected = norm.cdf((sharpe_hat - benchmark) * math.sqrt(n_obs - 1))
    assert psr == expected


def test_psr_increases_with_more_observations():
    low_n = probabilistic_sharpe_ratio(1.0, 0.0, n_obs=30)
    high_n = probabilistic_sharpe_ratio(1.0, 0.0, n_obs=1000)
    assert high_n > low_n


def test_expected_max_sharpe_increases_with_more_trials():
    """More independent strategies tried -> higher Sharpe explainable by luck alone."""
    sr0_few = expected_max_sharpe_under_null(sharpe_variance=0.01, n_trials=5)
    sr0_many = expected_max_sharpe_under_null(sharpe_variance=0.01, n_trials=500)
    assert sr0_many > sr0_few


def test_expected_max_sharpe_zero_for_single_trial():
    assert expected_max_sharpe_under_null(sharpe_variance=0.01, n_trials=1) == 0.0


def test_deflated_sharpe_penalizes_more_trials():
    """The same observed Sharpe should look less trustworthy (lower DSR) the
    more strategy variants were tried before it (manual sec 4.5: 'track
    deflated Sharpe across all trials, not just the winner')."""
    # n_obs/sharpe_hat chosen so neither PSR saturates to exactly 1.0 in
    # float64 -- these formulas use per-observation (not annualized) Sharpe,
    # and the z-score grows with sqrt(n_obs), so large n_obs with a punchy
    # Sharpe pins PSR at the float64 ceiling and hides the trials effect.
    single_trial = deflated_sharpe_ratio(sharpe_hat=0.8, n_obs=60, n_trials=1)
    many_trials = deflated_sharpe_ratio(sharpe_hat=0.8, n_obs=60, n_trials=200)
    assert many_trials["dsr"] < single_trial["dsr"]
    assert many_trials["sr0_noise_floor"] > single_trial["sr0_noise_floor"]


def test_deflated_sharpe_flags_likely_overfit_with_many_trials_low_sharpe():
    result = deflated_sharpe_ratio(sharpe_hat=0.3, n_obs=100, n_trials=1000)
    assert result["likely_overfit"] is True


def test_minimum_track_record_length_none_when_no_edge():
    assert minimum_track_record_length(sharpe_hat=0.2, benchmark_sr=0.5) is None
    assert minimum_track_record_length(sharpe_hat=0.5, benchmark_sr=0.5) is None


def test_minimum_track_record_length_decreases_with_more_edge():
    modest_edge = minimum_track_record_length(sharpe_hat=0.6, benchmark_sr=0.0)
    strong_edge = minimum_track_record_length(sharpe_hat=2.0, benchmark_sr=0.0)
    assert strong_edge < modest_edge
    assert strong_edge > 0
