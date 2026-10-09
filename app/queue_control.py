from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

from app.errors import QueueBusyError, VerificationTimeoutError


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return max(0.0, float(raw))


CCC_TIMEOUT_SECONDS = _float_env("CCC_TIMEOUT_SECONDS", 60)
TEST_REPORT_TIMEOUT_SECONDS = _float_env("TEST_REPORT_TIMEOUT_SECONDS", 600)


class EndpointLimiter:
    """Allow one in-flight job; extra requests are rejected immediately."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._busy = False

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self._busy:
                return False
            self._busy = True
            return True

    async def release(self) -> None:
        async with self._lock:
            self._busy = False


_ccc_limiter: EndpointLimiter | None = None
_test_report_limiter: EndpointLimiter | None = None


def ccc_limiter() -> EndpointLimiter:
    global _ccc_limiter
    if _ccc_limiter is None:
        _ccc_limiter = EndpointLimiter()
    return _ccc_limiter


def test_report_limiter() -> EndpointLimiter:
    global _test_report_limiter
    if _test_report_limiter is None:
        _test_report_limiter = EndpointLimiter()
    return _test_report_limiter


def reset_slots_for_tests() -> None:
    global _ccc_limiter, _test_report_limiter
    _ccc_limiter = None
    _test_report_limiter = None


async def run_with_queue[T](
    func: Callable[..., T],
    *args: Any,
    limiter: EndpointLimiter,
    timeout_seconds: float,
    busy_message: str,
    timeout_message: str,
) -> T:
    """Reject immediately if busy, otherwise run the blocking job with an execution timeout."""
    if not await limiter.try_acquire():
        raise QueueBusyError(busy_message)

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise VerificationTimeoutError(timeout_message) from exc
    finally:
        await limiter.release()
