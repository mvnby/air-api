"""Read-only sales choices, priced by the existing installation domain."""

import hashlib
import json
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.command_actor import CommandActor
from crud.connector_catalog_selection import ConnectorCatalogSelectionDAO as CatalogDAO
from crud.product import ProductDAO
from schemas_connector_catalog import CatalogProductDetail, CatalogProductInput
from schemas_connector_sales_pricing import (
    SalesInstallationInput, SalesPreviewInput, SalesSelectionInput, SalesSelectionOption, SalesSelectionResult,
)
from schemas_installation_price_book import InstallationInput, InstallationPreviewPayload, InstallationPreviewResponse
from services.connector_catalog_selection_service import ConnectorCatalogSelectionService as Catalog
from services.catalog_accessory_service import CatalogAccessoryService
from services.installation_price_book_service import InstallationPriceBookService as Book
from services.service_estimate_money import exact_money
from services.product_response_mapper import _main_image_public_url
from services.storefront_settings_service import StorefrontSettingsService


class ConnectorSalesPricingService:
    VERSION = "connector-sales-installation-v1"
    ESTIMATE_WARNING = (
        "Это предварительный расчёт оборудования и монтажа по указанным условиям. "
        "Окончательный состав работ и возможность монтажа подтверждаются после проверки объекта. "
        "Наличие не подтверждает дату поставки."
    )

    @staticmethod
    async def verified_actor(session: AsyncSession, actor: CommandActor) -> CommandActor:
        # OAuth carries tenant identity but leaves the canonical-storefront flag
        # unset. Resolve it from the current domain identity, ignoring any
        # previously supplied hint, before native bundle discounts are evaluated.
        unresolved = replace(actor, tenant_scope=replace(actor.tenant_scope, is_canonical_storefront=None))
        canonical = await Catalog._canonical_scope(session, unresolved)
        return replace(actor, tenant_scope=replace(actor.tenant_scope, is_canonical_storefront=canonical))

    @staticmethod
    def missing_inputs(installation: SalesInstallationInput) -> list[str]:
        missing = []
        if installation.route_length_m is None:
            missing.append("installation.route_length_m")
        if installation.holes_by_type is None:
            missing.append("installation.holes_by_type")
        if installation.access == "unknown":
            missing.append("installation.access")
        return missing

    @classmethod
    def preview_payload(cls, product_id: int, installation: SalesInstallationInput) -> InstallationPreviewPayload:
        missing = cls.missing_inputs(installation)
        if missing:
            raise HTTPException(422, {"code": "installation_inputs_required", "missing_inputs": missing})
        if installation.access != "standard" or any(extra.code.startswith("access.") for extra in installation.extras):
            raise HTTPException(422, {"code": "site_assessment_required"})
        return InstallationPreviewPayload(installations=[InstallationInput(
            key="sales", product_id=product_id, work_kind="standard",
            route_length_m=installation.route_length_m,
            holes_by_type=installation.holes_by_type, extras=installation.extras,
        )])

    @classmethod
    async def _require_enabled(cls, session: AsyncSession, actor: CommandActor) -> None:
        if not await StorefrontSettingsService.is_service_enabled(
            session, tenant_scope=actor.tenant_scope, service_kind="installation",
        ):
            raise HTTPException(409, {"code": "installation_disabled"})

    @classmethod
    async def price_option(
        cls, session: AsyncSession, actor: CommandActor, *, product_id: int,
        installation: SalesInstallationInput, accessory_product_ids: list[int] | None = None,
        expected_fingerprint: str | None = None,
    ) -> SalesSelectionOption:
        """Revalidate visibility, compatibility and all current commercial money.

        The authenticated write command owns its transaction and publication lock;
        this function neither commits nor persists a preview or service estimate.
        """
        actor = await cls.verified_actor(session, actor)
        await cls._require_enabled(session, actor)
        payload = cls.preview_payload(product_id, installation)
        canonical = actor.tenant_scope.is_canonical_storefront
        candidates = CatalogDAO.candidates(
            session, tenant_scope=actor.tenant_scope, canonical=canonical, product_id=product_id,
        )
        if (await session.execute(select(candidates.c.product_id))).scalar_one_or_none() is None:
            raise HTTPException(404, "Product unavailable for single-room wall split selection")
        detail = await Catalog.get_product(session, actor, CatalogProductInput(product_id=product_id))
        product_model = await ProductDAO.get_by_id(session, product_id, is_published=True, load_image_variants=True)
        image_url = _main_image_public_url(product_model) if product_model else None
        preview = await Book.preview(session, actor.tenant_scope, payload, persist=False)
        return cls._option(actor, detail, installation, preview, accessory_product_ids or [],
                           image_url=image_url, expected_fingerprint=expected_fingerprint)

    @classmethod
    def _option(
        cls, actor: CommandActor, detail: CatalogProductDetail,
        installation: SalesInstallationInput, preview: InstallationPreviewResponse,
        selected_ids: list[int], *, image_url: str | None = None,
        expected_fingerprint: str | None = None,
    ) -> SalesSelectionOption:
        if len(set(selected_ids)) != len(selected_ids):
            raise HTTPException(422, {"code": "duplicate_accessory"})
        available = {item.product_id: item for item in detail.accessories if item.price > 0}
        if set(selected_ids) - available.keys():
            raise HTTPException(422, {"code": "accessory_unavailable_or_incompatible"})
        selected = [available[key] for key in sorted(selected_ids)]
        if preview.status != "fixed" or preview.total is None:
            raise HTTPException(409, {
                "code": "installation_not_ready", "reason_code": preview.reason_code or preview.status,
            })
        equipment_total = exact_money(detail.unit_price_byn)
        accessory_total = sum((exact_money(item.price) for item in selected), Decimal("0.00"))
        installation_total = exact_money(preview.total)
        # Only public commercial data enters this hash; internal costs, supplier
        # identities and margin calculations never become a connector payload.
        fingerprint_data = {
            "version": cls.VERSION, "tenant_id": actor.tenant_scope.tenant_id,
            "storefront_id": actor.tenant_scope.storefront_id,
            "product": detail.model_dump(mode="json", exclude={"documents", "accessories"}),
            "selected_accessories": [item.model_dump(mode="json") for item in selected],
            "installation_input": installation.model_dump(mode="json"),
            "installation": preview.model_dump(mode="json"),
        }
        fingerprint = hashlib.sha256(json.dumps(
            fingerprint_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        if expected_fingerprint is not None and fingerprint != expected_fingerprint:
            raise HTTPException(409, {"code": "sales_price_changed"})
        return SalesSelectionOption(
            label=detail.brand or "Вариант", product=detail, image_url=image_url,
            compatible_accessories=detail.accessories, selected_accessories=selected,
            equipment_total_byn=equipment_total, accessories_total_byn=accessory_total,
            installation_total_byn=installation_total,
            total_byn=equipment_total + accessory_total + installation_total,
            installation_input=installation, installation=preview,
            calculation_fingerprint=fingerprint, assumptions=installation.assumptions,
        )

    @classmethod
    async def preview(cls, session: AsyncSession, actor: CommandActor, inputs: SalesPreviewInput) -> SalesSelectionOption:
        return await cls.price_option(
            session, actor, product_id=inputs.product_id, installation=inputs.installation,
            accessory_product_ids=inputs.accessory_product_ids, expected_fingerprint=inputs.expected_fingerprint,
        )

    @classmethod
    def _message(cls, options: list[SalesSelectionOption]) -> str:
        lines = ["Варианты для одной комнаты: оборудование и монтаж. Выберите один вариант; суммы альтернатив не складываются."]
        for index, option in enumerate(options, 1):
            lines.extend([
                "", f"{index}. {option.product.title}", Catalog._facts(option.product),
                f"Оборудование: {option.equipment_total_byn:.2f} BYN; выбранные аксессуары: {option.accessories_total_byn:.2f} BYN; "
                f"монтаж: {option.installation_total_byn:.2f} BYN. Итого: {option.total_byn:.2f} BYN.",
                option.installation.customer_text or "",
                option.product.site_url or "Ссылка витрины недоступна.",
            ])
            lines.extend(option.installation_input.assumptions)
        lines.extend(["", cls.ESTIMATE_WARNING])
        return "\n".join(lines)

    @classmethod
    async def select(cls, session: AsyncSession, actor: CommandActor, inputs: SalesSelectionInput) -> SalesSelectionResult:
        checked_at = datetime.now(timezone.utc)
        # Resolve the storefront before returning any readiness information.
        actor = await cls.verified_actor(session, actor)
        canonical = actor.tenant_scope.is_canonical_storefront
        missing = cls.missing_inputs(inputs.installation)
        if missing:
            return SalesSelectionResult(
                status="needs_input", checked_at=checked_at, missing_inputs=missing,
                message_text="Для полного расчёта нужны длина трассы, отверстия по типам и условия доступа к месту монтажа.",
            )
        if inputs.installation.access != "standard" or any(
            extra.code.startswith("access.") for extra in inputs.installation.extras
        ):
            return SalesSelectionResult(status="not_ready", checked_at=checked_at,
                excluded_reasons={"site_assessment_required": 1},
                message_text="Условия доступа требуют оценки объекта; полный бюджет пока не подтверждён.")
        try:
            await cls._require_enabled(session, actor)
        except HTTPException as exc:
            if not isinstance(exc.detail, dict) or exc.detail.get("code") != "installation_disabled":
                raise
            return SalesSelectionResult(status="not_ready", checked_at=checked_at,
                excluded_reasons={"installation_disabled": 1}, message_text="Монтаж в текущей витрине отключён.")
        if await Book.latest(session, actor.tenant_scope) is None:
            return SalesSelectionResult(status="not_ready", checked_at=checked_at,
                excluded_reasons={"price_book_not_published": 1},
                message_text="Нет опубликованного прайс-листа монтажа текущей компании; полный бюджет неизвестен.")
        if (inputs.query is not None and not inputs.query.strip()) or any(not slug.strip() for slug in inputs.brand_slugs):
            raise HTTPException(422, "Catalog constraints cannot be blank")
        candidates = CatalogDAO.candidates(
            session, tenant_scope=actor.tenant_scope, canonical=canonical,
            cooling_btu_class=inputs.cooling_btu_class, area_m2=inputs.area_m2,
            area_ceiling=Catalog._area_ceiling(inputs),
            max_unit_price=int(inputs.budget_byn) if inputs.budget_byn is not None else None,
            is_inverter=inputs.is_inverter, heating_min_c=inputs.heating_min_c,
            has_wifi=inputs.has_wifi, brand_slugs=inputs.brand_slugs,
            query=inputs.query, in_stock_only=inputs.in_stock_only,
        )
        rows = (await session.execute(select(candidates).order_by(*CatalogDAO._ranking(candidates)))).mappings().all()
        product_ids = {row["product_id"] for row in rows}
        context = await Book.read_context(session, actor.tenant_scope, product_ids)
        # Variant and compatibility reads are batched. Comparison cards omit
        # external documents; explicit preview still returns the detailed card.
        products = {product.id: product for product in await ProductDAO.get_by_ids(
            session, list(product_ids), load_image_variants=True,
        ) if product.id in context.products}
        accessories = await CatalogAccessoryService.resolve_public(
            session, list(products.values()), tenant_scope=actor.tenant_scope,
        )
        site_base = await Catalog._site_base(session, actor, canonical)
        priced = []
        reasons = Counter()
        for row in rows:
            product_id = row["product_id"]
            product_model = products.get(product_id)
            if product_model is None:
                reasons["product_not_visible"] += 1
                continue
            detail = CatalogProductDetail(
                **Catalog._product(row, site_base).model_dump(),
                accessories=accessories.get(product_id, []),
            )
            try:
                preview = await Book.preview(
                    session, actor.tenant_scope, cls.preview_payload(product_id, inputs.installation),
                    persist=False, _read_context=context,
                )
                option = cls._option(
                    actor, detail, inputs.installation, preview, inputs.accessory_product_ids,
                    image_url=_main_image_public_url(product_model),
                )
            except HTTPException as exc:
                if isinstance(exc.detail, dict) and exc.detail.get("code") in {
                    "installation_not_ready", "accessory_unavailable_or_incompatible",
                }:
                    reasons[exc.detail.get("reason_code") or exc.detail["code"]] += 1
                    continue
                raise
            if inputs.budget_byn is not None and option.total_byn > inputs.budget_byn:
                reasons["over_full_budget"] += 1
                continue
            priced.append(option)
        # Rank only after every constraint and the complete installation price
        # have been evaluated; cheap equipment with an expensive install cannot
        # consume a valid alternative's place.
        if inputs.budget_byn is not None:
            distinct = {}
            brand_ids = {row["product_id"]: row["brand_id"] for row in rows}
            for option in priced:
                key = brand_ids[option.product.product_id]
                distinct.setdefault(key, option)
            options = list(distinct.values())[:3]
        else:
            levels = {}
            for option in sorted(priced, key=lambda item: (item.total_byn, item.product.product_id)):
                levels.setdefault(option.total_byn, option)
            values = list(levels.values())
            indices = sorted({0, (len(values) - 1) // 2, len(values) - 1}) if values else []
            options = [values[index] for index in indices]
        for index, option in enumerate(options, 1):
            option.label = f"Вариант {index}"
        warnings = [cls.ESTIMATE_WARNING]
        if len(options) < 3:
            warnings.append(f"Подходящих альтернатив: {len(options)}. Требования не изменялись.")
        if inputs.budget_byn is None:
            warnings.append("Уровни полной цены не подтверждают различия качества оборудования.")
        status = "ready" if options else ("not_ready" if reasons and "over_full_budget" not in reasons else "no_matches")
        return SalesSelectionResult(
            status=status, checked_at=checked_at, options=options,
            matching_products=len(rows), excluded_reasons=dict(reasons), warnings=warnings,
            message_text=cls._message(options) if options else "По всем заданным условиям вариантов с полным расчётом не найдено. Требования не изменялись.",
        )
