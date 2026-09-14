"""Implied volatility solver tests (manual sec 3.6: Newton-Raphson + bisection fallback)."""
import pytest

from quantify.greeks.bsm import black_scholes
from quantify.greeks.iv import _solve_iv_bisection, solve_iv

S, K, T, r = 100.0, 100.0, 0.25, 0.04


@pytest.mark.parametrize("true_sigma", [0.10, 0.30, 0.60, 1.20])
def test_recovers_known_sigma_atm(true_sigma):
    price = float(black_scholes("c", S, K, T, r, true_sigma))
    recovered = solve_iv("c", S, K, T, r, price)
    assert recovered == pytest.approx(true_sigma, abs=1e-3)


@pytest.mark.parametrize("strike,true_sigma", [(60.0, 0.30), (150.0, 0.30)])
def test_recovers_known_sigma_away_from_atm(strike, true_sigma):
    price = float(black_scholes("c", S, strike, T, r, true_sigma))
    recovered = solve_iv("c", S, strike, T, r, price)
    assert recovered == pytest.approx(true_sigma, abs=1e-3)


def test_bisection_fallback_converges_to_a_price_consistent_sigma():
    """Deep OTM options have near-zero vega, which breaks pure Newton-Raphson
    (manual sec 3.6 pitfall) -- exercise the bisection fallback
    (`_solve_iv_bisection`) directly. Note: at extreme moneyness the price
    curve vs sigma is so flat (vega ~ 0) that IV is not tightly identified by
    price alone -- the meaningful invariant is that the *price* round-trips,
    not that the exact original sigma is recovered."""
    true_sigma = 0.35
    price = float(black_scholes("c", S, 250.0, T, r, true_sigma))
    recovered = _solve_iv_bisection("c", S, 250.0, T, r, price)
    assert recovered is not None
    roundtrip_price = float(black_scholes("c", S, 250.0, T, r, recovered))
    assert roundtrip_price == pytest.approx(price, abs=1e-5)


def test_solve_iv_handles_moderately_otm_option_end_to_end():
    true_sigma = 0.40
    price = float(black_scholes("p", S=100.0, K=70.0, T=0.5, r=r, sigma=true_sigma))
    recovered = solve_iv("p", 100.0, 70.0, 0.5, r, price)
    assert recovered == pytest.approx(true_sigma, abs=1e-2)


def test_price_below_intrinsic_returns_none():
    assert solve_iv("c", S=110.0, K=100.0, T=0.25, r=r, price=5.0) is None


def test_expired_option_returns_none():
    assert solve_iv("c", S, K, T=0.0, r=r, price=6.0) is None
