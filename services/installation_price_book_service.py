"""Publish validated installation tariffs and preview only immutable revisions."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import InstallationPriceBook, InstallationPreviewSnapshot, InstallationRate, Product, ServiceTariff, ServiceTariffRule
from models.tenancy import TenantScope
from schemas import ManagerInstallEstimateCalculatePayload
from schemas_installation_price_book import (
    InstallationComponent, InstallationMatcher, InstallationPreviewPayload,
    InstallationPreviewResponse, InstallationPublishResponse, InstallationResolveResponse,
    InstallationTarget, TypedInstallationProfile,
    InstallationLegacyComparisonResponse, InstallationLegacyComparisonRow,
    InstallationLegacyCandidate,
    InstallationAppliedDiscount,
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


class InstallationPriceBookService:
    RESOLVER_VERSION = "installation-book-v1"
    PREVIEW_TTL = timedelta(minutes=30)

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
        """Read-only candidate report. Similarity never copies or publishes prices."""
        book = await cls.latest(session, scope)
        rates = (await session.execute(select(InstallationRate).where(
            service_catalog_scope_clause(InstallationRate, scope)
        ).order_by(InstallationRate.id).offset(offset).limit(limit))).scalars().all()
        category_map = {"wall": "wall", "cassette": "cassette", "duct": "duct",
                        "ceiling": "floor_ceiling", "floor_ceiling": "floor_ceiling", "column": "column"}
        items: list[InstallationLegacyComparisonRow] = []
        for rate in rates:
            indoor_type = category_map.get((rate.category or "").strip().lower().replace("-", "_"))
            candidates = [entry for entry in (book.entries if book else [])
                          if indoor_type and entry["match"]["indoor_type"] == indoor_type]
            def route_price(entry: dict[str, Any]) -> Decimal | None:
                return next((Decimal(rule["unit_price"]) for rule in entry["rules"]
                             if rule["code"] == "route.extra_m"), None)
            same_price = [entry for entry in candidates
                          if Decimal(entry["base_price"]) == Decimal(rate.base_price)
                          and route_price(entry) == Decimal(rate.extra_pipe_price)]
            status = ("price_equal_review_required" if same_price else
                      "price_diff_review_required" if candidates else "unmapped_review_required")
            items.append(InstallationLegacyComparisonRow(
                legacy_rate_id=rate.id, legacy_category=rate.category, legacy_power_range=rate.power_range,
                legacy_base_price=Decimal(rate.base_price), legacy_route_extra_price=Decimal(rate.extra_pipe_price),
                candidates=[InstallationLegacyCandidate(tariff_code=entry["code"],
                    matcher=InstallationMatcher.model_validate(entry["match"]), mode=entry["mode"],
                    base_price=Decimal(entry["base_price"]), route_extra_price=route_price(entry))
                    for entry in candidates], status=status,
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
    def _range_overlap(a_min: Decimal | None, a_max: Decimal | None, b_min: Decimal | None, b_max: Decimal | None) -> bool:
        return (a_max is None or b_min is None or b_min <= a_max) and (b_max is None or a_min is None or a_min <= b_max)

    @staticmethod
    def _specificity(match: InstallationMatcher) -> int:
        return sum(value is not None for value in (
            match.capacity_min_kw, match.capacity_max_kw, match.pipe_liquid,
            match.weight_source, match.weight_min_kg, match.weight_max_kg,
        ))

    @classmethod
    def _overlap(cls, a: InstallationMatcher, b: InstallationMatcher) -> bool:
        if a.indoor_type != b.indoor_type or a.product_kind != b.product_kind:
            return False
        if a.pipe_liquid and b.pipe_liquid and (cls._pipe(a.pipe_liquid), cls._pipe(a.pipe_gas)) != (cls._pipe(b.pipe_liquid), cls._pipe(b.pipe_gas)):
            return False
        if not cls._range_overlap(a.capacity_min_kw, a.capacity_max_kw, b.capacity_min_kw, b.capacity_max_kw):
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
                match.pipe_liquid is None or
                (match.capacity_min_kw is None and match.capacity_max_kw is None)
            ):
                raise cls._bad("incomplete_fixed_matcher", f"{code}: pipe pair and cooling capacity bounds are required")
            if entry["mode"] in {"fixed", "from"} and exact_money(entry["base_price"]) <= 0:
                raise cls._bad("missing_base_price", f"{code}: exact/lower-bound price must be positive")
            rule_codes = {rule["code"] for rule in entry["rules"]}
            if entry["mode"] in {"fixed", "from"} and "route.extra_m" not in rule_codes:
                raise cls._bad("missing_route_price", f"{code}: route.extra_m is required")
            for hole_type in entry["included_holes"]:
                if entry["mode"] != "quote" and f"hole.{hole_type}.extra" not in rule_codes:
                    raise cls._bad("missing_hole_price", f"{code}: extra hole price is required")
            for rule in entry["rules"]:
                signature = (rule["rule_type"], rule["unit"])
                old_signature = component_signatures.setdefault(rule["code"], signature)
                if old_signature != signature:
                    raise cls._bad("component_code_conflict", f"{rule['code']}: unit or calculation type differs")
                if rule["code"] == "discount.equipment_bundle" and Decimal(rule["unit_price"]) > Decimal(entry["base_price"]):
                    raise cls._bad("excessive_discount", f"{code}: bundle discount exceeds base price")
                if rule["code"].startswith("access."):
                    old = site_prices.setdefault(rule["code"], rule["unit_price"])
                    if old != rule["unit_price"]:
                        raise cls._bad("site_extra_conflict", f"{rule['code']}: site prices disagree")
                if rule["code"] == "route.extra_m" and rule["rule_type"] != "per_meter_over_included":
                    raise cls._bad("invalid_component_rule", "route.extra_m must use per_meter_over_included")
                if rule["code"].startswith("hole.") and rule["rule_type"] != "per_hole_manual":
                    raise cls._bad("invalid_component_rule", "hole extra must use per_hole_manual")
            if len(rule_codes) != len(entry["rules"]):
                raise cls._bad("duplicate_component_code", f"{code}: duplicate component code")
            # A price-book matcher is structured. Legacy category/power strings never select a price.
            assert match.indoor_type
        for index, first in enumerate(entries):
            for second in entries[index + 1:]:
                a = InstallationMatcher.model_validate(first["match"])
                b = InstallationMatcher.model_validate(second["match"])
                if cls._specificity(a) == cls._specificity(b) and cls._overlap(a, b):
                    raise cls._bad("matcher_conflict", f"{first['code']} overlaps {second['code']} at equal specificity")

    @classmethod
    async def publish(cls, session: AsyncSession, scope: TenantScope, *, actor: str) -> InstallationPublishResponse:
        # Lock the tenant row to serialize publication by independent workers.
        from models import Tenant
        await session.execute(select(Tenant).where(Tenant.id == scope.tenant_id).with_for_update())
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
                if component_code not in {"route.extra_m", "pump.supply", "pump.install", "access.scaffold", "access.lift", "discount.equipment_bundle", "chase.extra_m"} and not re.fullmatch(r"hole\.[a-z][a-z0-9_]*\.extra", component_code):
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
                        raise cls._bad("component_code_reused", f"{rule['code']}: unit or calculation type changed")
        book = InstallationPriceBook(tenant_id=scope.tenant_id, revision=(current.revision + 1 if current else 1),
                                     fingerprint=fingerprint, entries=entries, published_by=actor)
        session.add(book)
        await session.commit()
        await session.refresh(book)
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
        values: dict[str, Any] = {"product_kind": product_kind, "indoor_type": indoor_type,
                                  "capacity_cooling_kw": capacity, "confirmed": True}
        for key in ("pipe_liquid", "pipe_gas", "weight_indoor", "weight_outdoor", "weight_indoor_package", "weight_outdoor_package"):
            raw = _spec_value(specs, key)
            if raw is not None:
                values[key] = cls._single_quantity(raw, kind="weight") if key.startswith("weight_") else str(raw).strip()
                sources[key] = f"product.specs.{key}"
        return TypedInstallationProfile.model_validate(values), sources

    @classmethod
    def _match(cls, profile: TypedInstallationProfile, entry: dict[str, Any]) -> tuple[bool, str | None]:
        match = InstallationMatcher.model_validate(entry["match"])
        if profile.indoor_type != match.indoor_type:
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
            if match.capacity_min_kw is not None and capacity < match.capacity_min_kw:
                return False, None
            if match.capacity_max_kw is not None and capacity > match.capacity_max_kw:
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
        if profile.product_kind != "complete_split_system":
            if profile.product_kind in {"indoor_unit", "outdoor_unit", "panel", "accessory", "consumable"}:
                return InstallationResolveResponse(status="unavailable", reason_code="ineligible_product_kind", **base), None
            return InstallationResolveResponse(status="quote", reason_code="incomplete_equipment", **base), None
        if not profile.confirmed:
            return InstallationResolveResponse(status="quote", reason_code="unconfirmed_profile", **base), None
        if profile.indoor_type is None:
            return InstallationResolveResponse(status="quote", reason_code="missing_equipment_type", **base), None
        if not book:
            return InstallationResolveResponse(status="quote", reason_code="price_book_not_published", **base), None
        candidates: list[dict[str, Any]] = []
        missing: set[str] = set()
        for entry in book.entries:
            matched, reason = cls._match(profile, entry)
            if matched:
                candidates.append(entry)
            if reason:
                missing.add(reason)
        if not candidates:
            reason = sorted(missing)[0] if missing else "no_matching_tariff"
            return InstallationResolveResponse(status="quote", reason_code=reason, **base), None
        candidates.sort(key=lambda item: cls._specificity(InstallationMatcher.model_validate(item["match"])), reverse=True)
        if len(candidates) > 1 and cls._specificity(InstallationMatcher.model_validate(candidates[0]["match"])) == cls._specificity(InstallationMatcher.model_validate(candidates[1]["match"])):
            return InstallationResolveResponse(status="quote", reason_code="matcher_conflict", **base), None
        entry = candidates[0]
        match = InstallationMatcher.model_validate(entry["match"])
        matched_by = ["product_kind", "indoor_type"] + [name for name in ("capacity_min_kw", "capacity_max_kw", "pipe_liquid", "weight_source") if getattr(match, name) is not None]
        return InstallationResolveResponse(status=entry["mode"], profile=profile, profile_sources=sources,
            matched_by=matched_by, tariff_code=entry["code"], scope_ref=scope_ref,
            price_book_id=book.id, price_book_revision=book.revision,
            included={"route_m": entry["included_route_m"], "holes_by_type": entry["included_holes"]},
            available_extras=[rule["code"] for rule in entry["rules"] if rule["is_optional"]],
            explanation=entry["description"], price_mode=entry["mode"],
            base_price=Decimal(entry["base_price"]) if entry["mode"] != "quote" else None), entry

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
                               included_route_meters=float(Decimal(entry["included_route_m"])))
        source_rule = ServiceTariffRule(id=rule["id"], tariff_id=entry["tariff_id"],
            rule_type=rule["rule_type"], name=rule["name"], line_template=rule["line_template"],
            unit=rule["unit"], unit_price=float(Decimal(rule["unit_price"])), is_optional=rule["is_optional"])
        payload = ManagerInstallEstimateCalculatePayload(tariff_id=entry["tariff_id"], route_length_m=float(route),
                                                         extra_holes_count=holes, quantity=1)
        line = ServiceEstimateService._build_rule_line(source_rule, tariff=tariff, payload=payload,
                                                       quantity=1, rule_input_qty=input_qty, sort_order=0)
        return cls._component(rule["code"], line, key, actual=actual, included=included) if line else None

    @classmethod
    async def preview(cls, session: AsyncSession, scope: TenantScope, payload: InstallationPreviewPayload) -> InstallationPreviewResponse:
        book = await cls.latest(session, scope)
        base = {"scope_ref": cls._scope_ref(scope), "price_book_id": book.id if book else None,
                "price_book_revision": book.revision if book else None}
        if payload.expected_revision is not None and book and payload.expected_revision != book.revision:
            raise HTTPException(status_code=409, detail={"code": "price_changed", "current_revision": book.revision})
        if book is None:
            return InstallationPreviewResponse(status="quote", reason_code="price_book_not_published", **base)
        components: list[InstallationComponent] = []
        applied_discounts: list[InstallationAppliedDiscount] = []
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
            matched_entries.append(entry)
            resolutions.append({"key": installation.key, "resolution": result.model_dump(mode="json")})
            tariff = ServiceTariff(id=entry["tariff_id"], selector_label=entry["short_name"],
                                   short_name=entry["short_name"], full_description=entry["description"],
                                   base_price=int(Decimal(entry["base_price"])))
            line = ServiceEstimateService._build_base_line(tariff, 1, 0)
            components.append(cls._component("installation.base", line, installation.key))
            rules = {rule["code"]: rule for rule in entry["rules"]}
            bundle_discount = rules.get("discount.equipment_bundle")
            if installation.product_id is not None and bundle_discount is not None:
                applied_discounts.append(InstallationAppliedDiscount(
                    code="discount.equipment_bundle", installation_key=installation.key,
                    amount=Decimal(bundle_discount["unit_price"])))
            included_route = Decimal(entry["included_route_m"])
            if installation.route_length_m > included_route:
                rule = rules.get("route.extra_m")
                if rule is None:
                    return InstallationPreviewResponse(status="quote", reason_code="missing_route_price", **base)
                part = cls._rule_component(entry, rule, installation.key, route=installation.route_length_m,
                                           actual=installation.route_length_m, included=included_route)
                if part:
                    components.append(part)
            for hole_type, actual in installation.holes_by_type.items():
                if actual != actual.to_integral_value():
                    raise cls._bad("invalid_hole_quantity", "Hole counts must be whole numbers")
                included = Decimal(entry["included_holes"].get(hole_type, "0"))
                extra = max(actual - included, Decimal("0"))
                if extra == 0:
                    continue
                code = f"hole.{hole_type}.extra"
                rule = rules.get(code)
                if rule is None:
                    return InstallationPreviewResponse(status="quote", reason_code="missing_hole_price", **base)
                part = cls._rule_component(entry, rule, installation.key, route=installation.route_length_m,
                                           holes=int(extra), actual=actual, included=included)
                if part:
                    components.append(part)
            seen_extras: set[str] = set()
            for extra in installation.extras:
                if extra.code in seen_extras or extra.code.startswith("access."):
                    raise cls._bad("invalid_extra", "Duplicate or site-only extra")
                seen_extras.add(extra.code)
                rule = rules.get(extra.code)
                if rule is None or not rule["is_optional"] or extra.code in {"route.extra_m"} or extra.code.startswith("hole."):
                    raise cls._bad("unknown_extra", extra.code)
                if extra.code in {"pump.supply", "pump.install"} and extra.quantity != 1:
                    raise cls._bad("invalid_extra_quantity", f"{extra.code}: one per installation")
                part = cls._rule_component(entry, rule, installation.key, route=installation.route_length_m,
                                           input_qty=extra.quantity)
                if part:
                    components.append(part)
        seen_site: set[str] = set()
        for extra in payload.site_extras:
            if extra.code in seen_site or not extra.code.startswith("access."):
                raise cls._bad("invalid_site_extra", extra.code)
            seen_site.add(extra.code)
            rule_entry = next(((entry, rule) for entry in matched_entries for rule in entry["rules"]
                               if rule["code"] == extra.code and rule["is_optional"]), None)
            if rule_entry is None:
                raise cls._bad("unknown_site_extra", extra.code)
            if extra.quantity != extra.quantity.to_integral_value():
                raise cls._bad("invalid_site_quantity", "Site access units must be whole")
            entry, rule = rule_entry
            part = cls._rule_component(entry, rule, None, route=Decimal("0"), input_qty=extra.quantity)
            if part:
                components.append(part)
        subtotal = sum((item.gross for item in components), Decimal("0.00"))
        discount = sum((item.amount for item in applied_discounts), Decimal("0.00"))
        if discount > subtotal:
            raise cls._bad("excessive_discount", "Applicable discounts exceed the subtotal")
        net_amounts = allocate_discount([item.gross for item in components], discount)
        for item, net in zip(components, net_amounts):
            item.net = net
            item.discount = item.gross - net
        response = InstallationPreviewResponse(status=status, components=components,
            applied_discounts=applied_discounts, subtotal=subtotal,
            discount=discount, total=subtotal - discount, explanation="Lower-bound estimate" if status == "from" else None,
            **base)
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + cls.PREVIEW_TTL
        snapshot = {"resolver_version": cls.RESOLVER_VERSION, "scope": {"tenant_id": scope.tenant_id,
                    "storefront_id": scope.storefront_id}, "price_book_id": book.id, "revision": book.revision,
                    "input": payload.model_dump(mode="json"), "resolutions": resolutions,
                    "result": response.model_dump(mode="json")}
        session.add(InstallationPreviewSnapshot(token_hash=hashlib.sha256(token.encode()).hexdigest(),
            tenant_id=scope.tenant_id, storefront_id=scope.storefront_id, price_book_id=book.id,
            input_hash=cls._fingerprint(snapshot["input"]), snapshot=snapshot, expires_at=expires))
        await session.commit()
        response.preview_ref = token
        response.expires_at = expires
        return response
