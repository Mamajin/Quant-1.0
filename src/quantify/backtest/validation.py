"""Deflated Sharpe Ratio + Minimum Track Record Length (manual sec 1.6):

Bailey, D.H. & Lopez de Prado, M. (2014), "The Deflated Sharpe Ratio:
Correcting for Selection Bias, Backtest Overfitting and Non-Normality",
Journal of Portfolio Management 40(5): 94-107 (SSRN 2460551).

DSR corrects an observed Sharpe ratio for (a) non-normal returns (skew/
kurtosis) and (b) having picked the best of many trials -- exactly the
"deflated Sharpe across all trials, not just the winner" discipline the
manual's maintenance guide calls for (sec 4.5).
"""
from __future__ import annotations

import math

from scipy.stats import norm

EULER_MASCHERONI = 0.5772156649015329


def probabilistic_sharpe_ratio(sharpe_hat: float, benchmark_sr: float, n_obs: int,
                                skew: float = 0.0, kurtosis: float = 3.0) -> float:
    """PSR(SR*): probability the *true* Sharpe ratio exceeds `benchmark_sr`,
    given an observed (per-period) Sharpe `sharpe_hat` over `n_obs`
    observations. `kurtosis` is non-excess (normal = 3.0).

    With skew=0, kurtosis=3 (normal returns) this reduces to the familiar
    Phi((SR_hat - SR*) * sqrt(n-1)).
    """
    if n_obs <= 1:
        return float("nan")
    variance_term = 1 - skew * sharpe_hat + (kurtosis - 1) / 4 * sharpe_hat**2
    if variance_term <= 0:
        return float("nan")
    z = (sharpe_hat - benchmark_sr) * math.sqrt(n_obs - 1) / math.sqrt(variance_term)
    return float(norm.cdf(z))


def expected_max_sharpe_under_null(sharpe_variance: float, n_trials: int) -> float:
    """SR0: the expected maximum Sharpe ratio you'd observe across
    `n_trials` independent strategies whose *true* Sharpe is zero -- i.e.
    how much "good Sharpe" is explainable by multiple-testing luck alone."""
    if n_trials <= 1:
        return 0.0
    return math.sqrt(sharpe_variance) * (
        (1 - EULER_MASCHERONI) * norm.ppf(1 - 1 / n_trials)
        + EULER_MASCHERONI * norm.ppf(1 - 1 / (n_trials * math.e))
    )


def deflated_sharpe_ratio(sharpe_hat: float, n_obs: int, n_trials: int = 1,
                           skew: float = 0.0, kurtosis: float = 3.0) -> dict:
    """Deflated Sharpe Ratio: PSR evaluated at SR0 (the expected max Sharpe
    achievable by chance across `n_trials`), instead of at 0. This is the
    "how much of my good Sharpe survives reality" number (manual sec 1.6/3.7).

    Returns a dict: sr0 (the noise floor), dsr (probability the strategy's
    true Sharpe exceeds that floor), and `deflated` (True if dsr < 0.95, a
    common "this is probably overfit" cutoff -- informational only).
    """
    variance_term = 1 - skew * sharpe_hat + (kurtosis - 1) / 4 * sharpe_hat**2
    sharpe_variance = max(variance_term, 0.0) / max(n_obs - 1, 1)
    sr0 = expected_max_sharpe_under_null(sharpe_variance, n_trials)
    dsr = probabilistic_sharpe_ratio(sharpe_hat, sr0, n_obs, skew, kurtosis)
    return {
        "sharpe_hat": sharpe_hat,
        "n_trials": n_trials,
        "sr0_noise_floor": sr0,
        "dsr": dsr,
        "likely_overfit": (not math.isnan(dsr)) and dsr < 0.95,
    }


def minimum_track_record_length(sharpe_hat: float, benchmark_sr: float = 0.0,
                                 skew: float = 0.0, kurtosis: float = 3.0,
                                 confidence: float = 0.95) -> float | None:
    """How many observations are needed before this Sharpe is statistically
    credible at `confidence` (manual sec 1.6 'Minimum Track Record Length').
    Returns None if sharpe_hat <= benchmark_sr (never becomes credible)."""
    if sharpe_hat <= benchmark_sr:
        return None
    z_alpha = norm.ppf(confidence)
    variance_term = 1 - skew * sharpe_hat + (kurtosis - 1) / 4 * sharpe_hat**2
    return 1 + variance_term * (z_alpha / (sharpe_hat - benchmark_sr)) ** 2
