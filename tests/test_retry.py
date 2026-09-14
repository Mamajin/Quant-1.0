"""Retry-with-backoff tests (manual NFR-003)."""
import pytest

from quantify.ingest.retry import retry_with_backoff


def test_succeeds_first_try_no_sleep():
    sleeps = []
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    result = retry_with_backoff(fn, sleep_fn=sleeps.append)
    assert result == "ok"
    assert calls["n"] == 1
    assert sleeps == []


def test_succeeds_after_transient_failures():
    sleeps = []
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    result = retry_with_backoff(fn, max_attempts=5, base_delay=1.0, jitter=0.0, sleep_fn=sleeps.append)
    assert result == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2  # slept after attempts 1 and 2, not after the successful 3rd


def test_raises_last_exception_after_exhausting_attempts():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError(f"fail {calls['n']}")

    with pytest.raises(ValueError, match="fail 3"):
        retry_with_backoff(fn, max_attempts=3, base_delay=0.01, jitter=0.0, sleep_fn=lambda d: None)
    assert calls["n"] == 3


def test_delay_grows_exponentially_and_is_capped():
    sleeps = []

    def fn():
        raise RuntimeError("always fails")

    with pytest.raises(RuntimeError):
        retry_with_backoff(fn, max_attempts=5, base_delay=1.0, max_delay=3.0, jitter=0.0, sleep_fn=sleeps.append)

    # base_delay * 2^(attempt-1): 1, 2, 4->capped to 3, 4->capped to 3
    assert sleeps == [1.0, 2.0, 3.0, 3.0]


def test_jitter_adds_nonnegative_extra_delay():
    sleeps = []

    def fn():
        raise RuntimeError("fails")

    with pytest.raises(RuntimeError):
        retry_with_backoff(fn, max_attempts=2, base_delay=1.0, jitter=0.5, sleep_fn=sleeps.append)

    assert len(sleeps) == 1
    assert 1.0 <= sleeps[0] <= 1.5
