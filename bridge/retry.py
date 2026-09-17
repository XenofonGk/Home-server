"""Retry with exponential backoff.

Separated out so the backoff schedule can be tested without waiting on a real
clock -- the sleep function is injected.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, Type, TypeVar

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    attempts: int = 2,
    base_delay_s: float = 2.0,
    exceptions: Iterable[Type[BaseException]] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call fn, retrying on the given exceptions with doubling delays.

    attempts counts total tries, not retries: attempts=2 means one retry.
    Re-raises the last exception if every attempt fails.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    caught = tuple(exceptions)
    last_error: BaseException | None = None

    for attempt in range(attempts):
        try:
            return fn()
        except caught as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            sleep(base_delay_s * (2 ** attempt))

    assert last_error is not None
    raise last_error
