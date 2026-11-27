"""Selected-company Manager shopping catalog over the canonical decision projection."""

from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_shop import (
    BotShopBrowseRequest, BotShopBrowseResponse, BotShopFacetsRequest, BotShopFacetsResponse,
    BotShopFilters, BotShopItem, BotShopProductRequest, BotShopProductResponse,
    BotShopResolveRequest, BotShopResolveResponse,
)
from models.tenancy import TenantScope
from services.bot_api_access import BotUseCaseAccessDeniedError, require_bot_manager
from services.bot_shop_features import facets, feature_page
from services.bot_shop_media import gallery, scoped_products
from services.catalog_decision_projection import CatalogDecisionFilters, CatalogDecisionQueryService
from services.feature_resolver_service import FeatureResolverService
from services.manager_tenant_catalog_reader import product_reader_specifications
from services.yandex_business_feed_text import sanitize_yandex_description


async def _scope(session: AsyncSession, actor: BotShopProductRequest) -> TenantScope:
    context = await require_bot_manager(session, actor.telegram_id)
    if context.selection is None:
        raise BotUseCaseAccessDeniedError("Выберите доступную компанию и витрину")
    if context.selection.context_version != actor.expected_context_version:
        from services.bot_staff_selection_service import context_changed
        raise context_changed()
    return context.selection.scope


def _filters(filters: BotShopFilters) -> CatalogDecisionFilters:
    values = filters.model_dump(exclude={"feature_ids"})
    for key in ("brand_ids", "series_ids", "cooling_btu_classes"):
        values[key] = tuple(values[key])
    if values["availability"] == "all":
        values["availability"] = None
    return CatalogDecisionFilters(**values)


def _item(row: dict, thumbnail_url: str | None) -> BotShopItem:
    values = {key: row[key] for key in BotShopItem.model_fields if key != "thumbnail_url"}
    return BotShopItem(**values, thumbnail_url=thumbnail_url)


async def _items(session: AsyncSession, scope: TenantScope, rows: list[dict]) -> list[BotShopItem]:
    products = await scoped_products(session, scope, [row["id"] for row in rows])
    result = []
    for row in rows:
        product = products.get(row["id"])
        if product is not None:
            images = gallery(product)
            result.append(_item(row, images[0].thumbnail_url if images else None))
    return result


async def browse(session: AsyncSession, request: BotShopBrowseRequest) -> BotShopBrowseResponse:
    scope = await _scope(session, request)
    filters = _filters(request.filters)
    if request.filters.feature_ids:
        ids, total = await feature_page(
            session, scope, filters, feature_ids=request.filters.feature_ids, sort=request.sort,
            direction=request.direction, page=request.page, limit=request.limit,
        )
        meta = {"page": request.page, "limit": request.limit, "total": total,
                "pages": max(1, (total + request.limit - 1) // request.limit)}
        if not ids:
            return BotShopBrowseResponse(items=[], meta=meta)
        rows = await CatalogDecisionQueryService.list_products(
            session, tenant_scope=scope, filters=replace(filters, product_ids=tuple(ids)),
            sort=request.sort, direction=request.direction, page=1, limit=request.limit, include_supplier_details=False,
        )
    else:
        rows = await CatalogDecisionQueryService.list_products(
            session, tenant_scope=scope, filters=filters, sort=request.sort, direction=request.direction,
            page=request.page, limit=request.limit, include_supplier_details=False,
        )
        meta = rows["meta"]
    return BotShopBrowseResponse(items=await _items(session, scope, rows["items"]), meta=meta)


async def list_facets(session: AsyncSession, request: BotShopFacetsRequest) -> BotShopFacetsResponse:
    return await facets(session, await _scope(session, request), _filters(request.filters), request.filters)


async def _by_ids(session: AsyncSession, scope: TenantScope, product_ids: list[int]) -> list[dict]:
    result = await CatalogDecisionQueryService.list_products(
        session, tenant_scope=scope, filters=CatalogDecisionFilters(product_ids=tuple(product_ids)),
        page=1, limit=len(product_ids), sort="title", direction="asc", include_supplier_details=False,
    )
    return result["items"]


async def resolve(session: AsyncSession, request: BotShopResolveRequest) -> BotShopResolveResponse:
    scope = await _scope(session, request)
    rows = await _by_ids(session, scope, request.product_ids)
    items = {item.id: item for item in await _items(session, scope, rows)}
    return BotShopResolveResponse(items=[items[pid] for pid in request.product_ids if pid in items])


async def detail(
    session: AsyncSession, product_id: int, request: BotShopProductRequest,
) -> BotShopProductResponse | None:
    scope = await _scope(session, request)
    rows = await _by_ids(session, scope, [product_id])
    if not rows:
        return None
    product = (await scoped_products(session, scope, [product_id], detail=True)).get(product_id)
    if product is None:
        return None
    images = gallery(product)
    item = _item(rows[0], images[0].thumbnail_url if images else None)
    groups, summary = product_reader_specifications(product)
    resolved = await FeatureResolverService.resolve_for_products(session, [product])
    return BotShopProductResponse(
        **item.model_dump(),
        description=sanitize_yandex_description(product.description, fallback="", limit=len(product.description or "") + 1),
        images=images, summary_fields=summary, specification_groups=groups,
        features=[{"id": f.id, "slug": f.slug, "title": f.name, "category": f.category.name}
                  for f in resolved[product_id]["effective"]],
    )
