from __future__ import annotations

import asyncio
import threading
import time

import pytest

from app.errors import QueueBusyError, VerificationTimeoutError
from app.queue_control import EndpointLimiter, _int_env, run_with_queue


def test_int_env_reads_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CCC_CONCURRENCY", "3")
    assert _int_env("CCC_CONCURRENCY", 1) == 3
    monkeypatch.setenv("CCC_CONCURRENCY", "0")
    assert _int_env("CCC_CONCURRENCY", 1) == 1
    monkeypatch.delenv("CCC_CONCURRENCY")
    assert _int_env("CCC_CONCURRENCY", 1) == 1


def test_run_with_queue_rejects_when_busy() -> None:
    async def _case() -> None:
        limiter = EndpointLimiter()
        assert await limiter.try_acquire()
        with pytest.raises(QueueBusyError, match="正在处理"):
            await run_with_queue(
                lambda: None,
                limiter=limiter,
                timeout_seconds=1,
                busy_message="正在处理",
                timeout_message="执行超时",
            )
        await limiter.release()

    asyncio.run(_case())


def test_run_with_queue_times_out_during_execution() -> None:
    async def _case() -> None:
        limiter = EndpointLimiter()

        def _slow() -> None:
            time.sleep(0.2)

        with pytest.raises(VerificationTimeoutError, match="执行超时"):
            await run_with_queue(
                _slow,
                limiter=limiter,
                timeout_seconds=0.01,
                busy_message="正在处理",
                timeout_message="执行超时",
            )
        assert await limiter.try_acquire()
        await limiter.release()

    asyncio.run(_case())


def test_run_with_queue_rejects_second_in_flight_immediately() -> None:
    async def _case() -> None:
        limiter = EndpointLimiter()
        started = threading.Event()
        hold = threading.Event()

        def _slow() -> str:
            started.set()
            hold.wait(timeout=5)
            return "ok"

        first = asyncio.create_task(
            run_with_queue(
                _slow,
                limiter=limiter,
                timeout_seconds=5,
                busy_message="正在处理",
                timeout_message="执行超时",
            )
        )
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()

        with pytest.raises(QueueBusyError, match="正在处理"):
            await run_with_queue(
                lambda: "nope",
                limiter=limiter,
                timeout_seconds=1,
                busy_message="正在处理",
                timeout_message="执行超时",
            )
        hold.set()
        assert await first == "ok"

    asyncio.run(_case())


def test_run_with_queue_allows_up_to_configured_limit() -> None:
    async def _case() -> None:
        limiter = EndpointLimiter(limit=2)
        assert await limiter.try_acquire()
        assert await limiter.try_acquire()
        with pytest.raises(QueueBusyError, match="正在处理"):
            await run_with_queue(
                lambda: None,
                limiter=limiter,
                timeout_seconds=1,
                busy_message="正在处理",
                timeout_message="执行超时",
            )
        await limiter.release()
        result = await run_with_queue(
            lambda: "ok",
            limiter=limiter,
            timeout_seconds=1,
            busy_message="正在处理",
            timeout_message="执行超时",
        )
        assert result == "ok"
        await limiter.release()

    asyncio.run(_case())


def test_ccc_and_test_report_limiters_are_independent() -> None:
    async def _case() -> None:
        ccc = EndpointLimiter()
        report = EndpointLimiter()
        assert await ccc.try_acquire()
        result = await run_with_queue(
            lambda: "ok",
            limiter=report,
            timeout_seconds=1,
            busy_message="正在处理",
            timeout_message="执行超时",
        )
        assert result == "ok"
        await ccc.release()

    asyncio.run(_case())


def test_run_with_queue_releases_slot_after_success() -> None:
    async def _case() -> None:
        limiter = EndpointLimiter()
        result = await run_with_queue(
            lambda: "ok",
            limiter=limiter,
            timeout_seconds=1,
            busy_message="正在处理",
            timeout_message="执行超时",
        )
        assert result == "ok"
        assert await limiter.try_acquire()
        await limiter.release()

    asyncio.run(_case())
