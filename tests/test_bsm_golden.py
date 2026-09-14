"""Golden-file tests for Black-Scholes-Merton pricing/Greeks against the
manual's own worked example (Appendix E / sec 3.6):
S=100, K=100, T=0.25, r=4%, sigma=30% -> C ~= $6.4
(manual shows intermediate values d1~=0.142, d2~=-0.008, N(d1)~=0.556, N(d2)~=0.497)
"""
import pytest

from quantify.greeks.bsm import black_scholes, delta, gamma, theta, vega

S, K, T, r, sigma = 100.0, 100.0, 0.25, 0.04, 0.30


def test_call_price_matches_manual_worked_example():
    price = float(black_scholes("c", S, K, T, r, sigma))
    assert price == pytest.approx(6.4, abs=0.1)


def test_put_call_parity():
    import numpy as np
    call = float(black_scholes("c", S, K, T, r, sigma))
    put = float(black_scholes("p", S, K, T, r, sigma))
    assert call - put == pytest.approx(S - K * np.exp(-r * T), abs=1e-8)


def test_delta_bounds_and_relationship():
    d_call = float(delta("c", S, K, T, r, sigma))
    d_put = float(delta("p", S, K, T, r, sigma))
    assert 0.0 < d_call < 1.0
    assert d_put == pytest.approx(d_call - 1.0, abs=1e-8)


def test_gamma_positive_and_same_for_call_and_put():
    g_call = float(gamma("c", S, K, T, r, sigma))
    g_put = float(gamma("p", S, K, T, r, sigma))
    assert g_call > 0
    assert g_call == pytest.approx(g_put, abs=1e-10)


def test_theta_negative_for_long_option():
    assert float(theta("c", S, K, T, r, sigma)) < 0
    assert float(theta("p", S, K, T, r, sigma)) < 0


def test_vega_positive():
    assert float(vega("c", S, K, T, r, sigma)) > 0


def test_deep_itm_call_converges_to_intrinsic():
    price = float(black_scholes("c", S=1000.0, K=100, T=0.01, r=r, sigma=sigma))
    assert price == pytest.approx(900.0, abs=1.0)


def test_expired_option_is_intrinsic_value():
    call = float(black_scholes("c", S=110.0, K=100.0, T=0.0, r=r, sigma=sigma))
    put = float(black_scholes("p", S=110.0, K=100.0, T=0.0, r=r, sigma=sigma))
    assert call == pytest.approx(10.0, abs=1e-8)
    assert put == pytest.approx(0.0, abs=1e-8)
