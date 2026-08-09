import asyncio

import pytest

from services.manager_content_ai_limiter import (
    ManagerContentAILimiter,
    ManagerContentAIRateLimitError,
)


@pytest.mark.asyncio
async def test_content_ai_limiter_enforces_per_identity_window():
    now = [100.0]
    limiter = ManagerContentAILimiter(
        max_concurrent=1,
        max_requests=2,
        window_seconds=60,
        clock=lambda: now[0],
    )

    async with limiter.limit("1:manager"):
        pass
    async with limiter.limit("1:manager"):
        pass

    with pytest.raises(ManagerContentAIRateLimitError) as error:
        async with limiter.limit("1:manager"):
            pass
    assert error.value.retry_after == 60

    async with limiter.limit("1:other-manager"):
        pass
    now[0] = 161.0
    async with limiter.limit("1:manager"):
        pass


@pytest.mark.asyncio
async def test_content_ai_limiter_rejects_excess_concurrency_without_queueing():
    limiter = ManagerContentAILimiter(
        max_concurrent=1,
        max_requests=10,
        acquire_timeout=0.01,
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold_slot():
        async with limiter.limit("1:first"):
            entered.set()
            await release.wait()

    task = asyncio.create_task(hold_slot())
    await entered.wait()
    try:
        with pytest.raises(ManagerContentAIRateLimitError) as error:
            async with limiter.limit("1:second"):
                pass
        assert error.value.retry_after == 1
    finally:
        release.set()
        await task
