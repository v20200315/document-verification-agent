from __future__ import annotations

import asyncio
import time

import pytest

from app.errors import QueueTimeoutError, VerificationTimeoutError
from app.queue_control import run_with_queue


def test_run_with_queue_times_out_while_waiting_for_slot() -> None:
    async def _case() -> None:
        slots = asyncio.Semaphore(1)
        await slots.acquire()
        with pytest.raises(QueueTimeoutError, match="排队超时"):
            await run_with_queue(
                lambda: None,
                slots=slots,
                queue_wait_seconds=0.01,
                timeout_seconds=1,
                queue_timeout_message="排队超时",
                timeout_message="执行超时",
            )

    asyncio.run(_case())


def test_run_with_queue_times_out_during_execution() -> None:
    async def _case() -> None:
        slots = asyncio.Semaphore(1)

        def _slow() -> None:
            time.sleep(0.2)

        with pytest.raises(VerificationTimeoutError, match="执行超时"):
            await run_with_queue(
                _slow,
                slots=slots,
                queue_wait_seconds=1,
                timeout_seconds=0.01,
                queue_timeout_message="排队超时",
                timeout_message="执行超时",
            )
        assert not slots.locked()

    asyncio.run(_case())


def test_run_with_queue_releases_slot_after_success() -> None:
    async def _case() -> None:
        slots = asyncio.Semaphore(1)
        result = await run_with_queue(
            lambda: "ok",
            slots=slots,
            queue_wait_seconds=1,
            timeout_seconds=1,
            queue_timeout_message="排队超时",
            timeout_message="执行超时",
        )
        assert result == "ok"
        assert not slots.locked()

    asyncio.run(_case())
