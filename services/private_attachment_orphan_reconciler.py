from __future__ import annotations

import os
import secrets
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import ServiceAttachment, StorageReconciliationCursor
from services.private_attachment_storage_service import (
    PrivateAttachmentStorage,
    PrivateStoragePage,
    get_private_attachment_storage,
)


@dataclass(frozen=True)
class _ReconciliationClaim:
    name: str
    lease_token: str
    cursor: str | None
    database_now: datetime


class PrivateAttachmentOrphanReconciler:
    VARIANT_PREFIXES = ("public-installation-", "public-repair-")
    GRACE_HOURS = 24
    LEASE_SECONDS = 5 * 60

    @classmethod
    async def process_batch(
        cls,
        session: AsyncSession,
        *,
        storage: PrivateAttachmentStorage | None = None,
        now: datetime | None = None,
        limit: int = 100,
        worker_id: str | None = None,
    ) -> int:
        selected_storage = storage or get_private_attachment_storage()
        # Kept only as a compatibility input for existing callers; application
        # clock values must never influence deletion eligibility.
        del now
        bounded_limit = max(1, min(int(limit), 1000))
        normalized_worker = str(
            worker_id or f"{socket.gethostname()}:{os.getpid()}"
        )[:128]
        async with session.begin():
            claim = await cls._claim(
                session,
                storage=selected_storage,
                worker_id=normalized_worker,
            )
        if claim is None:
            return 0

        try:
            page = await selected_storage.list_reconciliation_page(
                variant_prefixes=cls.VARIANT_PREFIXES,
                older_than=claim.database_now - timedelta(hours=cls.GRACE_HOURS),
                cursor=claim.cursor,
                limit=bounded_limit,
            )
            cls._validate_page(page, limit=bounded_limit)
            referenced = await cls._referenced_keys(
                session,
                storage=selected_storage,
                keys=[item.storage_key for item in page.candidates],
            )
            deleted = 0
            for candidate in page.candidates:
                if candidate.storage_key in referenced:
                    continue
                await selected_storage.delete(candidate.storage_key)
                deleted += 1
        except BaseException:
            await cls._release_without_advance(session, claim=claim)
            raise

        await cls._advance(
            session,
            claim=claim,
            next_cursor=page.next_cursor,
        )
        return deleted

    @staticmethod
    def _cursor_name(storage: PrivateAttachmentStorage) -> str:
        return f"private-attachment-orphans:{storage.inventory_id}"[:160]

    @classmethod
    async def _claim(
        cls,
        session: AsyncSession,
        *,
        storage: PrivateAttachmentStorage,
        worker_id: str,
    ) -> _ReconciliationClaim | None:
        now = await cls._database_now(session)
        name = cls._cursor_name(storage)
        values = {
            "name": name,
            "storage_provider": storage.provider_name,
            "updated_at": now,
        }
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            insert_statement = postgresql_insert(StorageReconciliationCursor)
        elif dialect_name == "sqlite":
            insert_statement = sqlite_insert(StorageReconciliationCursor)
        else:  # pragma: no cover - production and tests use PostgreSQL/SQLite
            raise RuntimeError(
                f"Unsupported reconciliation database dialect: {dialect_name}"
            )
        await session.execute(
            insert_statement.values(**values).on_conflict_do_nothing(
                index_elements=["name"]
            )
        )
        statement = select(StorageReconciliationCursor).where(
            StorageReconciliationCursor.name == name,
            or_(
                StorageReconciliationCursor.lease_expires_at.is_(None),
                StorageReconciliationCursor.lease_expires_at <= now,
            ),
        )
        if dialect_name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        row = await session.scalar(statement)
        if row is None:
            return None
        lease_token = secrets.token_hex(16)
        row.storage_provider = storage.provider_name
        row.lease_owner = worker_id
        row.lease_token = lease_token
        row.lease_expires_at = now + timedelta(seconds=cls.LEASE_SECONDS)
        row.updated_at = now
        session.add(row)
        await session.flush()
        return _ReconciliationClaim(
            name=name,
            lease_token=lease_token,
            cursor=row.cursor,
            database_now=now,
        )

    @staticmethod
    async def _referenced_keys(
        session: AsyncSession,
        *,
        storage: PrivateAttachmentStorage,
        keys: list[str],
    ) -> set[str]:
        if not keys:
            return set()
        async with session.begin():
            rows = await session.execute(
                select(
                    ServiceAttachment.storage_key,
                    ServiceAttachment.preview_storage_key,
                ).where(
                    ServiceAttachment.storage_provider == storage.provider_name,
                    or_(
                        ServiceAttachment.storage_key.in_(keys),
                        ServiceAttachment.preview_storage_key.in_(keys),
                    ),
                )
            )
            return {
                key
                for row in rows
                for key in row
                if key is not None
            }

    @classmethod
    async def _advance(
        cls,
        session: AsyncSession,
        *,
        claim: _ReconciliationClaim,
        next_cursor: str | None,
    ) -> bool:
        async with session.begin():
            now = await cls._database_now(session)
            statement = select(StorageReconciliationCursor).where(
                StorageReconciliationCursor.name == claim.name,
                StorageReconciliationCursor.lease_token == claim.lease_token,
                StorageReconciliationCursor.lease_expires_at.is_not(None),
                StorageReconciliationCursor.lease_expires_at > now,
            )
            if session.get_bind().dialect.name == "postgresql":
                statement = statement.with_for_update()
            row = await session.scalar(statement)
            if row is None:
                return False
            row.cursor = next_cursor
            row.lease_owner = None
            row.lease_token = None
            row.lease_expires_at = None
            row.updated_at = now
            session.add(row)
            return True

    @staticmethod
    async def _release_without_advance(
        session: AsyncSession,
        *,
        claim: _ReconciliationClaim,
    ) -> None:
        try:
            if session.in_transaction():
                await session.rollback()
            async with session.begin():
                statement = select(StorageReconciliationCursor).where(
                    StorageReconciliationCursor.name == claim.name,
                    StorageReconciliationCursor.lease_token == claim.lease_token,
                )
                if session.get_bind().dialect.name == "postgresql":
                    statement = statement.with_for_update()
                row = await session.scalar(statement)
                if row is None:
                    return
                now = await PrivateAttachmentOrphanReconciler._database_now(
                    session
                )
                row.lease_owner = None
                row.lease_token = None
                row.lease_expires_at = None
                row.updated_at = now
                session.add(row)
        except Exception:
            # A crash or release failure is safe: the durable lease expires and
            # the same page is retried. Deletion itself is idempotent.
            if session.in_transaction():
                await session.rollback()

    @staticmethod
    def _validate_page(page: PrivateStoragePage, *, limit: int) -> None:
        if page.examined < 0 or page.examined > limit:
            raise RuntimeError("Private storage exceeded reconciliation page limit")
        if not page.wrapped and not page.next_cursor:
            raise RuntimeError("Private storage page did not advance its cursor")
        if len(page.candidates) > page.examined:
            raise RuntimeError("Private storage returned impossible candidate count")

    @staticmethod
    async def _database_now(session: AsyncSession) -> datetime:
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            clock = func.clock_timestamp()
        elif dialect_name == "sqlite":
            clock = func.strftime("%Y-%m-%d %H:%M:%f", "now")
        else:  # pragma: no cover - production and tests use PostgreSQL/SQLite
            clock = func.current_timestamp()
        value = (await session.execute(select(clock))).scalar_one()
        return PrivateAttachmentOrphanReconciler._as_utc(value)

    @staticmethod
    def _as_utc(value: object) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace(" ", "T"))
        if not isinstance(value, datetime):
            raise TypeError("Database clock did not return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
