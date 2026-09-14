"""Implied volatility solver: Newton-Raphson (fast, uses vega) with a bisection
fallback (robust) -- manual sec 3.6: 'Implied volatility solving'.

Documented pitfalls handled here (sec 3.6):
  - "no solution below intrinsic value" -> price is clamped above intrinsic
  - "vega->0 deep ITM/OTM breaks Newton" -> falls back to bisection
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

from .bsm import _d1_d2, black_scholes

MIN_SIGMA = 1e-4
MAX_SIGMA = 5.0
NEWTON_MAX_ITER = 50
NEWTON_TOL = 1e-6
BISECTION_MAX_ITER = 100


def _raw_vega(flag, S, K, T, r, sigma) -> float:
    d1, _, T_safe, _ = _d1_d2(S, K, T, r, sigma)
    return float(S * norm.pdf(d1) * np.sqrt(T_safe))


def solve_iv(flag: str, S: float, K: float, T: float, r: float, price: float) -> float | None:
    """Solve for sigma given an observed option price. Returns None if no
    sensible solution exists (expired, or price below intrinsic value)."""
    S, K, T, r, price = float(S), float(K), float(T), float(r), float(price)

    if T <= 1e-9:
        return None

    intrinsic = max(S - K, 0.0) if flag == "c" else max(K - S, 0.0)
    if price <= intrinsic + 1e-9:
        return None  # sec 3.6: "no solution below intrinsic value"

    # Brenner-Subrahmanyam initial guess, clamped to a sane range.
    sigma = max(MIN_SIGMA, min(MAX_SIGMA, np.sqrt(2 * np.pi / T) * (price / S)))

    for _ in range(NEWTON_MAX_ITER):
        model_price = float(black_scholes(flag, S, K, T, r, sigma))
        diff = model_price - price
        if abs(diff) < NEWTON_TOL:
            return float(np.clip(sigma, MIN_SIGMA, MAX_SIGMA))

        v = _raw_vega(flag, S, K, T, r, sigma)
        if v < 1e-8:
            break  # vega too small (deep ITM/OTM) -> hand off to bisection

        sigma -= diff / v
        if sigma <= MIN_SIGMA or sigma >= MAX_SIGMA or not np.isfinite(sigma):
            break  # Newton stepped out of range -> hand off to bisection

    return _solve_iv_bisection(flag, S, K, T, r, price)


def _solve_iv_bisection(flag: str, S: float, K: float, T: float, r: float, price: float) -> float | None:
    lo, hi = MIN_SIGMA, MAX_SIGMA
    price_lo = float(black_scholes(flag, S, K, T, r, lo))
    price_hi = float(black_scholes(flag, S, K, T, r, hi))

    if not (price_lo <= price <= price_hi):
        return None  # price outside achievable range even at MAX_SIGMA

    for _ in range(BISECTION_MAX_ITER):
        mid = (lo + hi) / 2
        model_price = float(black_scholes(flag, S, K, T, r, mid))
        if abs(model_price - price) < NEWTON_TOL:
            return mid
        if model_price < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
