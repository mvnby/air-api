from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, NamedTuple, Optional

from sqlalchemy import and_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    GlobalConfig,
    Storefront,
    StorefrontCatalogRevision,
    StorefrontDomain,
    Tenant,
)
from models.tenancy import TenantScope


CATALOG_REVISION_KEY = "catalog_revision"
CATALOG_REVISION_EPOCH = datetime(1970, 1, 1)
CATALOG_REVISION_DESCRIPTION = "Monotonic public catalog revision for storefront cache freshness."
CATALOG_STATIC_PUBLISHED_REVISION_KEY = "catalog_static_published_revision"
CATALOG_STATIC_PUBLISHED_AT_KEY = "catalog_static_published_at"
CATALOG_STATIC_REBUILD_REQUESTED_REVISION_KEY = "catalog_static_rebuild_requested_revision"
CATALOG_STATIC_REBUILD_REQUESTED_AT_KEY = "catalog_static_rebuild_requested_at"
CATALOG_STATIC_REBUILD_LAST_ERROR_KEY = "catalog_static_rebuild_last_error"


class CatalogRevisionSnapshot(NamedTuple):
    revision: int
    updated_at: datetime


class CatalogStaticPublishSnapshot(NamedTuple):
    current_revision: int
    current_updated_at: datetime
    published_revision: int
    published_at: datetime | None
    requested_revision: int
    requested_at: datetime | None
    last_error: str | None


@dataclass(frozen=True)
class CatalogInvalidationTargetSnapshot:
    tenant_id: int
    storefront_id: int
    is_system: bool
    is_default: bool
    hostnames: tuple[str, ...]


def _parse_revision(value: str | None) -> int:
    try:
        return max(0, int(str(value or "0")))
    except (TypeError, ValueError):
        return 0


def _parse_datetime(value: str | None) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _scope_description(scope: str) -> str:
    normalized_scope = str(scope or "catalog").strip() or "catalog"
    return f"{CATALOG_REVISION_DESCRIPTION} Last scope: {normalized_scope}."


def _static_key_description(label: str) -> str:
    return f"Static storefront rebuild state. {label}"


