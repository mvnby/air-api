from __future__ import annotations

import hashlib
import hmac
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import AuthLoginThrottle
from services.staff_user_service import StaffUserService


@dataclass(frozen=True)
class LoginThrottleDecision:
    blocked: bool
    retry_after_seconds: int = 0


@dataclass(frozen=True)
class LoginAttemptReservation:
    source_row: AuthLoginThrottle
    account_row: AuthLoginThrottle
    current_time: datetime


class LoginThrottleExceeded(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Password login is temporarily rate limited")
        self.retry_after_seconds = max(1, int(retry_after_seconds))


class LoginThrottleService:
    MAX_FAILURES = 5
    SOURCE_MAX_FAILURES = 20
    SOURCE_BUCKET_COUNT = 65_536
    GLOBAL_MAX_FAILURES = 100
    FAILURE_WINDOW = timedelta(minutes=15)
    BLOCK_DURATION = timedelta(minutes=15)
    RETENTION = timedelta(minutes=30)
    _FINGERPRINT_DOMAIN = b"manager-password-login\x00"
    _SOURCE_FINGERPRINT_DOMAIN = b"manager-password-login-source\x00"
    _GLOBAL_FINGERPRINT_DOMAIN = b"manager-password-login-global\x00"

    @classmethod
    def fingerprint(cls, username: str | None) -> str:
        normalized = StaffUserService.normalize_username(username)
        if normalized:
            encoded = normalized.encode("utf-8", errors="surrogatepass")
            identity = b"\x01" + len(encoded).to_bytes(4, "big") + encoded
        else:
            identity = b"\x00"
        payload = cls._FINGERPRINT_DOMAIN + identity
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def global_fingerprint(cls) -> str:
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            cls._GLOBAL_FINGERPRINT_DOMAIN,
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def source_fingerprint(cls, source: str | None) -> str:
        encoded = str(source or "unavailable").encode(
            "utf-8",
            errors="surrogatepass",
        )
        source_digest = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            cls._SOURCE_FINGERPRINT_DOMAIN + encoded,
            hashlib.sha256,
        ).digest()
        bucket = int.from_bytes(source_digest[:4], "big") % cls.SOURCE_BUCKET_COUNT
        payload = (
            cls._SOURCE_FINGERPRINT_DOMAIN
            + bucket.to_bytes(4, "big")
        )
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    async def reserve_attempt(
        cls,
        session: AsyncSession,
        username: str | None,
        source: str | None = None,
        *,
        now: datetime | None = None,
    ) -> LoginAttemptReservation:
        """Serialize one source/account attempt until auth commits its outcome."""
        current_time = await cls._current_time(session, now)
        source_row = await cls._get_or_create_locked(
            session,
            fingerprint=cls.source_fingerprint(source),
            current_time=current_time,
        )
        source_retry_after = cls._active_retry_after(source_row, current_time)
        if source_retry_after:
            await session.rollback()
            raise LoginThrottleExceeded(source_retry_after)

        account_row = await cls._get_or_create_locked(
            session,
            fingerprint=cls.fingerprint(username),
            current_time=current_time,
        )
        account_retry_after = cls._active_retry_after(account_row, current_time)
        if account_retry_after:
            await session.rollback()
            raise LoginThrottleExceeded(account_retry_after)

        await cls._delete_expired_rows(session, current_time)

        return LoginAttemptReservation(
            source_row=source_row,
            account_row=account_row,
            current_time=current_time,
        )

    @classmethod
    async def record_failure(
        cls,
        session: AsyncSession,
        username: str | None,
        source: str | None = None,
        *,
        now: datetime | None = None,
        reservation: LoginAttemptReservation | None = None,
    ) -> LoginThrottleDecision:
        if reservation is None:
            reservation = await cls.reserve_attempt(
                session,
                username,
                source,
                now=now,
            )
        current_time = reservation.current_time

        # Global state is acquired after the source/account reservation. This
        # keeps unrelated credentials concurrent during bcrypt while every
        # production login follows one consistent lock order.
        global_row = await cls._get_or_create_locked(
            session,
            fingerprint=cls.global_fingerprint(),
            current_time=current_time,
        )
        global_retry_after, global_was_blocked = cls._record_row_failure(
            global_row,
            current_time=current_time,
            max_failures=cls.GLOBAL_MAX_FAILURES,
        )

        source_retry_after, _ = cls._record_row_failure(
            reservation.source_row,
            current_time=current_time,
            max_failures=cls.SOURCE_MAX_FAILURES,
        )

        account_retry_after = 0
        if not global_was_blocked:
            account_retry_after, _ = cls._record_row_failure(
                reservation.account_row,
                current_time=current_time,
                max_failures=cls.MAX_FAILURES,
            )
            session.add(reservation.account_row)
        else:
            await session.delete(reservation.account_row)

        session.add(global_row)
        session.add(reservation.source_row)
        await session.commit()
        retry_after = max(
            global_retry_after,
            source_retry_after,
            account_retry_after,
        )
        return LoginThrottleDecision(
            blocked=retry_after > 0,
            retry_after_seconds=retry_after,
        )

    @classmethod
    def _active_retry_after(
        cls,
        row: AuthLoginThrottle,
        current_time: datetime,
    ) -> int:
        if row.blocked_until is None:
            return 0
        blocked_until = cls._as_utc(row.blocked_until)
        if blocked_until <= current_time:
            return 0
        return cls._retry_after(blocked_until, current_time)

    @classmethod
    async def clear(
        cls,
        session: AsyncSession,
        username: str | None,
    ) -> None:
        await session.execute(
            delete(AuthLoginThrottle).where(
                AuthLoginThrottle.fingerprint == cls.fingerprint(username)
            )
        )
        await session.commit()

    @classmethod
    def _record_row_failure(
        cls,
        row: AuthLoginThrottle,
        *,
        current_time: datetime,
        max_failures: int,
    ) -> tuple[int, bool]:
        blocked_until = (
            cls._as_utc(row.blocked_until)
            if row.blocked_until is not None
            else None
        )
        was_blocked = blocked_until is not None and blocked_until > current_time
        if was_blocked:
            retry_after = cls._retry_after(blocked_until, current_time)
        else:
            window_started_at = cls._as_utc(row.window_started_at)
            if (
                blocked_until is not None
                or window_started_at <= current_time - cls.FAILURE_WINDOW
            ):
                row.failure_count = 1
                row.window_started_at = current_time
                row.blocked_until = None
            else:
                row.failure_count += 1

            if row.failure_count >= max_failures:
                row.blocked_until = current_time + cls.BLOCK_DURATION
                retry_after = cls._retry_after(row.blocked_until, current_time)
            else:
                retry_after = 0

        row.updated_at = current_time
        return retry_after, was_blocked

    @classmethod
    async def _delete_expired_rows(
        cls,
        session: AsyncSession,
        current_time: datetime,
    ) -> None:
        cutoff = current_time - cls.RETENTION
        await session.execute(
            delete(AuthLoginThrottle).where(
                AuthLoginThrottle.updated_at < cutoff,
                or_(
                    AuthLoginThrottle.blocked_until.is_(None),
                    AuthLoginThrottle.blocked_until <= current_time,
                ),
            ).execution_options(synchronize_session=False)
        )

    @classmethod
    async def _get_or_create_locked(
        cls,
        session: AsyncSession,
        *,
        fingerprint: str,
        current_time: datetime,
    ) -> AuthLoginThrottle:
        row = (
            await session.execute(
                select(AuthLoginThrottle)
                .where(AuthLoginThrottle.fingerprint == fingerprint)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is not None:
            return row

        candidate = AuthLoginThrottle(
            fingerprint=fingerprint,
            failure_count=0,
            window_started_at=current_time,
            updated_at=current_time,
        )
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
            return candidate
        except IntegrityError:
            row = (
                await session.execute(
                    select(AuthLoginThrottle)
                    .where(AuthLoginThrottle.fingerprint == fingerprint)
                    .with_for_update()
                )
            ).scalar_one()
            return row

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    async def _current_time(
        cls,
        session: AsyncSession,
        override: datetime | None,
    ) -> datetime:
        if override is not None:
            return cls._as_utc(override)
        database_time = (await session.execute(select(func.now()))).scalar_one()
        return cls._as_utc(database_time)

    @staticmethod
    def _retry_after(blocked_until: datetime, current_time: datetime) -> int:
        return max(
            1,
            math.ceil((blocked_until - current_time).total_seconds()),
        )


__all__ = [
    "LoginAttemptReservation",
    "LoginThrottleDecision",
    "LoginThrottleExceeded",
    "LoginThrottleService",
]
