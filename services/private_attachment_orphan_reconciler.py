from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import ServiceAttachment
from services.private_attachment_storage_service import (
    PrivateAttachmentStorage,
    get_private_attachment_storage,
)


class PrivateAttachmentOrphanReconciler:
    VARIANT_PREFIX = "public-installation-"
    GRACE_HOURS = 24

    @classmethod
    async def process_batch(
        cls,
        session: AsyncSession,
        *,
        storage: PrivateAttachmentStorage | None = None,
        now: datetime | None = None,
        limit: int = 100,
    ) -> int:
        selected_storage = storage or get_private_attachment_storage()
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(
            hours=cls.GRACE_HOURS
        )
        candidates = await selected_storage.list_variant_candidates(
            variant_prefix=cls.VARIANT_PREFIX,
            older_than=cutoff,
            limit=max(1, min(int(limit), 1000)),
        )
        keys = [item.storage_key for item in candidates]
        if not keys:
            return 0
        referenced_rows = await session.execute(
            select(
                ServiceAttachment.storage_key,
                ServiceAttachment.preview_storage_key,
            ).where(
                ServiceAttachment.storage_provider
                == selected_storage.provider_name,
                or_(
                    ServiceAttachment.storage_key.in_(keys),
                    ServiceAttachment.preview_storage_key.in_(keys),
                ),
            )
        )
        referenced = {
            key
            for row in referenced_rows
            for key in row
            if key is not None
        }
        deleted = 0
        for storage_key in keys:
            if storage_key in referenced:
                continue
            await selected_storage.delete(storage_key)
            deleted += 1
        return deleted
