from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Text, cast, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Order
from services.general_media_storage_service import (
    GeneralMediaStorage,
    get_general_media_storage,
)


REPAIR_PUBLIC_WRITE_NAMESPACE = "public-repair-write"


class RepairDiagnosticStorageService:
    """Own per-attempt repair uploads and reconcile only abandoned objects."""

    ORPHAN_GRACE_HOURS = 24

    @staticmethod
    def new_attempt_namespace(
        *,
        tenant_id: int,
        storefront_id: int,
        key_hash: str,
        nonce: str | None = None,
    ) -> str:
        attempt_nonce = nonce or secrets.token_hex(16)
        if (
            len(key_hash) != 64
            or any(char not in "0123456789abcdef" for char in key_hash)
        ):
            raise ValueError("Invalid repair idempotency key hash")
        if (
            len(attempt_nonce) != 32
            or any(char not in "0123456789abcdef" for char in attempt_nonce)
        ):
            raise ValueError("Invalid repair storage attempt nonce")
        return (
            f"{REPAIR_PUBLIC_WRITE_NAMESPACE}/"
            f"{int(tenant_id)}/{int(storefront_id)}/"
            f"{key_hash}-{attempt_nonce}"
        )

    @classmethod
    async def reconcile_orphans(
        cls,
        session: AsyncSession,
        *,
        storage: GeneralMediaStorage | None = None,
        now: datetime | None = None,
        limit: int = 100,
    ) -> int:
        selected_storage = storage or get_general_media_storage()
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(
            hours=cls.ORPHAN_GRACE_HOURS
        )
        candidates = await selected_storage.list_namespace_candidates(
            namespace_prefix=REPAIR_PUBLIC_WRITE_NAMESPACE,
            older_than=cutoff,
            limit=max(1, min(int(limit), 1000)),
        )
        candidate_paths = {item.path for item in candidates}
        if not candidate_paths:
            return 0

        referenced = set()
        # JSON/JSONB operators differ between SQLite and PostgreSQL. A bounded
        # text prefilter keeps the query portable and avoids loading every
        # repair order; exact path equality is still checked in Python before
        # any delete. Candidate paths are unique, high-entropy object keys.
        ordered_paths = sorted(candidate_paths)
        for offset in range(0, len(ordered_paths), 20):
            path_batch = ordered_paths[offset : offset + 20]
            rows = await session.execute(
                select(Order.technical_meta).where(
                    Order.workflow_type == "repair",
                    Order.technical_meta.is_not(None),
                    or_(
                        *[
                            cast(Order.technical_meta, Text).contains(path)
                            for path in path_batch
                        ]
                    ),
                )
            )
            for technical_meta in rows.scalars():
                referenced.update(
                    cls._referenced_paths(
                        technical_meta,
                        candidates=candidate_paths,
                    )
                )

        deleted = 0
        for candidate in candidates:
            if candidate.path in referenced:
                continue
            await selected_storage.delete_media(candidate.path)
            deleted += 1
        return deleted

    @staticmethod
    def _referenced_paths(
        technical_meta: Any,
        *,
        candidates: set[str],
    ) -> set[str]:
        if not isinstance(technical_meta, dict):
            return set()
        repair_meta = technical_meta.get("repair")
        photos = repair_meta.get("photos") if isinstance(repair_meta, dict) else None
        if not isinstance(photos, dict):
            return set()
        referenced: set[str] = set()
        for items in photos.values():
            if not isinstance(items, list):
                continue
            for item in items:
                path = item.get("storage_path") if isinstance(item, dict) else None
                if isinstance(path, str) and path in candidates:
                    referenced.add(path)
        return referenced
