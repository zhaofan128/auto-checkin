"""Retry and rate-limit helpers."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

from .errors import TransientError

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 15.0
    jitter: bool = True
    retry_on: tuple[type[BaseException], ...] = (TransientError,)


def retry_call(
    fn: Callable[[], T],
    policy: RetryPolicy = RetryPolicy(),
    *,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    attempts = max(1, policy.attempts)
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except policy.retry_on as exc:
            if attempt >= attempts:
                raise
            delay = min(policy.max_delay_s, policy.base_delay_s * (2 ** (attempt - 1)))
            if policy.jitter:
                delay *= 0.5 + random.random()
            if on_retry is not None:
                on_retry(attempt, exc)
            time.sleep(delay)
    raise AssertionError("unreachable")


class RateLimiter:
    def __init__(
        self,
        min_interval_s: float = 0.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval_s = max(0.0, min_interval_s)
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self.min_interval_s and self._last is not None:
            delay = self.min_interval_s - (self._clock() - self._last)
            if delay > 0:
                self._sleep(delay)
        self._last = self._clock()
