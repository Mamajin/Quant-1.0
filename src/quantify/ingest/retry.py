"""Retry with exponential backoff (manual NFR-003: 'ingestion retries with
exponential backoff; no crash on provider outage')."""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.1,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    """Call fn(), retrying on exception with exponential backoff + jitter.
    Re-raises the last exception if every attempt fails -- the caller (e.g.
    ingest_symbol's per-symbol try/except) decides what "no crash" means at
    the pipeline level; this just makes transient failures self-heal first.
    `sleep_fn` is injectable so tests don't have to wait in real time.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - generic retry wrapper, re-raised if attempts exhausted
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay += random.uniform(0, jitter * delay)
            logger.warning("Attempt %d/%d failed (%s), retrying in %.1fs", attempt, max_attempts, exc, delay)
            sleep_fn(delay)
    raise last_exc
