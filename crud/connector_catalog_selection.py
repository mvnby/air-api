"""Read-only public catalog projection and global selection queries."""

from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.product import ProductDAO
from crud.public_catalog import PublicCatalogDAO
from crud.public_taxonomy import PublicTaxonomyDAO
from models import Brand, Product, ProductSeries, ProductTagLink, Tag, TagGroup, TenantOffer
from models.supplier import ProductLocalStock, ProductSupplierMapping, Supplier, SupplierOffer
from models.tenancy import Storefront, StorefrontDomain, TenantScope
from services.catalog_decision_projection import CatalogDecisionFilters, CatalogDecisionQueryService
from services.catalog_form_factor import indoor_form_factor_expr


class ConnectorCatalogSelectionDAO:
    @staticmethod
    def _stock():
        # Only positive, active quantities count. No supplier prices or costs
        # enter this projection, including its intermediate SQL columns.
        supplier = (
            select(
                ProductSupplierMapping.product_id.label("product_id"),
                func.sum(SupplierOffer.qty).label("quantity"),
            )
            .join(SupplierOffer, and_(
                SupplierOffer.supplier_id == ProductSupplierMapping.supplier_id,
                SupplierOffer.external_id == ProductSupplierMapping.external_id,
            ))
            .join(Supplier, Supplier.id == SupplierOffer.supplier_id)
            .where(
                ProductSupplierMapping.is_active.is_(True),
                SupplierOffer.is_active.is_(True),
                Supplier.is_active.is_(True),
                SupplierOffer.qty > 0,
            )
            .group_by(ProductSupplierMapping.product_id)
            .cte("connector_supplier_stock")
        )
        local = (
            select(
                ProductLocalStock.product_id.label("product_id"),
                func.sum(ProductLocalStock.qty).label("quantity"),
            )
            .where(ProductLocalStock.qty > 0)
            .group_by(ProductLocalStock.product_id)
            .cte("connector_local_stock")
        )
        return supplier, local

    @classmethod
    def candidates(
        cls, session: AsyncSession, *, tenant_scope: TenantScope,
        canonical: bool, quantity: int = 1, cooling_btu_class: int | None = None,
        area_m2: int | None = None, area_ceiling: float | None = None,
        max_unit_price: int | None = None, is_inverter: bool | None = None,
        heating_min_c: int | None = None, has_wifi: bool | None = None,
        brand_slugs: list[str] | None = None, query: str | None = None,
        in_stock_only: bool = False, product_id: int | None = None,
    ):
        decision = CatalogDecisionQueryService
        area = decision._json_float(session, "area_m2")
        nominal = func.coalesce(Product.power_cooling, decision._json_float(session, "capacity_cooling_kw"))
        heating = func.coalesce(
            decision._json_float_path(session, "__typed_specs", "temp_range_heat", "min"),
            decision._json_float(session, "__filter_min_heat"),
        )
        wifi_state = ProductDAO.wifi_state_expr(session)
        legacy_wifi = ProductDAO._json_text_expr(session, "__filter_wifi")
        wifi = case(
            (wifi_state.in_(("builtin", "ready", "none")), wifi_state),
            (and_(wifi_state.is_(None), legacy_wifi.in_(("false", "0"))), "none"),
            else_="unknown",
        )
        supplier, local = cls._stock()
        enough_stock = (func.coalesce(supplier.c.quantity, 0) + func.coalesce(local.c.quantity, 0)) >= quantity
        price = Product.price if canonical else TenantOffer.price
        favorite = exists(
            select(ProductTagLink.product_id)
            .join(Tag, Tag.id == ProductTagLink.tag_id)
            .join(TagGroup, TagGroup.id == Tag.group_id)
            .where(
                ProductTagLink.product_id == Product.id,
                Tag.slug == "manager-favorite",
                *PublicTaxonomyDAO.public_tag_conditions(),
            )
        )
        statement = (
            select(
                Product.id.label("product_id"), Product.title, Product.slug,
                Brand.id.label("brand_id"), Brand.title.label("brand"),
                ProductSeries.title.label("series"), price.label("unit_price_byn"),
                Product.is_inverter, nominal.label("cooling_power_kw"),
                area.label("area_m2"), heating.label("heating_min_c"), wifi.label("wifi"),
                enough_stock.label("enough_stock"),
                (area - area_m2 if area_m2 is not None else 0 * price).label("area_fit"),
                favorite.label("favorite"), func.coalesce(Brand.sort_order, 999).label("brand_priority"),
            )
            .select_from(Product)
            .outerjoin(Brand, and_(Brand.id == Product.brand_id, Brand.is_published.is_(True)))
            .outerjoin(ProductSeries, and_(
                ProductSeries.id == Product.series_id,
                ProductSeries.brand_id == Product.brand_id,
                ProductSeries.is_published.is_(True),
            ))
            .outerjoin(supplier, supplier.c.product_id == Product.id)
            .outerjoin(local, local.c.product_id == Product.id)
            .where(decision._complete_split_condition(session), indoor_form_factor_expr(session) == "wall", price > 0)
        )
        statement = ProductDAO._apply_common_filters(session, statement, is_inverter=is_inverter, is_published=True)
        statement = PublicTaxonomyDAO.apply_published_brand_filter(statement, brand_slugs)
        if not canonical:
            statement = statement.join(TenantOffer, TenantOffer.product_id == Product.id).where(
                *PublicCatalogDAO.visible_offer_conditions(tenant_scope, require_catalog_grant=True),
            )
        if cooling_btu_class is not None:
            statement = statement.where(*decision._conditions(
                session, CatalogDecisionFilters(cooling_btu_classes=(cooling_btu_class,)),
                availability=enough_stock, retail=price, cooling_nominal=nominal,
                cooling_min=nominal, cooling_max=nominal, area=area, heating_min=heating,
            ))
        if area_m2 is not None:
            statement = statement.where(area >= area_m2)
        if area_ceiling is not None:
            statement = statement.where(area <= area_ceiling)
        if max_unit_price is not None:
            statement = statement.where(price <= max_unit_price)
        if heating_min_c is not None:
            statement = statement.where(heating <= heating_min_c)
        if has_wifi is not None:
            # A legacy normalized capability boolean cannot tell whether Wi-Fi
            # is built in or requires a module. It filters capability without
            # fabricating either factual state in the public result.
            statement = statement.where(or_(
                wifi.in_(("builtin", "ready")),
                and_(wifi_state.is_(None), legacy_wifi.in_(("true", "1"))),
            ) if has_wifi else wifi == "none")
        if in_stock_only:
            statement = statement.where(enough_stock)
        if product_id is not None:
            statement = statement.where(Product.id == product_id)
        # Literal AND-token search observes only public taxonomy, including
        # canonical brands/series. Private tags cannot produce a match.
        for token in (query or "").strip().split():
            pattern = "%" + token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            tag_match = exists(
                select(ProductTagLink.product_id)
                .join(Tag, Tag.id == ProductTagLink.tag_id)
                .join(TagGroup, TagGroup.id == Tag.group_id)
                .where(ProductTagLink.product_id == Product.id, Tag.title.ilike(pattern, escape="\\"), *PublicTaxonomyDAO.public_tag_conditions())
            )
            statement = statement.where(or_(
                Product.title.ilike(pattern, escape="\\"), Product.slug.ilike(pattern, escape="\\"),
                Brand.title.ilike(pattern, escape="\\"), ProductSeries.title.ilike(pattern, escape="\\"), tag_match,
            ))
        return statement.cte("connector_catalog_candidates")

    @staticmethod
    async def counts(session: AsyncSession, candidates) -> tuple[int, int]:
        row = (await session.execute(select(func.count(), func.count(func.distinct(candidates.c.brand_id))).select_from(candidates))).one()
        return int(row[0]), int(row[1])

    @staticmethod
    def _ranking(candidates):
        return (
            candidates.c.enough_stock.desc(), candidates.c.area_fit.asc().nullslast(),
            candidates.c.favorite.desc(), candidates.c.brand_priority.asc(),
            candidates.c.unit_price_byn.asc(), candidates.c.product_id.asc(),
        )

    @classmethod
    async def budget_choices(cls, session: AsyncSession, candidates, *, allow_unbranded: bool):
        # Each brand's winner is computed over the complete filtered catalog,
        # before the outer limit; NULL is never counted as an extra brand.
        winners = select(
            *candidates.c,
            func.row_number().over(partition_by=candidates.c.brand_id, order_by=cls._ranking(candidates)).label("brand_rank"),
        ).cte("connector_brand_winners")
        statement = select(winners).where(winners.c.brand_rank == 1)
        if not allow_unbranded:
            statement = statement.where(winners.c.brand_id.is_not(None))
        return list((await session.execute(statement.order_by(*cls._ranking(winners)).limit(3))).mappings().all())

    @classmethod
    async def price_tiers(cls, session: AsyncSession, candidates):
        # Models with the same public price form one level. Choose their best
        # representative before ranking distinct levels over the full catalog,
        # so a popular low price cannot also consume the middle-price choice.
        models = select(
            *candidates.c,
            func.row_number().over(
                partition_by=candidates.c.unit_price_byn,
                order_by=cls._ranking(candidates),
            ).label("price_model_rank"),
        ).cte("connector_price_models")
        levels = select(models).where(models.c.price_model_rank == 1).cte("connector_price_levels")
        ranked = select(
            *levels.c,
            func.row_number().over(order_by=levels.c.unit_price_byn.asc()).label("price_rank"),
            func.count().over().label("price_count"),
        ).cte("connector_price_tiers")
        statement = select(ranked).where(or_(
            ranked.c.price_rank == 1,
            ranked.c.price_rank == func.floor((ranked.c.price_count + 1) / 2.0),
            ranked.c.price_rank == ranked.c.price_count,
        )).order_by(ranked.c.price_rank.asc())
        return list((await session.execute(statement)).mappings().all())

    @staticmethod
    async def verified_domains(session: AsyncSession, tenant_scope: TenantScope) -> list[str]:
        return list((await session.execute(
            select(StorefrontDomain.hostname)
            .join(Storefront, Storefront.id == StorefrontDomain.storefront_id)
            .where(
                Storefront.tenant_id == tenant_scope.tenant_id,
                Storefront.id == tenant_scope.storefront_id, Storefront.status == "active",
                StorefrontDomain.status == "active", StorefrontDomain.verified_at.is_not(None),
            )
            .order_by(StorefrontDomain.is_primary.desc(), StorefrontDomain.id.asc())
        )).scalars().all())

    @staticmethod
    async def storefront_currency(session: AsyncSession, tenant_scope: TenantScope) -> str | None:
        return (await session.execute(select(Storefront.currency).where(
            Storefront.tenant_id == tenant_scope.tenant_id,
            Storefront.id == tenant_scope.storefront_id,
            Storefront.status == "active",
        ))).scalar_one_or_none()
