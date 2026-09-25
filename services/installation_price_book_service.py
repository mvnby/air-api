"""Publish validated installation tariffs and preview only immutable revisions."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import InstallationPriceBook, InstallationRate, Product, ServiceTariff, ServiceTariffRule
from models.tenancy import TenantScope
from schemas import ManagerInstallEstimateCalculatePayload, ManagerTariffServiceKind
from schemas_installation_price_book import (
    InstallationComponent, InstallationMatcher, InstallationPreviewPayload,
    InstallationPreviewResponse, InstallationPublishResponse, InstallationResolveResponse,
    InstallationTarget, TypedInstallationProfile,
    InstallationLegacyComparisonResponse, InstallationLegacyComparisonRow,
    InstallationLegacyCandidate,
    InstallationAppliedDiscount,
    InstallationMeasuredWork, InstallationSelectedWork, InstallationWorkSummary,
)
from services.installation_product_profile import _spec_value
from services.product_collection_catalog_access import ProductCollectionCatalogAccess
from services.service_estimate_money import allocate_discount, exact_money, money
from services.service_estimate_service import ServiceEstimateService
from services.spec_registry import canonical_indoor_type_slug
from services.spec_normalizer import clean_value
from services.product_kind_service import ProductKindService
from services.tariffs_service import TariffsService
from services.service_catalog_scope import service_catalog_scope_clause
from services.installation_preview_receipt_service import InstallationPreviewReceiptService


class InstallationPriceBookService:
    RESOLVER_VERSION = "installation-book-v1"
    _WORK_LABELS = {
        "wall": "Монтаж настенного комплекта",
        "cassette": "Монтаж кассетного комплекта",
        "duct": "Монтаж канального комплекта",
        "floor_ceiling": "Монтаж напольно-потолочного комплекта",
        "column": "Монтаж колонного комплекта",
        "console": "Монтаж консольного комплекта",
    }
    _EXTRA_LABELS = {
        "pump.supply": "Поставка насоса",
        "pump.install": "Монтаж насоса",
        "pump.package": "Дренажный насос с поставкой и монтажом",
        "access.scaffold": "Леса",
        "access.lift": "Вышка (не менее 4 часов)",
        "chase.extra_m": "Штробление",
    }
    _COMPONENT_RULES = {
        "route.extra_m": ("per_meter_over_included", "м", False),
        "pump.supply": ("per_unit_manual", "шт", True),
        "pump.install": ("per_unit_manual", "шт", True),
        "pump.package": ("per_unit_manual", "шт", True),
        "access.scaffold": ("fixed_once", "шт", True),
        "access.lift": ("fixed_once", "шт", True),
        "chase.extra_m": ("per_unit_manual", "м", True),
        "discount.equipment_bundle": ("fixed_once", "шт", False),
    }

    @staticmethod
    def _pipe(value: str) -> str:
        value = value.strip()
        if "/" in value and '"' not in value:
            value += '"'
        return str(clean_value("pipe_liquid", value))

    @staticmethod
    def _single_quantity(value: object, *, kind: str) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        raw = str(value).strip().lower().replace(",", ".")
        unit = r"(?:квт|kw)" if kind == "power" else r"(?:кг|kg)"
        match = re.fullmatch(rf"(\d+(?:\.\d+)?)\s*{unit}?", raw)
        if match is None:
            return None
        number = Decimal(match.group(1))
        if not number.is_finite() or number <= 0 or number > (1000 if kind == "power" else 10000):
            return None
        return number

    @classmethod
    async def legacy_comparison(cls, session: AsyncSession, scope: TenantScope, *, offset: int, limit: int) -> InstallationLegacyComparisonResponse:
        """Compare legacy rates with current typed drafts, without copying or publishing prices."""
        book = await cls.latest(session, scope)
        drafts = await TariffsService.get_all_tariffs(
            session, service_kind=ManagerTariffServiceKind.installation, include_inactive=False, tenant_scope=scope,
        )
        candidates: list[InstallationLegacyCandidate] = []
        for tariff in drafts:
            if not tariff.installation_match or not tariff.installation_code:
                continue
            try:
                matcher = InstallationMatcher.model_validate(tariff.installation_match)
            except ValidationError:
                continue  # Publication reports the invalid draft with its precise error.
            route_rule = next((rule for rule in tariff.rules if rule.is_active and rule.component_code == "route.extra_m"), None)
            candidates.append(InstallationLegacyCandidate(
                tariff_code=tariff.installation_code, matcher=matcher,
                mode=tariff.installation_price_mode,
                base_price=Decimal(str(tariff.base_price)),
                route_extra_price=Decimal(str(route_rule.unit_price)) if route_rule else None,
            ))
        rates = (await session.execute(select(InstallationRate).where(
            service_catalog_scope_clause(InstallationRate, scope)
        ).order_by(InstallationRate.id).offset(offset).limit(limit))).scalars().all()
        category_map = {"wall": "wall", "cassette": "cassette", "duct": "duct",
                        "ceiling": "floor_ceiling", "floor_ceiling": "floor_ceiling", "column": "column"}
        items: list[InstallationLegacyComparisonRow] = []
        for rate in rates:
            indoor_type = category_map.get((rate.category or "").strip().lower().replace("-", "_"))
            possible = [candidate for candidate in candidates if indoor_type and candidate.matcher.indoor_type == indoor_type]
            same_price = [candidate for candidate in possible
                          if candidate.base_price == Decimal(rate.base_price)
                          and candidate.route_extra_price == Decimal(rate.extra_pipe_price)]
            status = ("price_equal_review_required" if same_price else
                      "price_diff_review_required" if possible else "unmapped_review_required")
            items.append(InstallationLegacyComparisonRow(
                legacy_rate_id=rate.id, legacy_category=rate.category, legacy_power_range=rate.power_range,
                legacy_base_price=Decimal(rate.base_price), legacy_route_extra_price=Decimal(rate.extra_pipe_price),
                candidates=possible, status=status,
            ))
        return InstallationLegacyComparisonResponse(price_book_revision=book.revision if book else None, items=items)

    @staticmethod
    def _json(data: object) -> str:
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    @classmethod
    def _fingerprint(cls, data: object) -> str:
        return hashlib.sha256(cls._json(data).encode()).hexdigest()

    @staticmethod
    def _scope_ref(scope: TenantScope) -> str:
        return hashlib.sha256(f"{scope.tenant_id}:{scope.storefront_id}".encode()).hexdigest()[:24]

    @staticmethod
    def _bad(code: str, message: str) -> HTTPException:
        return HTTPException(status_code=422, detail={"code": code, "message": message})

    @staticmethod
    def _range_overlap(a_min: Decimal | None, a_max: Decimal | None, b_min: Decimal | None, b_max: Decimal | None,
                       *, a_min_inclusive: bool = True, a_max_inclusive: bool = True,
                       b_min_inclusive: bool = True, b_max_inclusive: bool = True) -> bool:
        if a_max is not None and b_min is not None and (a_max < b_min or
                (a_max == b_min and not (a_max_inclusive and b_min_inclusive))):
            return False
        if b_max is not None and a_min is not None and (b_max < a_min or
                (b_max == a_min and not (b_max_inclusive and a_min_inclusive))):
            return False
        return True

    @staticmethod
    def _specificity(match: InstallationMatcher) -> int:
        return sum(value is not None for value in (
            match.capacity_min_kw, match.capacity_max_kw, match.pipe_liquid,
            match.weight_source, match.weight_min_kg, match.weight_max_kg,
        ))

    @classmethod
    def _component_signature(cls, code: str) -> tuple[str, str, bool] | None:
        if re.fullmatch(r"hole\.[a-z][a-z0-9_]*\.extra", code):
            return ("per_hole_manual", "шт", False)
        return cls._COMPONENT_RULES.get(code)

    @classmethod
    def _work_label(cls, entry: dict[str, Any]) -> str:
        matcher = InstallationMatcher.model_validate(entry["match"])
        if matcher.product_kind == "multi_split_system":
            return "Монтаж мультисплит-системы"
        return cls._WORK_LABELS[matcher.indoor_type]

    @staticmethod
    def _quantity_text(value: Decimal) -> str:
        return format(value.normalize(), "f").replace(".", ",")

    @classmethod
    def _measured_label(cls, code: str) -> str:
        if code == "route.length_m":
            return "Трасса"
        if code == "hole.diamond":
            return "Алмазные отверстия"
        if code == "hole.through_thin":
            return "Проходы через стену до 20 см"
        if code == "hole.through_thick":
            return "Проходы через стену свыше 20 до 80 см"
        if code == "hole.through_over_80":
            return "Проходы через стену свыше 80 см"
        return f"Отверстия типа {code.removeprefix('hole.')}"

    @classmethod
    def _summary_text(cls, summary: InstallationWorkSummary) -> str:
        parts = [summary.work_label]
        for measured in summary.measured:
            if measured.actual == 0:
                continue
            actual = cls._quantity_text(measured.actual)
            included = cls._quantity_text(measured.included)
            detail = f"{measured.label.lower()} {actual} {measured.unit} (включено {included} {measured.unit}"
            if measured.extra:
                detail += f", дополнительно {cls._quantity_text(measured.extra)} {measured.unit}"
            parts.append(detail + ")")
        for selected in summary.selected_extras:
            detail = selected.label.lower()
            if selected.quantity != 1:
                detail += f" {cls._quantity_text(selected.quantity)} {selected.unit}"
            parts.append(detail)
        return f"Установка {summary.display_label or summary.installation_key}: " + ", ".join(parts)

    @classmethod
    def _overlap(cls, a: InstallationMatcher, b: InstallationMatcher) -> bool:
        if a.indoor_type != b.indoor_type or a.product_kind != b.product_kind or a.work_kind != b.work_kind:
            return False
        if a.pipe_liquid and b.pipe_liquid and (cls._pipe(a.pipe_liquid), cls._pipe(a.pipe_gas)) != (cls._pipe(b.pipe_liquid), cls._pipe(b.pipe_gas)):
            return False
        if not cls._range_overlap(a.capacity_min_kw, a.capacity_max_kw, b.capacity_min_kw, b.capacity_max_kw,
                a_min_inclusive=a.capacity_min_inclusive, a_max_inclusive=a.capacity_max_inclusive,
                b_min_inclusive=b.capacity_min_inclusive, b_max_inclusive=b.capacity_max_inclusive):
            return False
        if a.weight_source and b.weight_source and a.weight_source == b.weight_source:
            return cls._range_overlap(a.weight_min_kg, a.weight_max_kg, b.weight_min_kg, b.weight_max_kg)
        return True

    @classmethod
    def _validate_entries(cls, entries: list[dict[str, Any]]) -> None:
        if not entries:
            raise cls._bad("empty_price_book", "No typed installation tariffs to publish")
        codes: set[str] = set()
        site_prices: dict[str, str] = {}
        component_signatures: dict[str, tuple[str, str]] = {}
        for entry in entries:
            code = entry["code"]
            if code in codes:
                raise cls._bad("duplicate_tariff_code", f"Duplicate tariff code: {code}")
            codes.add(code)
            match = InstallationMatcher.model_validate(entry["match"])
            if match.weight_source in {"weight_indoor_package", "weight_outdoor_package"}:
                raise cls._bad("packed_weight_requires_transport_rule", f"{code}: packaged weight is reserved for transport")
            if entry["mode"] in {"fixed", "from"} and (
                (match.match_strategy == "strict" and match.pipe_liquid is None) or
                (match.match_strategy == "capacity_only" and
                 match.capacity_min_kw is None and match.capacity_max_kw is None)
            ):
                raise cls._bad("incomplete_fixed_matcher", f"{code}: required pipe pair or cooling capacity bounds missing")
            if entry["mode"] in {"fixed", "from"} and match.product_kind == "complete_split_system" and match.indoor_type in {"wall", "console"} and (
                match.match_strategy == "type_only" or
                (match.match_strategy == "capacity_only" and match.capacity_max_kw is None)
            ):
                raise cls._bad("unbounded_capacity_matcher", f"{code}: fixed wall/console capacity matcher needs a reviewed upper bound")
            if entry["mode"] in {"fixed", "from"} and exact_money(entry["base_price"]) <= 0:
                raise cls._bad("missing_base_price", f"{code}: exact/lower-bound price must be positive")
            rule_codes = {rule["code"] for rule in entry["rules"]}
            if entry["mode"] in {"fixed", "from"} and match.work_kind == "standard" and "route.extra_m" not in rule_codes:
                raise cls._bad("missing_route_price", f"{code}: route.extra_m is required")
            if match.work_kind == "prelaid_route" and (Decimal(entry["included_route_m"]) != 0 or
                    "route.extra_m" in rule_codes or entry["included_holes"]):
                raise cls._bad("invalid_prelaid_inclusions", f"{code}: prelaid work has no new included route or hole")
            for hole_type in entry["included_holes"]:
                if hole_type == "shared_pass_through":
                    allowance = Decimal(entry["included_holes"][hole_type])
                    if allowance < 0 or allowance > 100:
                        raise cls._bad("invalid_shared_hole", f"{code}: shared pass-through allowance is invalid")
                    if {"through_thin", "through_thick"} & entry["included_holes"].keys():
                        raise cls._bad("mixed_hole_allowances", f"{code}: shared and per-type pass-through allowances cannot be combined")
                    if not {"hole.through_thin.extra", "hole.through_thick.extra"} <= rule_codes:
                        raise cls._bad("missing_hole_price", f"{code}: both pass-through prices are required")
                    continue
                if entry["mode"] != "quote" and f"hole.{hole_type}.extra" not in rule_codes:
                    raise cls._bad("missing_hole_price", f"{code}: extra hole price is required")
            for rule in entry["rules"]:
                expected = cls._component_signature(rule["code"])
                if expected is None or (rule["rule_type"], rule["unit"], bool(rule["is_optional"])) != expected:
                    raise cls._bad("invalid_component_rule", f"{code}: {rule['code']} calculation type, unit, or optional mode is invalid")
                signature = (rule["rule_type"], rule["unit"])
                old_signature = component_signatures.setdefault(rule["code"], signature)
                if old_signature != signature:
                    raise cls._bad("component_code_conflict", f"{code}: {rule['code']} unit or calculation type differs")
                if rule["code"] == "discount.equipment_bundle" and Decimal(rule["unit_price"]) > Decimal(entry["base_price"]):
                    raise cls._bad("excessive_discount", f"{code}: bundle discount exceeds base price")
                if rule["code"].startswith("access."):
                    old = site_prices.setdefault(rule["code"], rule["unit_price"])
                    if old != rule["unit_price"]:
                        raise cls._bad("site_extra_conflict", f"{code}: {rule['code']} site prices disagree")
            if len(rule_codes) != len(entry["rules"]):
                raise cls._bad("duplicate_component_code", f"{code}: duplicate component code")
            # A price-book matcher is structured. Legacy category/power strings never select a price.
            assert match.indoor_type or match.product_kind == "multi_split_system"
        for index, first in enumerate(entries):
            for second in entries[index + 1:]:
                a = InstallationMatcher.model_validate(first["match"])
                b = InstallationMatcher.model_validate(second["match"])
                if cls._specificity(a) == cls._specificity(b) and cls._overlap(a, b):
                    raise cls._bad("matcher_conflict", f"{first['code']} overlaps {second['code']} at equal specificity")

    @classmethod
    async def build_entries_from_drafts(cls, session: AsyncSession, scope: TenantScope) -> list[dict[str, Any]]:
        """Validate active typed drafts without publishing or mutating them."""
        tariffs = await TariffsService.get_all_tariffs(session, include_inactive=False, tenant_scope=scope)
        entries: list[dict[str, Any]] = []
        for tariff in tariffs:
            if tariff.service_kind != "installation" or tariff.installation_match is None:
                continue
            try:
                match = InstallationMatcher.model_validate(tariff.installation_match)
            except ValidationError as exc:
                raise cls._bad("invalid_matcher", f"Tariff {tariff.id}: {exc}") from exc
            code = (tariff.installation_code or "").strip()
            if not code or not code.startswith("installation."):
                raise cls._bad("missing_tariff_code", f"Tariff {tariff.id}: installation.* code required")
            if tariff.installation_price_mode not in {"fixed", "from", "quote"}:
                raise cls._bad("invalid_price_mode", f"Tariff {tariff.id}: invalid price mode")
            try:
                base_price = exact_money(tariff.base_price)
            except ValueError as exc:
                raise cls._bad("invalid_base_price", f"Tariff {tariff.id}: {exc}") from exc
            included_route = Decimal(str(tariff.included_route_meters))
            if not included_route.is_finite() or included_route < 0:
                raise cls._bad("invalid_included_route", f"Tariff {tariff.id}: invalid included route")
            included_holes: dict[str, str] = {}
            for hole_type, value in (tariff.included_holes_by_type or {}).items():
                quantity = Decimal(str(value))
                if not hole_type or not quantity.is_finite() or quantity < 0 or quantity != quantity.to_integral_value():
                    raise cls._bad("invalid_included_holes", f"Tariff {tariff.id}: invalid included holes")
                included_holes[hole_type] = str(quantity)
            rules: list[dict[str, Any]] = []
            for rule in tariff.rules:
                if not rule.is_active:
                    continue
                component_code = (rule.component_code or "").strip()
                if not component_code:
                    raise cls._bad("missing_component_code", f"Rule {rule.id}: stable code required")
                try:
                    unit_price = exact_money(rule.unit_price)
                except ValueError as exc:
                    raise cls._bad("invalid_rule_price", f"Rule {rule.id}: {exc}") from exc
                if cls._component_signature(component_code) is None:
                    raise cls._bad("unknown_component_code", f"Rule {rule.id}: unsupported component code")
                if component_code not in {"route.extra_m", "discount.equipment_bundle"} and not component_code.startswith("hole.") and not rule.is_optional:
                    raise cls._bad("extra_default_on", f"Rule {rule.id}: extras must default off")
                if component_code == "discount.equipment_bundle" and (rule.rule_type != "fixed_once" or rule.is_optional):
                    raise cls._bad("invalid_discount_rule", f"Rule {rule.id}: bundle discount must be automatic fixed_once")
                rules.append({"id": rule.id, "code": component_code, "rule_type": rule.rule_type,
                              "name": rule.name, "line_template": rule.line_template, "unit": rule.unit,
                              "unit_price": str(money(unit_price)), "is_optional": bool(rule.is_optional),
                              "sort_order": rule.sort_order})
            entries.append({"tariff_id": tariff.id, "code": code, "match": match.model_dump(mode="json"),
                            "mode": tariff.installation_price_mode, "base_price": str(money(base_price)),
                            "short_name": tariff.effective_short_name, "description": tariff.effective_full_description,
                            "included_route_m": str(included_route), "included_holes": included_holes, "rules": rules})
        cls._validate_entries(entries)
        entries.sort(key=lambda item: item["code"])
        return entries

    @classmethod
    async def current_draft_fingerprint(cls, session: AsyncSession, scope: TenantScope) -> str:
        return cls._fingerprint(await cls.build_entries_from_drafts(session, scope))

    @classmethod
    async def publish(cls, session: AsyncSession, scope: TenantScope, *, actor: str,
                      commit: bool = True) -> InstallationPublishResponse:
        # Lock the tenant row to serialize publication by independent workers.
        from models import Tenant
        await session.execute(select(Tenant).where(Tenant.id == scope.tenant_id).with_for_update(key_share=True))
        entries = await cls.build_entries_from_drafts(session, scope)
        fingerprint = cls._fingerprint(entries)
        current = await cls.latest(session, scope)
        if current and current.fingerprint == fingerprint:
            return InstallationPublishResponse(price_book_id=current.id, revision=current.revision,
                                               fingerprint=current.fingerprint, tariff_count=len(entries), published_at=current.published_at)
        if current:
            history = (await session.execute(select(InstallationPriceBook).where(
                InstallationPriceBook.tenant_id == scope.tenant_id
            ).order_by(InstallationPriceBook.revision))).scalars().all()
            previous_by_code = {entry["code"]: entry for book in history for entry in book.entries}
            previous_component_signatures = {
                rule["code"]: (rule["rule_type"], rule["unit"])
                for book in history for previous in book.entries for rule in previous["rules"]
            }
            for entry in entries:
                previous = previous_by_code.get(entry["code"])
                if previous and InstallationMatcher.model_validate(entry["match"]) != InstallationMatcher.model_validate(previous["match"]):
                    raise cls._bad("tariff_code_reused", f"{entry['code']}: matcher changed; publish under a new code")
                for rule in entry["rules"]:
                    older = previous_component_signatures.get(rule["code"])
                    if older and older != (rule["rule_type"], rule["unit"]):
                        raise cls._bad("component_code_reused", f"{entry['code']}: {rule['code']} unit or calculation type changed")
        book = InstallationPriceBook(tenant_id=scope.tenant_id, revision=(current.revision + 1 if current else 1),
                                     fingerprint=fingerprint, entries=entries, published_by=actor)
        session.add(book)
        if commit:
            await session.commit()
            await session.refresh(book)
        else:
            await session.flush()
        return InstallationPublishResponse(price_book_id=book.id, revision=book.revision,
                                           fingerprint=fingerprint, tariff_count=len(entries), published_at=book.published_at)

    @staticmethod
    async def latest(session: AsyncSession, scope: TenantScope) -> InstallationPriceBook | None:
        return (await session.execute(select(InstallationPriceBook).where(
            InstallationPriceBook.tenant_id == scope.tenant_id).order_by(InstallationPriceBook.revision.desc()).limit(1)
        )).scalars().first()

    @classmethod
    async def _profile(cls, session: AsyncSession, scope: TenantScope, target: InstallationTarget) -> tuple[TypedInstallationProfile | None, dict[str, str]]:
        if target.typed_profile is not None:
            return target.typed_profile, {key: "confirmed_manual" for key in target.typed_profile.model_fields_set}
        visible = await ProductCollectionCatalogAccess.visible_by_ids(session, tenant_scope=scope, product_ids=[target.product_id])
        projection = visible.get(target.product_id)
        if projection is None:
            return None, {}
        product: Product = projection.product
        if not product.is_published:
            return None, {}
        specs = product.specs if isinstance(product.specs, dict) else {}
        raw_type = _spec_value(specs, "indoor_type")
        indoor_type = canonical_indoor_type_slug(raw_type)
        system_indoor_type = canonical_indoor_type_slug(_spec_value(specs, "type"))
        if indoor_type and system_indoor_type and indoor_type != system_indoor_type:
            indoor_type = None
        if indoor_type is None:
            indoor_type = system_indoor_type if not raw_type else None
        raw_capacity = _spec_value(specs, "capacity_cooling_kw")
        capacity = cls._single_quantity(raw_capacity, kind="power")
        sources = {"product_kind": "product.product_kind", "indoor_type": "product.specs.indoor_type" if raw_type else "product.specs.type"}
        if raw_capacity is None:
            capacity = cls._single_quantity(product.power_cooling, kind="power")
            sources["capacity_cooling_kw"] = "product.power_cooling_compatibility"
        else:
            sources["capacity_cooling_kw"] = "product.specs.capacity_cooling_kw"
        product_kind = ProductKindService.resolve(product.product_kind, specs=specs)
        derived_kind = ProductKindService.derive_from_specs(specs)
        if derived_kind in {"indoor_unit", "outdoor_unit", "panel", "accessory", "consumable", "other"}:
            product_kind = derived_kind
        values: dict[str, Any] = {"product_kind": product_kind,
                                  "indoor_type": None if product_kind == "multi_split_system" else indoor_type,
                                  "capacity_cooling_kw": capacity, "confirmed": True}
        for key in ("pipe_liquid", "pipe_gas", "weight_indoor", "weight_outdoor", "weight_indoor_package", "weight_outdoor_package"):
            raw = _spec_value(specs, key)
            if raw is not None:
                values[key] = cls._single_quantity(raw, kind="weight") if key.startswith("weight_") else str(raw).strip()
                sources[key] = f"product.specs.{key}"
        return TypedInstallationProfile.model_validate(values), sources

    @classmethod
    def _match(cls, profile: TypedInstallationProfile, entry: dict[str, Any], work_kind: str = "standard") -> tuple[bool, str | None]:
        match = InstallationMatcher.model_validate(entry["match"])
        if profile.product_kind != match.product_kind or match.work_kind != work_kind:
            return False, None
        if match.indoor_type is not None and profile.indoor_type != match.indoor_type:
            return False, None
        if match.pipe_liquid is not None:
            if not profile.pipe_liquid or not profile.pipe_gas:
                return False, "missing_pipe_pair"
            if (
                cls._pipe(profile.pipe_liquid),
                cls._pipe(profile.pipe_gas),
            ) != (
                cls._pipe(match.pipe_liquid),
                cls._pipe(match.pipe_gas),
            ):
                return False, None
        if match.capacity_min_kw is not None or match.capacity_max_kw is not None:
            capacity = profile.capacity_cooling_kw
            if capacity is None:
                return False, "missing_cooling_capacity"
            if match.capacity_min_kw is not None and (capacity < match.capacity_min_kw or
                    (capacity == match.capacity_min_kw and not match.capacity_min_inclusive)):
                return False, None
            if match.capacity_max_kw is not None and (capacity > match.capacity_max_kw or
                    (capacity == match.capacity_max_kw and not match.capacity_max_inclusive)):
                return False, None
        if match.weight_source is not None:
            weight = getattr(profile, match.weight_source)
            if weight is None:
                return False, "missing_required_weight"
            if match.weight_min_kg is not None and weight < match.weight_min_kg:
                return False, None
            if match.weight_max_kg is not None and weight > match.weight_max_kg:
                return False, None
        return True, None

    @classmethod
    async def resolve(cls, session: AsyncSession, scope: TenantScope, target: InstallationTarget,
                      *, book: InstallationPriceBook | None = None) -> tuple[InstallationResolveResponse, dict[str, Any] | None]:
        scope_ref = cls._scope_ref(scope)
        profile, sources = await cls._profile(session, scope, target)
        book = book or await cls.latest(session, scope)
        base = {"scope_ref": scope_ref, "profile": profile, "profile_sources": sources,
                "price_book_id": book.id if book else None, "price_book_revision": book.revision if book else None}
        if profile is None:
            return InstallationResolveResponse(status="unavailable", reason_code="product_not_visible", **base), None
        if profile.product_kind not in {"complete_split_system", "multi_split_system"}:
            if profile.product_kind in {"indoor_unit", "outdoor_unit", "panel", "accessory", "consumable"}:
                return InstallationResolveResponse(status="unavailable", reason_code="ineligible_product_kind", **base), None
            return InstallationResolveResponse(status="quote", reason_code="incomplete_equipment", **base), None
        if not profile.confirmed:
            return InstallationResolveResponse(status="quote", reason_code="unconfirmed_profile", **base), None
        if profile.product_kind == "multi_split_system":
            if target.product_id is not None:
                return InstallationResolveResponse(status="quote", reason_code="multisplit_requires_manager_composition", **base), None
            if profile.indoor_unit_count is None or not profile.composition_note:
                return InstallationResolveResponse(status="quote", reason_code="missing_confirmed_multisplit_composition", **base), None
        elif profile.indoor_type is None:
            return InstallationResolveResponse(status="quote", reason_code="missing_equipment_type", **base), None
        if not book:
            return InstallationResolveResponse(status="quote", reason_code="price_book_not_published", **base), None
        candidates: list[dict[str, Any]] = []
        missing: list[tuple[int, str]] = []
        for entry in book.entries:
            matched, reason = cls._match(profile, entry, target.work_kind)
            if matched:
                candidates.append(entry)
            if reason:
                missing.append((cls._specificity(InstallationMatcher.model_validate(entry["match"])), reason))
        if not candidates:
            reason = sorted(missing, key=lambda item: (-item[0], item[1]))[0][1] if missing else "no_matching_tariff"
            return InstallationResolveResponse(status="quote", reason_code=reason, **base), None
        candidates.sort(key=lambda item: cls._specificity(InstallationMatcher.model_validate(item["match"])), reverse=True)
        top_specificity = cls._specificity(InstallationMatcher.model_validate(candidates[0]["match"]))
        relevant_missing = sorted((reason for specificity, reason in missing if specificity >= top_specificity))
        if relevant_missing:
            return InstallationResolveResponse(status="quote", reason_code=relevant_missing[0], **base), None
        if len(candidates) > 1 and top_specificity == cls._specificity(InstallationMatcher.model_validate(candidates[1]["match"])):
            return InstallationResolveResponse(status="quote", reason_code="matcher_conflict", **base), None
        entry = candidates[0]
        match = InstallationMatcher.model_validate(entry["match"])
        matched_by = ["product_kind", "work_kind"] + (["indoor_type"] if match.indoor_type else []) + [name for name in ("capacity_min_kw", "capacity_max_kw", "pipe_liquid", "weight_source") if getattr(match, name) is not None]
        units = profile.indoor_unit_count if match.product_kind == "multi_split_system" else 1
        included_route = Decimal(entry["included_route_m"]) * units
        return InstallationResolveResponse(status=entry["mode"], profile=profile, profile_sources=sources,
            matched_by=matched_by, tariff_code=entry["code"], scope_ref=scope_ref,
            price_book_id=book.id, price_book_revision=book.revision,
            included={"route_m": str(included_route), "holes_by_type": entry["included_holes"]},
            available_extras=[rule["code"] for rule in entry["rules"] if rule["is_optional"]],
            explanation=(f"{cls._work_label(entry)}; включена трасса до {cls._quantity_text(included_route)} м" if match.work_kind == "standard"
                         else f"{cls._work_label(entry)} на готовую трассу; новая трасса не включена"),
            price_mode=entry["mode"],
            base_price=Decimal(entry["base_price"]) * units if entry["mode"] != "quote" else None), entry

    @classmethod
    def _component(cls, code: str, line: Any, key: str | None, *, actual: Decimal | None = None,
                   included: Decimal | None = None) -> InstallationComponent:
        gross = money(line.line_total)
        return InstallationComponent(code=code, installation_key=key, unit=line.unit,
            quantity=Decimal(str(line.qty)), unit_price=exact_money(line.unit_price), gross=gross,
            net=gross, description=line.name, actual=actual, included=included)

    @classmethod
    def _rule_component(cls, entry: dict[str, Any], rule: dict[str, Any], key: str | None,
                        *, route: Decimal, holes: int = 0, input_qty: Decimal | None = None,
                        actual: Decimal | None = None, included: Decimal | None = None) -> InstallationComponent | None:
        tariff = ServiceTariff(id=entry["tariff_id"], selector_label=entry["short_name"],
                               base_price=int(Decimal(entry["base_price"])),
                               included_route_meters=float(included if rule["code"] == "route.extra_m" and included is not None
                                                           else Decimal(entry["included_route_m"])))
        source_rule = ServiceTariffRule(id=rule["id"], tariff_id=entry["tariff_id"],
            rule_type=rule["rule_type"], name=rule["name"], line_template=rule["line_template"],
            unit=rule["unit"], unit_price=float(Decimal(rule["unit_price"])), is_optional=rule["is_optional"])
        payload = ManagerInstallEstimateCalculatePayload(tariff_id=entry["tariff_id"], route_length_m=float(route),
                                                         extra_holes_count=holes, quantity=1)
        line = ServiceEstimateService._build_rule_line(source_rule, tariff=tariff, payload=payload,
                                                       quantity=1, rule_input_qty=input_qty, sort_order=0)
        return cls._component(rule["code"], line, key, actual=actual, included=included) if line else None

    @classmethod
    async def preview(cls, session: AsyncSession, scope: TenantScope, payload: InstallationPreviewPayload,
                      *, idempotency_key: str | None = None, persist: bool = True) -> InstallationPreviewResponse:
        request_hash = None
        key_hash = None
        if persist:
            if idempotency_key is None:
                raise ValueError("A persistent preview requires an idempotency key")
            request_hash = InstallationPreviewReceiptService.input_hash(payload)
            key_hash = InstallationPreviewReceiptService.key_hash(idempotency_key)
            replay = await InstallationPreviewReceiptService.replay(
                session, scope, key_hash=key_hash, request_hash=request_hash)
            if replay is not None:
                return replay
        book = await cls.latest(session, scope)
        base = {"scope_ref": cls._scope_ref(scope), "price_book_id": book.id if book else None,
                "price_book_revision": book.revision if book else None}
        if payload.expected_revision is not None and book and payload.expected_revision != book.revision:
            raise HTTPException(status_code=409, detail={"code": "price_changed", "current_revision": book.revision})
        if book is None:
            return InstallationPreviewResponse(status="quote", reason_code="price_book_not_published", **base)
        components: list[InstallationComponent] = []
        applied_discounts: list[InstallationAppliedDiscount] = []
        work_summaries: list[InstallationWorkSummary] = []
        site_work: list[InstallationSelectedWork] = []
        resolutions: list[dict[str, Any]] = []
        matched_entries: list[dict[str, Any]] = []
        status = "fixed"
        for installation in payload.installations:
            result, entry = await cls.resolve(session, scope, installation, book=book)
            if entry is None:
                return InstallationPreviewResponse(status=result.status, reason_code=result.reason_code, **base)
            if entry["mode"] == "quote":
                return InstallationPreviewResponse(status="quote", reason_code="manual_quote_tariff", **base)
            if entry["mode"] == "from":
                status = "from"
            matcher = InstallationMatcher.model_validate(entry["match"])
            if matcher.work_kind == "prelaid_route" and installation.route_length_m > 0:
                return InstallationPreviewResponse(status="quote", reason_code="prelaid_new_route_requires_quote", **base)
            if installation.holes_by_type.get("through_over_80", Decimal("0")) > 0:
                return InstallationPreviewResponse(status="quote", reason_code="wall_over_80_requires_quote", **base)
            matched_entries.append(entry)
            resolutions.append({"key": installation.key, "resolution": result.model_dump(mode="json")})
            units = result.profile.indoor_unit_count if matcher.product_kind == "multi_split_system" else 1
            work_label = cls._work_label(entry)
            if matcher.product_kind == "multi_split_system":
                noun = "блока" if 2 <= units % 10 <= 4 and not 12 <= units % 100 <= 14 else "блоков"
                work_label += f": {units} внутренних {noun}"
            if matcher.work_kind == "prelaid_route":
                work_label += " на готовую трассу"
            tariff = ServiceTariff(id=entry["tariff_id"], selector_label=work_label,
                                   short_name=work_label, full_description=work_label,
                                   base_price=int(Decimal(entry["base_price"])))
            line = ServiceEstimateService._build_base_line(tariff, units, 0)
            components.append(cls._component("installation.base", line, installation.key))
            measured = []
            selected_extras = []
            rules = {rule["code"]: rule for rule in entry["rules"]}
            bundle_discount = rules.get("discount.equipment_bundle")
            if installation.product_id is not None and bundle_discount is not None:
                applied_discounts.append(InstallationAppliedDiscount(
                    code="discount.equipment_bundle", installation_key=installation.key,
                    amount=Decimal(bundle_discount["unit_price"])))
            included_route = Decimal(entry["included_route_m"]) * units
            measured.append(InstallationMeasuredWork(
                code="route.length_m", label=("Новая трасса" if matcher.work_kind == "prelaid_route" else "Трасса"), unit="м",
                actual=installation.route_length_m, included=included_route,
                extra=max(installation.route_length_m - included_route, Decimal("0")),
            ))
            if installation.route_length_m > included_route:
                rule = rules.get("route.extra_m")
                if rule is None:
                    return InstallationPreviewResponse(status="quote", reason_code="missing_route_price", **base)
                part = cls._rule_component(entry, rule, installation.key, route=installation.route_length_m,
                                           actual=installation.route_length_m, included=included_route)
                if part is None:
                    raise cls._bad("unpriced_component", "Selected route overage produced no line")
                components.append(part)
            shared_remaining = Decimal(entry["included_holes"].get("shared_pass_through", "0"))
            holes_ordered = sorted(installation.holes_by_type.items(),
                key=lambda pair: (-(Decimal(rules.get(f"hole.{pair[0]}.extra", {}).get("unit_price", "0"))), pair[0]))
            for hole_type, actual in holes_ordered:
                if actual != actual.to_integral_value():
                    raise cls._bad("invalid_hole_quantity", "Hole counts must be whole numbers")
                included = Decimal(entry["included_holes"].get(hole_type, "0"))
                if hole_type in {"through_thin", "through_thick"} and shared_remaining > 0:
                    use = min(actual, shared_remaining)
                    included += use
                    shared_remaining -= use
                extra = max(actual - included, Decimal("0"))
                measured.append(InstallationMeasuredWork(
                    code=f"hole.{hole_type}", label=cls._measured_label(f"hole.{hole_type}"),
                    unit="шт", actual=actual, included=included, extra=extra,
                ))
                if extra == 0:
                    continue
                code = f"hole.{hole_type}.extra"
                rule = rules.get(code)
                if rule is None:
                    return InstallationPreviewResponse(status="quote", reason_code="missing_hole_price", **base)
                part = cls._rule_component(entry, rule, installation.key, route=installation.route_length_m,
                                           holes=int(extra), actual=actual, included=included)
                if part is None:
                    raise cls._bad("unpriced_component", f"{code}: selected hole overage produced no line")
                components.append(part)
            seen_extras: set[str] = set()
            for extra in installation.extras:
                if extra.code in seen_extras or extra.code.startswith("access."):
                    raise cls._bad("invalid_extra", "Duplicate or site-only extra")
                seen_extras.add(extra.code)
                if "pump.package" in seen_extras and {"pump.supply", "pump.install"} & seen_extras:
                    raise cls._bad("invalid_extra_combination", "Pump package cannot be combined with legacy pump parts")
                rule = rules.get(extra.code)
                if rule is None or not rule["is_optional"] or extra.code in {"route.extra_m"} or extra.code.startswith("hole."):
                    raise cls._bad("unknown_extra", extra.code)
                if extra.code in {"pump.supply", "pump.install", "pump.package"} and extra.quantity != 1:
                    raise cls._bad("invalid_extra_quantity", f"{extra.code}: one per installation")
                part = cls._rule_component(entry, rule, installation.key, route=installation.route_length_m,
                                           input_qty=extra.quantity)
                if part is None:
                    raise cls._bad("unpriced_component", f"{extra.code}: selected extra produced no line")
                components.append(part)
                selected_extras.append(InstallationSelectedWork(
                    code=extra.code, label=cls._EXTRA_LABELS[extra.code],
                    unit=part.unit, quantity=extra.quantity,
                ))
            work_summaries.append(InstallationWorkSummary(
                installation_key=installation.key, display_label=installation.display_label,
                tariff_code=entry["code"],
                work_label=work_label, measured=measured, selected_extras=selected_extras,
            ))
        approved_site = {item.code: item for item in payload.approved_site_access}
        seen_site: set[str] = set()
        for extra in payload.site_extras:
            if extra.code in seen_site or not extra.code.startswith("access."):
                raise cls._bad("invalid_site_extra", extra.code)
            seen_site.add(extra.code)
            rule_entry = next(((entry, rule) for entry in matched_entries for rule in entry["rules"]
                               if rule["code"] == extra.code and rule["is_optional"]), None)
            if rule_entry is None:
                raise cls._bad("unknown_site_extra", extra.code)
            if extra.quantity != 1:
                raise cls._bad("invalid_site_quantity", "Site access is selected once per site")
            entry, rule = rule_entry
            part = cls._rule_component(entry, rule, None, route=Decimal("0"), input_qty=extra.quantity)
            if part is None:
                raise cls._bad("unpriced_component", f"{extra.code}: selected site work produced no line")
            approval = approved_site.get(extra.code)
            if approval is None:
                part.is_provisional = True
                status = "provisional"
            else:
                approved_amount = exact_money(approval.actual_total)
                part.unit_price = money(approved_amount / extra.quantity)
                part.gross = approved_amount
                part.net = approved_amount
                part.description += f"; согласовано: {approval.scope_note}"
            components.append(part)
            site_work.append(InstallationSelectedWork(
                code=extra.code, label=cls._EXTRA_LABELS[extra.code],
                unit=part.unit, quantity=extra.quantity,
                scope_note=approval.scope_note if approval else None,
            ))
        subtotal = sum((item.gross for item in components), Decimal("0.00"))
        discount = sum((item.amount for item in applied_discounts), Decimal("0.00"))
        if discount > subtotal:
            raise cls._bad("excessive_discount", "Applicable discounts exceed the subtotal")
        net_amounts = allocate_discount([item.gross for item in components], discount)
        for item, net in zip(components, net_amounts):
            item.net = net
            item.discount = item.gross - net
        text_parts = [cls._summary_text(summary) for summary in work_summaries]
        if site_work:
            text_parts.append("На объекте: " + ", ".join(
                f"{item.label.lower()} {cls._quantity_text(item.quantity)} {item.unit}" +
                (f" (согласовано: {item.scope_note})" if item.scope_note else "")
                for item in site_work
            ))
        customer_text = ". ".join(text_parts) + "."
        if status == "provisional":
            customer_text += " Стоимость доступа к месту работ ориентировочная; состав и окончательная сумма требуют согласования менеджером."
        response = InstallationPreviewResponse(status=status,
            reason_code="site_access_requires_approval" if status == "provisional" else None,
            components=components,
            applied_discounts=applied_discounts, subtotal=subtotal,
            installations=work_summaries, site_work=site_work, customer_text=customer_text,
            discount=discount, total=subtotal - discount,
            explanation=("Стоимость указана как нижняя граница. " if status == "from" else "") + customer_text,
            **base)
        if not persist:
            return response
        snapshot = {"resolver_version": cls.RESOLVER_VERSION, "scope": {"tenant_id": scope.tenant_id,
                    "storefront_id": scope.storefront_id}, "price_book_id": book.id, "revision": book.revision,
                    "input": payload.model_dump(mode="json"), "resolutions": resolutions,
                    "result": response.model_dump(mode="json")}
        return await InstallationPreviewReceiptService.store_or_replay(
            session, scope, key_hash=key_hash, request_hash=request_hash,
            price_book_id=book.id, snapshot=snapshot)
