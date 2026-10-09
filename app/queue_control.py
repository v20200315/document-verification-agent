from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

from app.errors import QueueTimeoutError, VerificationTimeoutError


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return max(1, int(raw))


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return max(0.0, float(raw))


CCC_CONCURRENCY = _int_env("CCC_CONCURRENCY", 3)
CCC_QUEUE_WAIT_SECONDS = _float_env("CCC_QUEUE_WAIT_SECONDS", 20)
CCC_TIMEOUT_SECONDS = _float_env("CCC_TIMEOUT_SECONDS", 60)

TEST_REPORT_CONCURRENCY = _int_env("TEST_REPORT_CONCURRENCY", 2)
TEST_REPORT_QUEUE_WAIT_SECONDS = _float_env("TEST_REPORT_QUEUE_WAIT_SECONDS", 40)
TEST_REPORT_TIMEOUT_SECONDS = _float_env("TEST_REPORT_TIMEOUT_SECONDS", 600)

_ccc_slots: asyncio.Semaphore | None = None
_test_report_slots: asyncio.Semaphore | None = None


def ccc_slots() -> asyncio.Semaphore:
    global _ccc_slots
    if _ccc_slots is None:
        _ccc_slots = asyncio.Semaphore(CCC_CONCURRENCY)
    return _ccc_slots


def test_report_slots() -> asyncio.Semaphore:
    global _test_report_slots
    if _test_report_slots is None:
        _test_report_slots = asyncio.Semaphore(TEST_REPORT_CONCURRENCY)
    return _test_report_slots


def reset_slots_for_tests() -> None:
    global _ccc_slots, _test_report_slots
    _ccc_slots = None
    _test_report_slots = None


async def run_with_queue[T](
    func: Callable[..., T],
    *args: Any,
    slots: asyncio.Semaphore,
    queue_wait_seconds: float,
    timeout_seconds: float,
    queue_timeout_message: str,
    timeout_message: str,
) -> T:
    """Wait for a concurrency slot, then run the blocking job with an execution timeout."""
    try:
        await asyncio.wait_for(slots.acquire(), timeout=queue_wait_seconds)
    except TimeoutError as exc:
        raise QueueTimeoutError(queue_timeout_message) from exc

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise VerificationTimeoutError(timeout_message) from exc
    finally:
        slots.release()