class CatalogRevisionDAO:
    @staticmethod
    async def _insert_global_revision_if_missing(
        session: AsyncSession,
        *,
        scope: str,
        now: datetime,
    ) -> None:
        values = {
            "key": CATALOG_REVISION_KEY,
            "value": "0",
            "updated_at": now,
            "description": _scope_description(scope),
        }
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            statement = postgresql_insert(GlobalConfig).values(**values)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(GlobalConfig).values(**values)
        else:
            raise NotImplementedError(
                "Global catalog revision upsert is unsupported for "
                f"{dialect_name!r}"
            )
        await session.execute(
            statement.on_conflict_do_nothing(
                index_elements=[GlobalConfig.key]
            )
        )

    @staticmethod
    async def _insert_storefront_revision_if_missing(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        now: datetime,
    ) -> None:
        values = {
            "tenant_id": tenant_scope.tenant_id,
            "storefront_id": tenant_scope.storefront_id,
            "revision": 0,
            "updated_at": now,
        }
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            statement = postgresql_insert(StorefrontCatalogRevision).values(**values)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(StorefrontCatalogRevision).values(**values)
        else:
            raise NotImplementedError(
                "Storefront catalog revision upsert is unsupported for "
                f"{dialect_name!r}"
            )
        await session.execute(
            statement.on_conflict_do_nothing(
                index_elements=[
                    StorefrontCatalogRevision.tenant_id,
                    StorefrontCatalogRevision.storefront_id,
                ]
            )
        )

    @staticmethod
    async def get_storefront_current(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> CatalogRevisionSnapshot:
        row = await session.get(
            StorefrontCatalogRevision,
            (tenant_scope.tenant_id, tenant_scope.storefront_id),
        )
        if row is None:
            return CatalogRevisionSnapshot(
                revision=0,
                updated_at=CATALOG_REVISION_EPOCH,
            )
        return CatalogRevisionSnapshot(
            revision=max(0, int(row.revision)),
            updated_at=row.updated_at or CATALOG_REVISION_EPOCH,
        )

    @staticmethod
    async def bump_storefront(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> CatalogRevisionSnapshot:
        now = datetime.now(timezone.utc)
        await CatalogRevisionDAO._insert_storefront_revision_if_missing(
            session,
            tenant_scope=tenant_scope,
            now=now,
        )
        statement = select(StorefrontCatalogRevision).where(
            StorefrontCatalogRevision.tenant_id == tenant_scope.tenant_id,
            StorefrontCatalogRevision.storefront_id == tenant_scope.storefront_id,
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        row = (await session.execute(statement)).scalar_one()
        row.revision = max(0, int(row.revision)) + 1
        row.updated_at = now
        session.add(row)
        await session.flush()
        return CatalogRevisionSnapshot(
            revision=row.revision,
            updated_at=row.updated_at,
        )

    @staticmethod
    async def list_invalidation_targets(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope | None = None,
    ) -> tuple[CatalogInvalidationTargetSnapshot, ...]:
        statement = (
            select(Tenant, Storefront, StorefrontDomain)
            .join(Storefront, Storefront.tenant_id == Tenant.id)
            .outerjoin(
                StorefrontDomain,
                and_(
                    StorefrontDomain.storefront_id == Storefront.id,
                    StorefrontDomain.status == "active",
                ),
            )
            .where(
                Tenant.status == "active",
                Storefront.status == "active",
            )
            .order_by(
                Tenant.id.asc(),
                Storefront.id.asc(),
                StorefrontDomain.is_primary.desc(),
                StorefrontDomain.id.asc(),
            )
        )
        if tenant_scope is not None:
            statement = statement.where(
                Tenant.id == tenant_scope.tenant_id,
                Storefront.id == tenant_scope.storefront_id,
            )

        grouped: dict[
            tuple[int, int],
            tuple[bool, bool, list[str]],
        ] = {}
        for tenant, storefront, domain in (await session.execute(statement)).all():
            key = (int(tenant.id), int(storefront.id))
            target = grouped.setdefault(
                key,
                (bool(tenant.is_system), bool(storefront.is_default), []),
            )
            if domain is not None:
                target[2].append(str(domain.hostname))

        return tuple(
            CatalogInvalidationTargetSnapshot(
                tenant_id=tenant_id,
                storefront_id=storefront_id,
                is_system=values[0],
                is_default=values[1],
                hostnames=tuple(sorted(set(values[2]), key=str.casefold)),
            )
            for (tenant_id, storefront_id), values in grouped.items()
        )

    @staticmethod
    async def _get_global_config_map(
        session: AsyncSession,
        keys: Iterable[str],
    ) -> dict[str, GlobalConfig]:
        normalized_keys = tuple(dict.fromkeys(str(key) for key in keys))
        if not normalized_keys:
            return {}
        rows = (
            await session.execute(
                select(GlobalConfig).where(GlobalConfig.key.in_(normalized_keys))
            )
        ).scalars().all()
        return {row.key: row for row in rows}

    @staticmethod
    async def _upsert_global_config(
        session: AsyncSession,
        *,
        key: str,
        value: str,
        description: str,
        now: datetime,
    ) -> GlobalConfig:
        row = (
            await session.execute(
                select(GlobalConfig).where(GlobalConfig.key == key).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            row = GlobalConfig(
                key=key,
                value=value,
                updated_at=now,
                description=description,
            )
        else:
            row.value = value
            row.updated_at = now
            row.description = description
        session.add(row)
        return row

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
        now = datetime.now()
        await CatalogRevisionDAO._insert_global_revision_if_missing(
            session,
            scope=scope,
            now=now,
        )
        statement = select(GlobalConfig).where(
            GlobalConfig.key == CATALOG_REVISION_KEY
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        row = (await session.execute(statement)).scalar_one()

        revision = _parse_revision(row.value) + 1
        row.value = str(revision)
        row.updated_at = now
        row.description = _scope_description(scope)

        session.add(row)
        await session.flush()
        return CatalogRevisionSnapshot(
            revision=revision,
            updated_at=row.updated_at or now,
        )

    @staticmethod
    async def get_static_publish_snapshot(session: AsyncSession) -> CatalogStaticPublishSnapshot:
        current = await CatalogRevisionDAO.get_current(session)
        rows = await CatalogRevisionDAO._get_global_config_map(
            session,
            (
                CATALOG_STATIC_PUBLISHED_REVISION_KEY,
                CATALOG_STATIC_PUBLISHED_AT_KEY,
                CATALOG_STATIC_REBUILD_REQUESTED_REVISION_KEY,
                CATALOG_STATIC_REBUILD_REQUESTED_AT_KEY,
                CATALOG_STATIC_REBUILD_LAST_ERROR_KEY,
            ),
        )

        published_revision = _parse_revision(
            rows.get(CATALOG_STATIC_PUBLISHED_REVISION_KEY).value
            if rows.get(CATALOG_STATIC_PUBLISHED_REVISION_KEY)
            else None
        )
        requested_revision = _parse_revision(
            rows.get(CATALOG_STATIC_REBUILD_REQUESTED_REVISION_KEY).value
            if rows.get(CATALOG_STATIC_REBUILD_REQUESTED_REVISION_KEY)
            else None
        )
        last_error = (
            rows[CATALOG_STATIC_REBUILD_LAST_ERROR_KEY].value.strip()
            if rows.get(CATALOG_STATIC_REBUILD_LAST_ERROR_KEY)
            and rows[CATALOG_STATIC_REBUILD_LAST_ERROR_KEY].value.strip()
            else None
        )

        return CatalogStaticPublishSnapshot(
            current_revision=current.revision,
            current_updated_at=current.updated_at,
            published_revision=published_revision,
            published_at=_parse_datetime(
                rows.get(CATALOG_STATIC_PUBLISHED_AT_KEY).value
                if rows.get(CATALOG_STATIC_PUBLISHED_AT_KEY)
                else None
            ),
            requested_revision=requested_revision,
            requested_at=_parse_datetime(
                rows.get(CATALOG_STATIC_REBUILD_REQUESTED_AT_KEY).value
                if rows.get(CATALOG_STATIC_REBUILD_REQUESTED_AT_KEY)
                else None
            ),
            last_error=last_error,
        )

    @staticmethod
    async def mark_static_rebuild_requested(
        session: AsyncSession,
        *,
        revision: int,
    ) -> CatalogStaticPublishSnapshot:
        now = datetime.now()
        await CatalogRevisionDAO._upsert_global_config(
            session,
            key=CATALOG_STATIC_REBUILD_REQUESTED_REVISION_KEY,
            value=str(max(0, int(revision))),
            description=_static_key_description("Last requested catalog revision."),
            now=now,
        )
        await CatalogRevisionDAO._upsert_global_config(
            session,
            key=CATALOG_STATIC_REBUILD_REQUESTED_AT_KEY,
            value=now.isoformat(),
            description=_static_key_description("Last rebuild request timestamp."),
            now=now,
        )
        await CatalogRevisionDAO._upsert_global_config(
            session,
            key=CATALOG_STATIC_REBUILD_LAST_ERROR_KEY,
            value="",
            description=_static_key_description("Last rebuild failure text."),
            now=now,
        )
        await session.flush()
        return await CatalogRevisionDAO.get_static_publish_snapshot(session)

    @staticmethod
    async def mark_static_rebuild_completed(
        session: AsyncSession,
        *,
        revision: int,
    ) -> CatalogStaticPublishSnapshot:
        now = datetime.now()
        await CatalogRevisionDAO._upsert_global_config(
            session,
            key=CATALOG_STATIC_PUBLISHED_REVISION_KEY,
            value=str(max(0, int(revision))),
            description=_static_key_description("Last successfully published catalog revision."),
            now=now,
        )
        await CatalogRevisionDAO._upsert_global_config(
            session,
            key=CATALOG_STATIC_PUBLISHED_AT_KEY,
            value=now.isoformat(),
            description=_static_key_description("Last successful publish timestamp."),
            now=now,
        )
        await CatalogRevisionDAO._upsert_global_config(
            session,
            key=CATALOG_STATIC_REBUILD_LAST_ERROR_KEY,
            value="",
            description=_static_key_description("Last rebuild failure text."),
            now=now,
        )
        await session.flush()
        return await CatalogRevisionDAO.get_static_publish_snapshot(session)

    @staticmethod
    async def mark_static_rebuild_failed(
        session: AsyncSession,
        *,
        revision: int,
        error: str,
    ) -> CatalogStaticPublishSnapshot:
        now = datetime.now()
        await CatalogRevisionDAO._upsert_global_config(
            session,
            key=CATALOG_STATIC_REBUILD_REQUESTED_REVISION_KEY,
            value=str(max(0, int(revision))),
            description=_static_key_description("Last requested catalog revision."),
            now=now,
        )
        await CatalogRevisionDAO._upsert_global_config(
            session,
            key=CATALOG_STATIC_REBUILD_LAST_ERROR_KEY,
            value=str(error or "GitHub Actions rebuild failed")[:1000],
            description=_static_key_description("Last rebuild failure text."),
            now=now,
        )
        await session.flush()
        return await CatalogRevisionDAO.get_static_publish_snapshot(session)
