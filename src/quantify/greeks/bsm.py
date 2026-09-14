"""Black-Scholes-Merton pricing and Greeks (manual sec 3.3, 3.6).

Worked example from Appendix E / sec 3.6: S=100, K=100, T=0.25, r=4%, sigma=30%
  d1 ~= 0.142, d2 ~= -0.008, N(d1) ~= 0.556, N(d2) ~= 0.497 -> C ~= $6.4
See tests/test_bsm_golden.py.

All functions accept scalars or numpy arrays (elementwise) so they can be
applied directly to a whole option chain at once.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

Right = str  # "c" or "p"


def _d1_d2(S, K, T, r, sigma):
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    T = np.asarray(T, dtype=float)
    r = np.asarray(r, dtype=float)
    sigma = np.asarray(sigma, dtype=float)

    # Guard against non-physical inputs (expired or zero-vol contracts) so
    # callers get intrinsic-value behavior instead of NaN/inf (sec 3.6 pitfall).
    T_safe = np.where(T > 1e-9, T, 1e-9)
    sigma_safe = np.where(sigma > 1e-6, sigma, 1e-6)

    d1 = (np.log(S / K) + (r + 0.5 * sigma_safe**2) * T_safe) / (sigma_safe * np.sqrt(T_safe))
    d2 = d1 - sigma_safe * np.sqrt(T_safe)
    return d1, d2, T_safe, sigma_safe


def black_scholes(flag: Right, S, K, T, r, sigma):
    """Option price. flag: 'c' for call, 'p' for put."""
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    T = np.asarray(T, dtype=float)
    r = np.asarray(r, dtype=float)
    d1, d2, T_safe, _ = _d1_d2(S, K, T, r, sigma)
    disc_K = K * np.exp(-r * T_safe)

    if flag == "c":
        price = S * norm.cdf(d1) - disc_K * norm.cdf(d2)
        intrinsic = np.maximum(S - K, 0.0)
    elif flag == "p":
        price = disc_K * norm.cdf(-d2) - S * norm.cdf(-d1)
        intrinsic = np.maximum(K - S, 0.0)
    else:
        raise ValueError(f"flag must be 'c' or 'p', got {flag!r}")

    # At/near expiry, collapse to intrinsic value rather than a noisy BSM number.
    return np.where(T <= 1e-9, intrinsic, price)


def delta(flag: Right, S, K, T, r, sigma):
    d1, _, _, _ = _d1_d2(S, K, T, r, sigma)
    if flag == "c":
        return norm.cdf(d1)
    elif flag == "p":
        return norm.cdf(d1) - 1.0
    raise ValueError(f"flag must be 'c' or 'p', got {flag!r}")


def gamma(flag: Right, S, K, T, r, sigma):
    S = np.asarray(S, dtype=float)
    d1, _, T_safe, sigma_safe = _d1_d2(S, K, T, r, sigma)
    return norm.pdf(d1) / (S * sigma_safe * np.sqrt(T_safe))


def vega(flag: Right, S, K, T, r, sigma):
    """Sensitivity per 1 vol *point* (e.g. IV 30% -> 31%), matching sec 3.3's
    plain-English example ("vega 0.10, IV +1% -> +$0.10")."""
    S = np.asarray(S, dtype=float)
    d1, _, T_safe, _ = _d1_d2(S, K, T, r, sigma)
    raw_vega = S * norm.pdf(d1) * np.sqrt(T_safe)  # dPrice / d(sigma as decimal)
    return raw_vega / 100.0


def theta(flag: Right, S, K, T, r, sigma):
    """Daily time decay (annual theta / 365), matching sec 3.3's example
    ("Theta -0.05 -> lose $5/contract/day")."""
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    r = np.asarray(r, dtype=float)
    d1, d2, T_safe, sigma_safe = _d1_d2(S, K, T, r, sigma)
    disc_K = K * np.exp(-r * T_safe)
    term1 = -(S * norm.pdf(d1) * sigma_safe) / (2 * np.sqrt(T_safe))

    if flag == "c":
        annual_theta = term1 - r * disc_K * norm.cdf(d2)
    elif flag == "p":
        annual_theta = term1 + r * disc_K * norm.cdf(-d2)
    else:
        raise ValueError(f"flag must be 'c' or 'p', got {flag!r}")

    return annual_theta / 365.0


def rho(flag: Right, S, K, T, r, sigma):
    """Sensitivity per 1% change in the risk-free rate (raw rho / 100)."""
    K = np.asarray(K, dtype=float)
    r = np.asarray(r, dtype=float)
    _, d2, T_safe, _ = _d1_d2(S, K, T, r, sigma)
    disc_K = K * np.exp(-r * T_safe)
    if flag == "c":
        raw_rho = K * T_safe * disc_K * norm.cdf(d2)
    elif flag == "p":
        raw_rho = -K * T_safe * disc_K * norm.cdf(-d2)
    else:
        raise ValueError(f"flag must be 'c' or 'p', got {flag!r}")
    return raw_rho / 100.0


def all_greeks(flag: Right, S, K, T, r, sigma) -> dict:
    return {
        "delta": delta(flag, S, K, T, r, sigma),
        "gamma": gamma(flag, S, K, T, r, sigma),
        "theta": theta(flag, S, K, T, r, sigma),
        "vega": vega(flag, S, K, T, r, sigma),
        "rho": rho(flag, S, K, T, r, sigma),
    }
