import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from crud.catalog_revision import (
    CatalogInvalidationTargetSnapshot,
    CatalogRevisionDAO,
    CatalogRevisionSnapshot,
)
from models import Brand, Product
from models.tenancy import TenantScope
from services.catalog_invalidation_contracts import (
    CatalogCacheInvalidationRequestedV1,
    catalog_cache_key,
)
from services.catalog_invalidation_event_service import (
    CatalogInvalidationEventService,
)
from services.catalog_purge_service import (
    build_catalog_purge_paths,
    normalize_catalog_origin,
)


logger = logging.getLogger(__name__)


class CatalogRevisionService:
    @staticmethod
    def _serialize(row: CatalogRevisionSnapshot) -> dict[str, Any]:
        return {
            "revision": row.revision,
            "updated_at": row.updated_at,
        }

    @staticmethod
    async def get_current(session: AsyncSession) -> dict[str, Any]:
        row = await CatalogRevisionDAO.get_current(session)
        return CatalogRevisionService._serialize(row)

    @staticmethod
    async def get_contextual(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        global_snapshot = await CatalogRevisionDAO.get_current(session)
        storefront_snapshot = await CatalogRevisionDAO.get_storefront_current(
            session,
            tenant_scope=tenant_scope,
        )
        return {
            "revision": global_snapshot.revision,
            "storefront_revision": storefront_snapshot.revision,
            "cache_key": catalog_cache_key(
                global_revision=global_snapshot.revision,
                storefront_revision=storefront_snapshot.revision,
            ),
            "updated_at": CatalogRevisionService._latest_updated_at(
                global_snapshot.updated_at,
                storefront_snapshot.updated_at,
            ),
        }

    @staticmethod
    def _serialize_static_rebuild_status(row: Any) -> dict[str, Any]:
        needs_rebuild = row.current_revision > row.published_revision
        rebuild_requested_for_current = (
            needs_rebuild
            and row.requested_revision >= row.current_revision
            and row.requested_at is not None
            and row.last_error is None
        )
        if not needs_rebuild:
            state = "fresh"
        elif rebuild_requested_for_current:
            state = "queued"
        else:
            state = "stale"

        return {
            "current_revision": row.current_revision,
            "current_revision_updated_at": row.current_updated_at,
            "published_revision": row.published_revision,
            "published_at": row.published_at,
            "requested_revision": row.requested_revision or None,
            "requested_at": row.requested_at,
            "needs_rebuild": needs_rebuild,
            "state": state,
            "last_error": row.last_error,
        }

    @staticmethod
    async def get_static_rebuild_status(session: AsyncSession) -> dict[str, Any]:
        row = await CatalogRevisionDAO.get_static_publish_snapshot(session)
        return CatalogRevisionService._serialize_static_rebuild_status(row)

    @staticmethod
    async def mark_static_rebuild_requested(
        session: AsyncSession,
        revision: int,
    ) -> dict[str, Any]:
        row = await CatalogRevisionDAO.mark_static_rebuild_requested(
            session,
            revision=revision,
        )
        return CatalogRevisionService._serialize_static_rebuild_status(row)

    @staticmethod
    async def mark_static_rebuild_completed(
        session: AsyncSession,
        revision: int,
    ) -> dict[str, Any]:
        row = await CatalogRevisionDAO.mark_static_rebuild_completed(
            session,
            revision=revision,
        )
        return CatalogRevisionService._serialize_static_rebuild_status(row)

    @staticmethod
    async def mark_static_rebuild_failed(
        session: AsyncSession,
        revision: int,
        error: str,
    ) -> dict[str, Any]:
        row = await CatalogRevisionDAO.mark_static_rebuild_failed(
            session,
            revision=revision,
            error=error,
        )
        return CatalogRevisionService._serialize_static_rebuild_status(row)

    @staticmethod
    async def bump(
        session: AsyncSession,
        scope: str,
        product_ids: Optional[Iterable[int]] = None,
        slugs: Optional[Iterable[str]] = None,
        brand_slugs: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        row = await CatalogRevisionDAO.bump(
            session,
            scope=scope,
            product_ids=product_ids,
            slugs=slugs,
            brand_slugs=brand_slugs,
        )
        return CatalogRevisionService._serialize(row)

    @staticmethod
    async def stage_invalidation(
        session: AsyncSession,
        reason: str,
        product_ids: Optional[Iterable[int]] = None,
        slugs: Optional[Iterable[str]] = None,
        brand_slugs: Optional[Iterable[str]] = None,
        tenant_scope: TenantScope | None = None,
    ) -> dict[str, Any]:
        """Stage revision changes and outbox events in the caller transaction."""

        product_id_values = CatalogRevisionService._normalize_ints(product_ids)
        product_slug_values = CatalogRevisionService._normalize_strings(slugs)
        explicit_brand_slug_values = CatalogRevisionService._normalize_strings(brand_slugs)

        (
            resolved_product_slug_values,
            resolved_brand_slug_values,
        ) = await CatalogRevisionService.get_product_purge_targets(session, product_id_values)
        purge_product_slugs = CatalogRevisionService._dedupe_strings(
            [*product_slug_values, *resolved_product_slug_values]
        )
        purge_brand_slugs = CatalogRevisionService._dedupe_strings(
            [*explicit_brand_slug_values, *resolved_brand_slug_values]
        )
        paths = build_catalog_purge_paths(
            product_slugs=purge_product_slugs,
            brand_slugs=purge_brand_slugs,
        )

        if tenant_scope is None:
            global_revision = await CatalogRevisionService.bump(
                session,
                scope=reason,
                product_ids=product_id_values,
                slugs=purge_product_slugs,
                brand_slugs=purge_brand_slugs,
            )
            global_snapshot = CatalogRevisionSnapshot(
                revision=int(global_revision["revision"]),
                updated_at=global_revision["updated_at"],
            )
            targets = await CatalogRevisionDAO.list_invalidation_targets(session)
            for target in targets:
                target_scope = TenantScope(
                    tenant_id=target.tenant_id,
                    storefront_id=target.storefront_id,
                    is_system=target.is_system,
                )
                storefront_snapshot = (
                    await CatalogRevisionDAO.get_storefront_current(
                        session,
                        tenant_scope=target_scope,
                    )
                )
                await CatalogRevisionService._enqueue_invalidation(
                    session,
                    invalidation_scope="global",
                    reason=reason,
                    target=target,
                    paths=paths,
                    global_snapshot=global_snapshot,
                    storefront_snapshot=storefront_snapshot,
                )
            if not targets:
                logger.warning(
                    "Global catalog invalidation staged without an active storefront "
                    "reason=%s revision=%s",
                    reason,
                    global_snapshot.revision,
                )
            return CatalogRevisionService._serialize(global_snapshot)

        targets = await CatalogRevisionDAO.list_invalidation_targets(
            session,
            tenant_scope=tenant_scope,
        )
        if len(targets) != 1:
            raise ValueError("Catalog invalidation storefront scope is unavailable")
        global_snapshot = await CatalogRevisionDAO.get_current(session)
        storefront_snapshot = await CatalogRevisionDAO.bump_storefront(
            session,
            tenant_scope=tenant_scope,
        )
        await CatalogRevisionService._enqueue_invalidation(
            session,
            invalidation_scope="storefront",
            reason=reason,
            target=targets[0],
            paths=paths,
            global_snapshot=global_snapshot,
            storefront_snapshot=storefront_snapshot,
        )
        return {
            "revision": global_snapshot.revision,
            "storefront_revision": storefront_snapshot.revision,
            "cache_key": catalog_cache_key(
                global_revision=global_snapshot.revision,
                storefront_revision=storefront_snapshot.revision,
            ),
            "updated_at": CatalogRevisionService._latest_updated_at(
                global_snapshot.updated_at,
                storefront_snapshot.updated_at,
            ),
        }

    @staticmethod
    async def _enqueue_invalidation(
        session: AsyncSession,
        *,
        invalidation_scope: str,
        reason: str,
        target: CatalogInvalidationTargetSnapshot,
        paths: tuple[str, ...],
        global_snapshot: CatalogRevisionSnapshot,
        storefront_snapshot: CatalogRevisionSnapshot,
    ) -> None:
        cache_key = catalog_cache_key(
            global_revision=global_snapshot.revision,
            storefront_revision=storefront_snapshot.revision,
        )
        payload = CatalogCacheInvalidationRequestedV1(
            scope=invalidation_scope,
            tenant_id=target.tenant_id,
            storefront_id=target.storefront_id,
            origins=CatalogRevisionService._origins_for_target(target),
            paths=list(paths),
            global_revision=global_snapshot.revision,
            storefront_revision=storefront_snapshot.revision,
            cache_key=cache_key,
            reason=reason,
        )
        await CatalogInvalidationEventService.enqueue_requested(
            session,
            idempotency_key=(
                f"catalog:{target.tenant_id}:{target.storefront_id}:"
                f"{invalidation_scope}:{cache_key}"
            ),
            payload=payload,
            priority=40,
            max_attempts=12,
        )

    @staticmethod
    def _origins_for_target(
        target: CatalogInvalidationTargetSnapshot,
    ) -> list[str]:
        origins: list[str] = []
        if target.is_system and target.is_default:
            origins.append(normalize_catalog_origin(settings.PUBLIC_SITE_URL))
        origins.extend(
            normalize_catalog_origin(f"https://{hostname}")
            for hostname in target.hostnames
        )
        normalized = sorted(set(origins), key=str.casefold)
        if (target.is_system and target.is_default) or target.hostnames:
            if not normalized:
                raise ValueError(
                    "Routable storefront catalog invalidation has no origin"
                )
        return normalized

    @staticmethod
    def _latest_updated_at(*values: datetime) -> datetime:
        normalized: list[datetime] = []
        for value in values:
            if value.tzinfo is None or value.utcoffset() is None:
                normalized.append(value.replace(tzinfo=timezone.utc))
            else:
                normalized.append(value.astimezone(timezone.utc))
        return max(normalized)

    @staticmethod
    async def get_product_purge_targets(
        session: AsyncSession,
        product_ids: Optional[Iterable[int]],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        product_id_values = CatalogRevisionService._normalize_ints(product_ids)
        if not product_id_values:
            return (), ()

        rows = (
            await session.execute(
                select(Product.slug, Brand.slug)
                .outerjoin(Brand, Product.brand_id == Brand.id)
                .where(Product.id.in_(product_id_values))
            )
        ).all()

        product_slugs = CatalogRevisionService._normalize_strings(row[0] for row in rows)
        brand_slugs = CatalogRevisionService._normalize_strings(row[1] for row in rows)
        return product_slugs, brand_slugs

    @staticmethod
    async def get_product_brand_slugs(
        session: AsyncSession,
        product_ids: Optional[Iterable[int]],
    ) -> tuple[str, ...]:
        _, brand_slugs = await CatalogRevisionService.get_product_purge_targets(session, product_ids)
        return brand_slugs

    @staticmethod
    def _normalize_ints(values: Optional[Iterable[int]]) -> tuple[int, ...]:
        result: list[int] = []
        for value in values or []:
            try:
                normalized = int(value)
            except (TypeError, ValueError):
                continue
            result.append(normalized)
        return tuple(dict.fromkeys(result))

    @staticmethod
    def _normalize_strings(values: Optional[Iterable[str]]) -> tuple[str, ...]:
        result: list[str] = []
        for value in values or []:
            normalized = str(value or "").strip()
            if normalized:
                result.append(normalized)
        return CatalogRevisionService._dedupe_strings(result)

    @staticmethod
    def _dedupe_strings(values: Iterable[str]) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return tuple(result)
