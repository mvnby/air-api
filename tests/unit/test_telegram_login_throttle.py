from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from services.login_throttle_service import LoginThrottleExceeded, LoginThrottleService
from services.telegram_login_throttle_service import TelegramLoginThrottleService


@pytest.mark.asyncio
async def test_office_telegram_starts_have_separate_budget_and_do_not_poison_password_login(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'telegram-throttle.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        now = datetime.now(timezone.utc)
        address = "192.0.2.50"
        for _ in range(6):
            result = await TelegramLoginThrottleService.record_failure(session, "shared-office", address, now=now)
            assert not result.blocked
        # Password authentication still has its own fresh account and source
        # counters even after several successful Telegram starts at this IP.
        reservation = await LoginThrottleService.reserve_attempt(session, "shared-office", address, now=now)
        assert reservation.account_row.failure_count == 0
        assert reservation.source_row.failure_count == 0
        await session.rollback()
        for _ in range(TelegramLoginThrottleService.MAX_FAILURES - 6):
            result = await TelegramLoginThrottleService.record_failure(session, "shared-office", address, now=now)
        assert result.blocked and result.retry_after_seconds > 0
        with pytest.raises(LoginThrottleExceeded):
            await TelegramLoginThrottleService.record_failure(session, "shared-office", address, now=now)
    await engine.dispose()
