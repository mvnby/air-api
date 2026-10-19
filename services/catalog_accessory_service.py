"""Series compatibility and model exceptions, separate from Wi-Fi capability flags."""

from collections import defaultdict
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.product import ProductDAO
from crud.public_catalog import PublicCatalogDAO
from models import Product, ProductSeries
from models.catalog_accessory import ProductAccessoryOverride, SeriesAccessoryLink
from models.tenancy import TenantScope
from schemas_catalog_accessories import (
    ManagerAccessoriesWorkspace,
    ManagerAccessoryItem,
    ProductAccessoriesUpdate,
    PublicCatalogAccessory,
    SeriesAccessoriesUpdate,
)
from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService
from services.product_read_service import ProductReadService
from services.product_response_mapper import map_product_to_response
from services.public_catalog_visibility_service import PublicCatalogVisibilityService


def _accessory_type(product: Product) -> str | None:
    value = (product.specs or {}).get("accessory_type")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _suggested_for_purchase(product: Product, accessory_type: str | None) -> bool:
    if accessory_type != "wifi_module":
        return True
    specs = product.specs or {}
    state = specs.get("wifi_state")
    if state is None:
        typed = specs.get("__typed_specs") or {}
        entry = typed.get("wifi_state") if isinstance(typed, dict) else None
        state = entry.get("value") if isinstance(entry, dict) else None
    return state == "ready"


