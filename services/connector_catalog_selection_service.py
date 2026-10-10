"""Customer-ready factual choices from the current public storefront catalog."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.command_actor import CommandActor
from core.config import settings
from crud.connector_catalog_selection import ConnectorCatalogSelectionDAO
from models.product_constants import BTU_MAPPING
from schemas_connector_catalog import (
    CatalogProduct, CatalogProductInput, CatalogSelectionInput,
    CatalogSelectionOption, CatalogSelectionResult,
)
from services.catalog_purge_service import build_catalog_purge_paths
from services.public_catalog_visibility_service import PublicCatalogVisibilityService
from services.storefront_context_service import InvalidStorefrontHostError, StorefrontContextService


class ConnectorCatalogSelectionService:
    @staticmethod
    async def _canonical_scope(session: AsyncSession, actor: CommandActor) -> bool:
        currency = await ConnectorCatalogSelectionDAO.storefront_currency(session, actor.tenant_scope)
        if currency is None:
            raise HTTPException(status_code=404, detail="Storefront unavailable")
        if currency != "BYN":
            raise HTTPException(status_code=409, detail="Catalog selection supports BYN storefronts only")
        return await PublicCatalogVisibilityService.is_canonical_scope(session, actor.tenant_scope)

    @staticmethod
    def _area_ceiling(inputs: CatalogSelectionInput) -> float | None:
        if inputs.area_m2 is None or inputs.cooling_btu_class is not None:
            return None
        # Room-area requests stay in the smallest supported coverage band;
        # higher-priced oversized equipment must not become a "premium" pick.
        ceilings = sorted({ranges["area"][1] for ranges in BTU_MAPPING.values()})
        return next((ceiling for ceiling in ceilings if ceiling >= inputs.area_m2), 0)

    @staticmethod
    async def _site_base(session: AsyncSession, actor: CommandActor, canonical: bool) -> str | None:
        if canonical:
            return settings.PUBLIC_SITE_URL.rstrip("/")
        for raw_hostname in await ConnectorCatalogSelectionDAO.verified_domains(session, actor.tenant_scope):
            try:
                hostname = StorefrontContextService.normalize_hostname(raw_hostname)
            except InvalidStorefrontHostError:
                continue
            return "https://" + hostname
        return None

    @staticmethod
    def _product(row, site_base: str | None) -> CatalogProduct:
        # Share the existing encoded public product route with catalog
        # freshness, while keeping the storefront origin separately scoped.
        product_path = next((
            path for path in build_catalog_purge_paths(product_slugs=[row["slug"]])
            if path.startswith("/product/")
        ), None)
        return CatalogProduct(
            product_id=row["product_id"], title=row["title"], brand=row["brand"], series=row["series"],
            unit_price_byn=row["unit_price_byn"],
            site_url=f"{site_base}{product_path}" if site_base and product_path else None,
            is_inverter=row["is_inverter"], cooling_power_kw=row["cooling_power_kw"],
            area_m2=row["area_m2"], heating_min_c=row["heating_min_c"], wifi=row["wifi"],
            availability="in_stock" if row["enough_stock"] else "on_request",
        )

    @staticmethod
    def _facts(product: CatalogProduct) -> str:
        features = ["инвертор" if product.is_inverter else "без инвертора"]
        if product.cooling_power_kw is not None:
            features.append(f"охлаждение {product.cooling_power_kw:g} кВт")
        if product.area_m2 is not None:
            features.append(f"площадь до {product.area_m2:g} м²")
        if product.heating_min_c is not None:
            features.append(f"обогрев до {product.heating_min_c:g} °C")
        features.append({
            "builtin": "Wi-Fi встроен", "ready": "Wi-Fi: подготовка под модуль",
            "none": "без Wi-Fi", "unknown": "Wi-Fi не указан",
        }[product.wifi])
        return "; ".join(features)

    @classmethod
    def _message(cls, options: list[CatalogSelectionOption], warnings: list[str], checked_at: datetime) -> str:
        local_checked_at = checked_at.astimezone(ZoneInfo("Europe/Minsk"))
        lines = [f"Варианты кондиционеров. Цены и наличие проверены {local_checked_at:%d.%m.%Y %H:%M} (Минск)."]
        if options:
            lines.append("Выберите один вариант; это альтернативы, их суммы не складываются.")
        else:
            lines.append("По указанным условиям подходящих моделей не найдено. Условия не изменялись.")
        for index, option in enumerate(options, 1):
            product = option.product
            taxonomy = ", ".join(value for value in (product.brand, product.series) if value)
            lines.extend([
                "",
                f"{index}. {option.label}: {product.title}" + (f" ({taxonomy})" if taxonomy else ""),
                cls._facts(product),
                f"{product.unit_price_byn} BYN за шт. × {option.quantity} шт. = {option.equipment_total_byn} BYN за оборудование.",
                "В наличии для указанного количества." if product.availability == "in_stock" else "Наличие и срок поставки уточняются.",
                product.site_url or "Ссылка на сайт этой витрины недоступна.",
            ])
        lines.extend(["", "Монтаж не включён в цену оборудования и рассчитывается отдельно."])
        if warnings:
            lines.extend(["", *warnings])
        return "\n".join(lines)

    @classmethod
    async def select(cls, session: AsyncSession, actor: CommandActor, inputs: CatalogSelectionInput) -> CatalogSelectionResult:
        if inputs.query is not None and not inputs.query.strip():
            raise HTTPException(status_code=422, detail="Search query cannot be blank")
        if any(not slug.strip() for slug in inputs.brand_slugs):
            raise HTTPException(status_code=422, detail="Brand slugs cannot be blank")
        canonical = await cls._canonical_scope(session, actor)
        unit_budget = inputs.budget_byn
        if unit_budget is not None and inputs.budget_scope == "total":
            unit_budget //= inputs.quantity
        area_ceiling = cls._area_ceiling(inputs)
        candidates = ConnectorCatalogSelectionDAO.candidates(
            session, tenant_scope=actor.tenant_scope, canonical=canonical, quantity=inputs.quantity,
            cooling_btu_class=inputs.cooling_btu_class, area_m2=inputs.area_m2, area_ceiling=area_ceiling,
            max_unit_price=unit_budget, is_inverter=inputs.is_inverter, heating_min_c=inputs.heating_min_c,
            has_wifi=inputs.has_wifi, brand_slugs=inputs.brand_slugs, query=inputs.query,
            in_stock_only=inputs.in_stock_only,
        )
        matching, brands = await ConnectorCatalogSelectionDAO.counts(session, candidates)
        mode = "budget_brands" if inputs.budget_byn is not None else "price_tiers"
        rows = (
            await ConnectorCatalogSelectionDAO.budget_choices(session, candidates, allow_unbranded=brands == 0)
            if mode == "budget_brands" else await ConnectorCatalogSelectionDAO.price_tiers(session, candidates)
        )
        site_base = await cls._site_base(session, actor, canonical)
        warnings = []
        customer_warnings = []
        if area_ceiling == 0:
            warnings.append("Для указанной площади нет стандартного диапазона подбора; требуется уточнить расчёт мощности.")
            customer_warnings.append(warnings[-1])
        if len(rows) < 3:
            warnings.append(f"По заданным условиям доступно вариантов: {len(rows)}. Ограничения не ослаблялись.")
            customer_warnings.append(f"По указанным условиям найдено вариантов: {len(rows)}.")
        if mode == "budget_brands" and brands < 3:
            warnings.append(f"Подходящих опубликованных брендов: {brands}; варианты без указанного бренда не считаются отдельными брендами.")
        if site_base is None:
            warnings.append("У этой витрины нет доступного подтверждённого домена; ссылки на товары недоступны.")
        if mode == "price_tiers":
            warnings.append("Бюджетный, средний и премиальный варианты обозначают уровень цены; более высокая цена не подтверждает более высокое качество.")
            if len(rows) < 3 and matching > len(rows):
                warnings.append(f"Подходящих моделей: {matching}; различных публичных цен: {len(rows)}. На каждый ценовой уровень выбран один вариант.")
        options = []
        for index, row in enumerate(rows):
            product = cls._product(row, site_base)
            if mode == "budget_brands":
                label = product.brand or "Бренд не указан"
                reason = "Соответствует условиям и бюджету; приоритет — наличие нужного количества, подходящая площадь и рекомендация каталога."
            else:
                labels = ["Бюджетный", "Средний", "Премиальный"] if len(rows) == 3 else ["Бюджетный", "Премиальный"]
                label = labels[index] if len(rows) > 1 else "Единственный ценовой уровень"
                reason = "Соответствует условиям; выбран по уровню публичной цены среди всех подходящих моделей."
            options.append(CatalogSelectionOption(
                label=label, reason=reason, product=product, quantity=inputs.quantity,
                equipment_total_byn=product.unit_price_byn * inputs.quantity,
            ))
        checked_at = datetime.now(timezone.utc)
        return CatalogSelectionResult(
            mode=mode, checked_at=checked_at, options=options, matching_products=matching,
            distinct_brands=brands, warnings=warnings,
            message_text=cls._message(options, customer_warnings, checked_at),
        )

    @classmethod
    async def get_product(cls, session: AsyncSession, actor: CommandActor, inputs: CatalogProductInput) -> CatalogProduct:
        canonical = await cls._canonical_scope(session, actor)
        candidates = ConnectorCatalogSelectionDAO.candidates(
            session, tenant_scope=actor.tenant_scope, canonical=canonical, product_id=inputs.product_id,
        )
        row = (await session.execute(select(candidates))).mappings().one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Product unavailable in this storefront catalog")
        return cls._product(row, await cls._site_base(session, actor, canonical))
