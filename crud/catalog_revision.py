from datetime import datetime
from typing import Iterable, NamedTuple, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import GlobalConfig


CATALOG_REVISION_KEY = "catalog_revision"
CATALOG_REVISION_EPOCH = datetime(1970, 1, 1)
CATALOG_REVISION_DESCRIPTION = "Monotonic public catalog revision for storefront cache freshness."


class CatalogRevisionSnapshot(NamedTuple):
    revision: int
    updated_at: datetime


def _parse_revision(value: str | None) -> int:
    try:
        return max(0, int(str(value or "0")))
    except (TypeError, ValueError):
        return 0


def _scope_description(scope: str) -> str:
    normalized_scope = str(scope or "catalog").strip() or "catalog"
    return f"{CATALOG_REVISION_DESCRIPTION} Last scope: {normalized_scope}."


class CatalogRevisionDAO:
    @staticmethod
    async def get_current(session: AsyncSession) -> CatalogRevisionSnapshot:
        row = (
            await session.execute(
                select(GlobalConfig).where(GlobalConfig.key == CATALOG_REVISION_KEY)
            )
        ).scalar_one_or_none()
        if row is None:
            return CatalogRevisionSnapshot(revision=0, updated_at=CATALOG_REVISION_EPOCH)
        return CatalogRevisionSnapshot(
            revision=_parse_revision(row.value),
            updated_at=row.updated_at or CATALOG_REVISION_EPOCH,
        )

    @staticmethod
    async def bump(
        session: AsyncSession,
        *,
        scope: str,
        product_ids: Optional[Iterable[int]] = None,
        slugs: Optional[Iterable[str]] = None,
        brand_slugs: Optional[Iterable[str]] = None,
    ) -> CatalogRevisionSnapshot:
        stmt = select(GlobalConfig).where(GlobalConfig.key == CATALOG_REVISION_KEY).with_for_update()
        row = (await session.execute(stmt)).scalar_one_or_none()
        now = datetime.now()

        if row is None:
            row = GlobalConfig(
                key=CATALOG_REVISION_KEY,
                value="0",
                updated_at=now,
                description=_scope_description(scope),
            )
            session.add(row)
            await session.flush()

        revision = _parse_revision(row.value) + 1
        row.value = str(revision)
        row.updated_at = now
        row.description = _scope_description(scope)

        session.add(row)
        await session.commit()
        await session.refresh(row)
        return CatalogRevisionSnapshot(
            revision=revision,
            updated_at=row.updated_at or now,
        )