class CatalogAccessoryService:
    @staticmethod
    async def _target(session, target_type: str, target_id: int, *, lock=False):
        model = ProductSeries if target_type == "series" else Product
        stmt = select(model).where(model.id == target_id)
        if lock:
            stmt = stmt.with_for_update()
        target = (await session.execute(stmt)).scalar_one_or_none()
        if target is None:
            raise HTTPException(404, "Серия не найдена." if target_type == "series" else "Товар не найден.")
        return target

    @staticmethod
    async def _links(session, *, series_ids: Iterable[int], product_ids: Iterable[int]):
        series_ids, product_ids = list(series_ids), list(product_ids)
        series = list((await session.execute(
            select(SeriesAccessoryLink)
            .where(SeriesAccessoryLink.series_id.in_(series_ids))
            .order_by(SeriesAccessoryLink.sort_order, SeriesAccessoryLink.accessory_product_id)
        )).scalars().all()) if series_ids else []
        overrides = list((await session.execute(
            select(ProductAccessoryOverride)
            .where(ProductAccessoryOverride.product_id.in_(product_ids))
            .order_by(ProductAccessoryOverride.sort_order, ProductAccessoryOverride.accessory_product_id)
        )).scalars().all()) if product_ids else []
        return series, overrides

    @classmethod
    async def get_workspace(cls, session: AsyncSession, *, target_type: str, target_id: int) -> ManagerAccessoriesWorkspace:
        target = await cls._target(session, target_type, target_id)
        series_id = int(target.id) if target_type == "series" else target.series_id
        series, overrides = await cls._links(
            session, series_ids=[series_id] if series_id else [],
            product_ids=[target_id] if target_type == "product" else [],
        )
        inherited_ids = [link.accessory_product_id for link in series]
        override_map = {row.accessory_product_id: row.is_enabled for row in overrides}
        ordered_ids = list(dict.fromkeys([*inherited_ids, *override_map]))
        products = {int(p.id): p for p in await ProductDAO.get_by_ids(session, ordered_ids)}
        items = []
        for product_id in ordered_ids:
            product = products.get(product_id)
            if product is None:
                continue
            inherited = target_type == "product" and product_id in inherited_ids
            override = override_map.get(product_id)
            items.append(ManagerAccessoryItem(
                accessory_product_id=product_id, title=product.title, slug=product.slug,
                accessory_type=_accessory_type(product), is_published=product.is_published,
                inherited=inherited, override=override,
                is_enabled=override if override is not None else True,
            ))
        return ManagerAccessoriesWorkspace(target_type=target_type, target_id=target_id, series_id=series_id, items=items)

    @staticmethod
    async def _validate_accessories(session, accessory_ids: list[int], *, product_id=None, series_id=None):
        if len(accessory_ids) > 100 or len(set(accessory_ids)) != len(accessory_ids) or any(value < 1 for value in accessory_ids):
            raise HTTPException(400, "Укажите до 100 уникальных ID аксессуаров.")
        products = await ProductDAO.get_by_ids(session, accessory_ids)
        if len(products) != len(accessory_ids):
            raise HTTPException(400, "Один из аксессуаров не найден.")
        for product in products:
            if product.product_kind != "accessory":
                raise HTTPException(400, f"Товар «{product.title}» должен иметь тип «Аксессуар».")
            if product.id == product_id or (series_id is not None and product.series_id == series_id):
                raise HTTPException(400, "Товар не может быть аксессуаром самого себя или собственной серии.")

    @classmethod
    async def set_series_accessories(cls, session: AsyncSession, *, series_id: int, payload: SeriesAccessoriesUpdate) -> ManagerAccessoriesWorkspace:
        await cls._target(session, "series", series_id, lock=True)
        ids = payload.accessory_product_ids
        await cls._validate_accessories(session, ids, series_id=series_id)
        current, _ = await cls._links(session, series_ids=[series_id], product_ids=[])
        changed = [link.accessory_product_id for link in current] != ids
        if changed:
            await session.execute(delete(SeriesAccessoryLink).where(SeriesAccessoryLink.series_id == series_id))
            session.add_all([SeriesAccessoryLink(series_id=series_id, accessory_product_id=value, sort_order=index) for index, value in enumerate(ids)])
        affected_ids = list((await session.execute(select(Product.id).where(Product.series_id == series_id))).scalars()) if changed else []
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session, producer="catalog_accessory.set_series_accessories", changed=changed, product_ids=affected_ids,
        )
        return await cls.get_workspace(session, target_type="series", target_id=series_id)

    @classmethod
    async def set_product_accessories(cls, session: AsyncSession, *, product_id: int, payload: ProductAccessoriesUpdate) -> ManagerAccessoriesWorkspace:
        await cls._target(session, "product", product_id, lock=True)
        values = [(item.accessory_product_id, item.is_enabled) for item in payload.overrides]
        await cls._validate_accessories(session, [value[0] for value in values], product_id=product_id)
        _, current = await cls._links(session, series_ids=[], product_ids=[product_id])
        changed = [(row.accessory_product_id, row.is_enabled) for row in current] != values
        if changed:
            await session.execute(delete(ProductAccessoryOverride).where(ProductAccessoryOverride.product_id == product_id))
            session.add_all([ProductAccessoryOverride(product_id=product_id, accessory_product_id=value, is_enabled=enabled, sort_order=index) for index, (value, enabled) in enumerate(values)])
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session, producer="catalog_accessory.set_product_accessories", changed=changed, product_ids=[product_id],
        )
        return await cls.get_workspace(session, target_type="product", target_id=product_id)

    @classmethod
    async def resolve_public(cls, session: AsyncSession, products: Iterable[Product], *, tenant_scope: TenantScope) -> dict[int, list[PublicCatalogAccessory]]:
        """Resolve compatibility in bulk, then apply the canonical storefront boundary.

        Series ordering survives explicit includes/excludes; additional model items
        follow series items. No compatibility follows from brand or Wi-Fi tags.
        Callers pass already-visible parent products and the trusted storefront scope.
        """
        products = list(products)
        result = {int(product.id): [] for product in products}
        if not products:
            return result
        series, overrides = await cls._links(
            session, series_ids={p.series_id for p in products if p.series_id}, product_ids=result,
        )
        series_map = defaultdict(list)
        override_map = defaultdict(dict)
        for link in series:
            series_map[link.series_id].append(link.accessory_product_id)
        for row in overrides:
            override_map[row.product_id][row.accessory_product_id] = row.is_enabled
        selected = {}
        for product in products:
            inherited = series_map[product.series_id]
            explicit = override_map[int(product.id)]
            selected[int(product.id)] = [
                (accessory_id, "product" if accessory_id in explicit else "series")
                for accessory_id in dict.fromkeys([*inherited, *explicit])
                if accessory_id != product.id and explicit.get(accessory_id, accessory_id in inherited)
            ]
        accessory_ids = sorted({value for values in selected.values() for value, _ in values})
        if not accessory_ids:
            return result
        if await PublicCatalogVisibilityService.is_canonical_scope(session, tenant_scope):
            accessories = await ProductDAO.get_by_ids(session, accessory_ids, load_image_variants=True)
            projections = [PublicCatalogVisibilityService.project_product(p) for p in accessories if p.is_published and p.product_kind == "accessory"]
        else:
            rows = await PublicCatalogDAO.get_by_ids(session, tenant_scope=tenant_scope, product_ids=accessory_ids, load_image_variants=True, require_catalog_grant=True)
            projections = [PublicCatalogVisibilityService.project_row(row) for row in rows if row[0].product_kind == "accessory"]
        metrics = await ProductReadService.get_supply_metrics_map(session, [p.product for p in projections])
        cards = {}
        for projection in projections:
            product = projection.product
            card = map_product_to_response(projection, supply_metrics=metrics.get(int(product.id), {}))
            cards[int(product.id)] = dict(
                product_id=int(product.id), title=card.title, slug=card.slug,
                accessory_type=_accessory_type(product), main_image=card.main_image,
                price=card.price, old_price=card.old_price, availability_status=card.availability_status,
                delivery_min_days=card.delivery_min_days, delivery_max_days=card.delivery_max_days,
            )
        parent_map = {int(product.id): product for product in products}
        for product_id, values in selected.items():
            result[product_id] = [PublicCatalogAccessory(
                **cards[accessory_id], compatibility_source=source,
                suggested_for_purchase=_suggested_for_purchase(parent_map[product_id], cards[accessory_id]["accessory_type"]),
            ) for accessory_id, source in values if accessory_id in cards]
        return result
