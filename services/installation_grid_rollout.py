"""Reviewed, atomic installation draft reset and immutable book publication."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from core.config import settings
from core.request_context import current_request_id
from models import (
    InstallationPriceBook, InstallationRate, Service, ServiceTariff,
    ServiceTariffRule, Storefront, Tenant, TenantAuditEvent,
)
from models.tenancy import TenantScope
from services.installation_grid_seed import SEED_VERSION, canonical_installation_grid
from services.installation_price_book_service import InstallationPriceBookService
from services.cooling_capacity import power_range_capacity_bounds
from services.service_catalog_scope import service_catalog_scope_clause
from services.storefront_settings_service import StorefrontSettingsService
from services.storefront_onboarding_plan_token import StorefrontOnboardingPlanToken
from services.storefront_onboarding_state import StorefrontOnboardingBlockedError


class InstallationGridPlanToken(StorefrontOnboardingPlanToken):
    @staticmethod
    def _key() -> bytes:
        return hashlib.sha256(
            b"mvn:installation-grid-rollout:plan-token:v1\0"
            + settings.SECRET_KEY.encode("utf-8")
        ).digest()


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _review_evidence_url(value: str | None) -> bool:
    parsed = urlparse(value or "")
    host = (parsed.hostname or "").lower()
    return (parsed.scheme == "https" and bool(parsed.path.strip("/")) and
            bool(host) and host not in {"localhost", "127.0.0.1"} and
            not host.endswith((".invalid", ".test", ".example")))


def _tariff_snapshot(row: ServiceTariff) -> dict[str, Any]:
    return {
        "id": row.id, "tenant_id": row.tenant_id,
        "source_tariff_id": row.source_tariff_id,
        "service_kind": row.service_kind, "installation_code": row.installation_code,
        "installation_match": row.installation_match,
        "installation_price_mode": row.installation_price_mode,
        "selector_label": row.selector_label, "estimate_template": row.estimate_template,
        "short_name": row.short_name, "full_description": row.full_description,
        "category": row.category, "power_range": row.power_range,
        "base_price": row.base_price,
        "included_route_meters": row.included_route_meters,
        "included_holes_by_type": row.included_holes_by_type,
        "is_active": row.is_active, "sort_order": row.sort_order,
        "comment": row.comment,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "rules": [{
            "id": rule.id, "tariff_id": rule.tariff_id,
            "source_rule_id": rule.source_rule_id,
            "rule_type": rule.rule_type, "name": rule.name,
            "line_template": rule.line_template, "unit": rule.unit,
            "unit_price": rule.unit_price, "component_code": rule.component_code,
            "is_optional": rule.is_optional, "is_favorite": rule.is_favorite,
            "is_active": rule.is_active, "sort_order": rule.sort_order,
            "service_id": rule.service_id,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        } for rule in sorted(row.rules, key=lambda item: (item.id or 0))],
    }


def _desired_snapshot() -> list[dict[str, Any]]:
    return [{"tariff": spec.fields(), "rules": [rule.fields() for rule in spec.rules]}
            for spec in canonical_installation_grid()]


def _validate_seed_against_installed_contract() -> None:
    entries = []
    next_rule_id = 1
    for tariff_id, spec in enumerate(canonical_installation_grid(), start=1):
        rules = []
        for rule in spec.rules:
            rules.append({
                "id": next_rule_id, "code": rule.code,
                "rule_type": rule.rule_type, "name": rule.name,
                "line_template": "{name}", "unit": rule.unit,
                "unit_price": str(rule.price), "is_optional": rule.optional,
                "sort_order": next_rule_id,
            })
            next_rule_id += 1
        entries.append({
            "tariff_id": tariff_id, "code": spec.code, "match": spec.match,
            "mode": "fixed", "base_price": str(spec.base_price),
            "short_name": spec.label, "description": spec.label,
            "included_route_m": str(spec.included_route_meters),
            "included_holes": {key: str(value) for key, value in spec.included_holes.items()},
            "rules": rules,
        })
    InstallationPriceBookService._validate_entries(entries)


def _candidate_comparison(
    *, category: str, power_range: str, old_base_price: int,
    old_extra_meter_price: float | None, work_kind: str = "standard",
    match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Show exact price values without claiming legacy matching is equivalent."""
    old_bounds = None
    if match and (match.get("capacity_min_kw") is not None or
                  match.get("capacity_max_kw") is not None):
        old_bounds = (match.get("capacity_min_kw"), match.get("capacity_max_kw"))
    else:
        old_bounds = power_range_capacity_bounds(power_range)
    candidates = []
    category_key = category.strip().lower().replace("-", "").replace("_", "")
    if category_key == "ceiling":
        category_key = "floorceiling"
    for spec in canonical_installation_grid():
        desired_match = spec.match
        if spec.category.lower() != category_key or desired_match["work_kind"] != work_kind:
            continue
        lower = desired_match.get("capacity_min_kw")
        upper = desired_match.get("capacity_max_kw")
        if lower is not None or upper is not None:
            if old_bounds is None or old_bounds[0] is None or old_bounds[1] is None:
                continue
            old_min, old_max = (Decimal(str(value)) for value in old_bounds)
            if lower is not None and old_min < Decimal(str(lower)):
                continue
            if upper is not None and old_max > Decimal(str(upper)):
                continue
            if lower is not None and old_min == Decimal(str(lower)) and not desired_match.get("capacity_min_inclusive", True):
                continue
            if upper is not None and old_max == Decimal(str(upper)) and not desired_match.get("capacity_max_inclusive", True):
                continue
        route_rule = next((rule for rule in spec.rules if rule.code == "route.extra_m"), None)
        candidates.append({
            "new_code": spec.code,
            "new_base_price": spec.base_price,
            "new_included_route_meters": spec.included_route_meters,
            "new_extra_meter_price": route_rule.price if route_rule else None,
        })
    return {
        "old_base_price": old_base_price,
        "old_extra_meter_price": old_extra_meter_price,
        "old_capacity_bounds_kw": list(old_bounds) if old_bounds is not None else None,
        "new_candidates": candidates,
        "coverage_status": ("range_candidate_only_not_equivalent_to_legacy_tag_priority"
                            if len(candidates) == 1 else
                            "unmapped_or_ambiguous_requires_review"),
    }


class InstallationGridRolloutService:
    """A single transaction resets every reviewed scope and publishes each book.

    Old tariff and rule rows are retained inactive, while append-only tenant
    audit events keep their complete pre-image. Immutable books, estimates,
    orders, and documents are never edited by this command.
    """

    @staticmethod
    async def _scope_rows(session: AsyncSession, scope: TenantScope, *, lock: bool):
        tariff_stmt = select(ServiceTariff).where(
            service_catalog_scope_clause(ServiceTariff, scope),
            ServiceTariff.service_kind == "installation",
        ).options(selectinload(ServiceTariff.rules)).order_by(ServiceTariff.id)
        rate_stmt = select(InstallationRate).where(
            service_catalog_scope_clause(InstallationRate, scope),
        ).order_by(InstallationRate.id)
        option_stmt = select(Service).where(
            service_catalog_scope_clause(Service, scope),
            Service.category == "installation_option",
        ).order_by(Service.id)
        book_stmt = select(InstallationPriceBook).where(
            InstallationPriceBook.tenant_id == scope.tenant_id,
        ).order_by(InstallationPriceBook.revision.desc()).limit(1)
        if lock:
            # Drafts are updated below; NO KEY UPDATE does not needlessly
            # block foreign-key KEY SHARE readers of the same tenant.
            tariff_stmt = tariff_stmt.with_for_update(key_share=True)
        tariffs = list((await session.execute(tariff_stmt)).scalars().unique().all())
        if lock and tariffs:
            await session.execute(select(ServiceTariffRule).where(
                ServiceTariffRule.tariff_id.in_([row.id for row in tariffs]),
            ).with_for_update(key_share=True))
        rates = list((await session.execute(rate_stmt)).scalars().all())
        options = list((await session.execute(option_stmt)).scalars().all())
        book = (await session.execute(book_stmt)).scalars().first()
        return tariffs, rates, options, book

    @classmethod
    async def plan(
        cls, session: AsyncSession, *, expected_partner_slugs: tuple[str, ...],
        backend_release_commit: str | None, backend_image_digest: str | None,
        web_v2_commit: str | None, web_v2_proof: str | None,
        manager_editor_proof: str | None, legacy_list_proof: str | None,
        legacy_calculate_proof: str | None,
        legacy_tariff_calculate_proof: str | None,
        include_demo_reset: bool = False, lock: bool = False,
    ) -> tuple[dict[str, Any], list[tuple[TenantScope, list[ServiceTariff]]]]:
        tenants = list((await session.execute(select(Tenant).order_by(Tenant.id))).scalars().all())
        storefronts = list((await session.execute(select(Storefront).order_by(Storefront.id))).scalars().all())
        defaults: dict[int, list[Storefront]] = {}
        for storefront in storefronts:
            if storefront.is_default:
                defaults.setdefault(storefront.tenant_id, []).append(storefront)
        blockers: list[str] = []
        system = [tenant for tenant in tenants if tenant.is_system and tenant.status == "active"]
        if len(system) != 1:
            blockers.append("exactly_one_active_system_tenant_required")
        active_partners = [tenant for tenant in tenants if not tenant.is_system
                           and tenant.status == "active"]
        if lock:
            selected_tenant_ids = [row.id for row in system + active_partners]
            selected_storefront_ids = [row.id for row in storefronts
                                       if row.tenant_id in selected_tenant_ids and row.is_default]
            # Lock only reviewed active scopes, in a stable order. Inactive
            # tenants and unrelated storefronts are read for inventory only.
            if selected_tenant_ids:
                await session.execute(select(Tenant).where(
                    Tenant.id.in_(selected_tenant_ids),
                ).order_by(Tenant.id).with_for_update(key_share=True))
            if selected_storefront_ids:
                await session.execute(select(Storefront).where(
                    Storefront.id.in_(selected_storefront_ids),
                ).order_by(Storefront.id).with_for_update(read=True, key_share=True))
        discovered = tuple(sorted(tenant.slug for tenant in active_partners))
        if tuple(sorted(expected_partner_slugs)) != discovered:
            blockers.append("expected_partner_slugs_do_not_match_discovered_active_partners")
        if len(set(expected_partner_slugs)) != len(expected_partner_slugs):
            blockers.append("duplicate_expected_partner_slug")
        if (backend_release_commit is None or
                re.fullmatch(r"[0-9a-f]{40}", backend_release_commit) is None):
            blockers.append("exact_backend_release_commit_required")
        if (backend_image_digest is None or
                re.fullmatch(r"sha256:[0-9a-f]{64}", backend_image_digest) is None):
            blockers.append("exact_backend_image_digest_required")
        if web_v2_commit is None or re.fullmatch(r"[0-9a-f]{40}", web_v2_commit) is None:
            blockers.append("verified_web_v2_commit_required")
        if not _review_evidence_url(web_v2_proof):
            blockers.append("verified_web_v2_runtime_proof_url_required")
        if not _review_evidence_url(manager_editor_proof):
            blockers.append("legacy_manager_rate_editor_guard_proof_url_required")
        if not _review_evidence_url(legacy_list_proof):
            blockers.append("legacy_public_installation_lists_guard_proof_url_required")
        if not _review_evidence_url(legacy_calculate_proof):
            blockers.append("legacy_public_calculate_guard_proof_url_required")
        if not _review_evidence_url(legacy_tariff_calculate_proof):
            blockers.append("legacy_public_tariff_calculate_guard_proof_url_required")
        if any(tenant.demo_read_only for tenant in active_partners) and not include_demo_reset:
            blockers.append("explicit_include_demo_reset_required")

        scopes: list[tuple[TenantScope, list[ServiceTariff]]] = []
        scope_reports: list[dict[str, Any]] = []
        for tenant in system + active_partners:
            tenant_defaults = defaults.get(tenant.id, [])
            if len(tenant_defaults) != 1:
                blockers.append(f"tenant_{tenant.id}_needs_one_default_storefront")
                continue
            storefront = tenant_defaults[0]
            scope = TenantScope(tenant_id=int(tenant.id),
                                storefront_id=int(storefront.id),
                                is_system=tenant.is_system,
                                demo_read_only=tenant.demo_read_only)
            tariffs, rates, options, book = await cls._scope_rows(session, scope, lock=lock)
            site_settings = await StorefrontSettingsService.get_settings(
                session, tenant_scope=scope,
            )
            installation_enabled = any(
                item.key == "installation" and item.enabled
                for item in site_settings.services
            )
            old = [_tariff_snapshot(row) for row in tariffs]
            report = {
                "tenant_id": tenant.id, "tenant_slug": tenant.slug,
                "storefront_id": storefront.id, "storefront_status": storefront.status,
                "is_system": tenant.is_system, "demo_read_only": tenant.demo_read_only,
                "settings_version": site_settings.version,
                "installation_direction_enabled": installation_enabled,
                "old_installation_drafts": old,
                "old_installation_drafts_digest": _digest(old),
                "legacy_public_rates": [{
                    "id": row.id, "category": row.category,
                    "power_range": row.power_range, "base_price": row.base_price,
                    "included_pipe_meters": row.included_pipe_meters,
                    "extra_pipe_price": row.extra_pipe_price,
                    "is_fixed": row.is_fixed,
                    "price_comparison": _candidate_comparison(
                        category=row.category, power_range=row.power_range,
                        old_base_price=row.base_price,
                        old_extra_meter_price=row.extra_pipe_price,
                    ),
                } for row in rates],
                "legacy_public_options": [{
                    "id": row.id, "slug": row.slug, "title": row.title,
                    "base_price": row.base_price, "is_active": row.is_active,
                } for row in options],
                "latest_book": ({"id": book.id, "revision": book.revision,
                                 "fingerprint": book.fingerprint,
                                 "prices": [{
                                     "code": entry.get("code"),
                                     "base_price": entry.get("base_price"),
                                     "route_extra_price": next((
                                         rule.get("unit_price") for rule in entry.get("rules", [])
                                         if rule.get("code") == "route.extra_m"
                                     ), None),
                                 } for entry in book.entries]}
                                if book else None),
                "old_to_new": [{
                    "old_id": row.id, "old_code": row.installation_code,
                    "old_label": row.selector_label, "old_base_price": row.base_price,
                    "old_route_meters": row.included_route_meters,
                    "old_rule_prices": {rule.component_code or f"rule:{rule.id}": rule.unit_price
                                        for rule in row.rules},
                    "action": "retire_active_draft" if row.is_active else "retain_inactive",
                    "price_comparison": _candidate_comparison(
                        category=row.category, power_range=row.power_range,
                        old_base_price=row.base_price,
                        old_extra_meter_price=next((rule.unit_price for rule in row.rules
                                                    if rule.component_code == "route.extra_m"), None),
                        work_kind=(row.installation_match or {}).get("work_kind", "standard"),
                        match=row.installation_match,
                    ),
                    "reason": "old matcher/coverage is not assumed equivalent to the approved grid",
                } for row in tariffs],
                "customer_after_apply": (
                    "published_book_v2; legacy rows remain stored; unsupported multi/prelaid "
                    "product checkout requires quote until its UI is enabled"
                    if installation_enabled else "installation_direction_disabled_returns_unavailable"
                ),
            }
            scope_reports.append(report)
            scopes.append((scope, tariffs))
            if tenant.is_system and any(row.tenant_id == tenant.id for row in tariffs):
                blockers.append("system_owned_installation_rows_need_manual_review")
            if storefront.status == "disabled":
                blockers.append(f"tenant_{tenant.id}_default_storefront_disabled")

        desired = _desired_snapshot()
        try:
            _validate_seed_against_installed_contract()
        except Exception as exc:
            blockers.append(f"seed_contract_validation_failed:{type(exc).__name__}")
        if len(desired) != 20:
            blockers.append("unexpected_seed_coverage")
        if len({row["tariff"]["installation_code"] for row in desired}) != len(desired):
            blockers.append("duplicate_seed_code")
        # A complete already-applied grid is not silently reset again. A new
        # explicit operation needs a new approved seed version and fresh plan.
        if scopes and all(
            {row.installation_code for row in tariffs if row.is_active}
            == {item["tariff"]["installation_code"] for item in desired}
            for _, tariffs in scopes
        ):
            blockers.append("approved_grid_already_active")
        report = {
            "operation": "installation_grid_rollout_v1",
            "seed_version": SEED_VERSION,
            "seed_digest": _digest(desired),
            "desired_installation_drafts": desired,
            "discovered_active_partner_slugs": list(discovered),
            "expected_partner_slugs": list(expected_partner_slugs),
            "backend_release_commit": backend_release_commit,
            "backend_image_digest": backend_image_digest,
            "excluded_disabled_tenants": [{"id": row.id, "slug": row.slug}
                                          for row in tenants if row.status != "active"],
            "web_v2_commit": web_v2_commit,
            "web_v2_proof": web_v2_proof,
            "manager_editor_proof": manager_editor_proof,
            "legacy_list_proof": legacy_list_proof,
            "legacy_calculate_proof": legacy_calculate_proof,
            "legacy_tariff_calculate_proof": legacy_tariff_calculate_proof,
            "include_demo_reset": include_demo_reset,
            "scopes": scope_reports,
            "blockers": sorted(set(blockers)),
            "history_policy": "Old drafts/rules stay inactive; immutable books and estimates stay unchanged. "
                              "A restoration of accepted prices requires another reviewed publication.",
            "read_path_inventory": {
                "new_authority": "published InstallationPriceBook for resolve/preview/accepted checkout",
                "legacy_public_lists": "/api/v1/installation-rates, /api/v1/services/options, "
                                       "/api/v1/content/services; installation prices must be guarded after web v2",
                "legacy_public_calculation": "InstallationPricingService; must reject obsolete with_installation input after web v2",
                "legacy_public_tariff_calculation": "/api/v1/service-pricing/calculate; must not present typed installation drafts as exact multi/shared-hole prices",
                "legacy_manager_editor": "/manager/installation-rates; must be read-only or clearly retired",
                "unchanged": "non-installation tariffs, immutable quotes/orders/documents",
            },
        }
        report["plan_digest"] = _digest(report)
        return report, scopes

    @classmethod
    async def apply(
        cls, session: AsyncSession, *, expected_partner_slugs: tuple[str, ...],
        backend_release_commit: str, backend_image_digest: str,
        web_v2_commit: str, web_v2_proof: str,
        manager_editor_proof: str, legacy_list_proof: str,
        legacy_calculate_proof: str,
        legacy_tariff_calculate_proof: str,
        include_demo_reset: bool, plan_token: str,
    ) -> dict[str, Any]:
        verified = InstallationGridPlanToken.verify(plan_token)
        report, scopes = await cls.plan(
            session, expected_partner_slugs=expected_partner_slugs,
            backend_release_commit=backend_release_commit,
            backend_image_digest=backend_image_digest,
            web_v2_commit=web_v2_commit, web_v2_proof=web_v2_proof,
            manager_editor_proof=manager_editor_proof,
            legacy_list_proof=legacy_list_proof,
            legacy_calculate_proof=legacy_calculate_proof,
            legacy_tariff_calculate_proof=legacy_tariff_calculate_proof,
            include_demo_reset=include_demo_reset, lock=True,
        )
        if not hmac.compare_digest(verified.plan_digest, report["plan_digest"]):
            raise StorefrontOnboardingBlockedError("State changed; review a fresh plan")
        if report["blockers"]:
            raise StorefrontOnboardingBlockedError("; ".join(report["blockers"]))
        if not scopes or not scopes[0][0].is_system:
            raise StorefrontOnboardingBlockedError("Canonical scope is missing")

        created: dict[str, ServiceTariff] = {}
        created_rules: dict[tuple[str, str], ServiceTariffRule] = {}
        summaries: list[dict[str, Any]] = []
        for scope, old_tariffs in scopes:
            before = [_tariff_snapshot(row) for row in old_tariffs]
            for old in old_tariffs:
                if old.is_active:
                    old.is_active = False
                    session.add(old)
            await session.flush()
            new_rows: list[ServiceTariff] = []
            for index, spec in enumerate(canonical_installation_grid()):
                source = None if scope.is_system else created[spec.code]
                tariff = ServiceTariff(
                    tenant_id=None if scope.is_system else scope.tenant_id,
                    source_tariff_id=None if source is None else source.id,
                    sort_order=index * 10,
                    **spec.fields(),
                )
                session.add(tariff)
                await session.flush()
                if scope.is_system:
                    created[spec.code] = tariff
                for rule_index, rule in enumerate(spec.rules):
                    source_rule = (None if scope.is_system else
                                   created_rules[(spec.code, rule.code)])
                    new_rule = ServiceTariffRule(
                        tariff_id=int(tariff.id), sort_order=rule_index * 10,
                        source_rule_id=None if source_rule is None else source_rule.id,
                        **rule.fields(),
                    )
                    session.add(new_rule)
                    await session.flush()
                    if scope.is_system:
                        created_rules[(spec.code, rule.code)] = new_rule
                new_rows.append(tariff)
            await session.flush()
            published = await InstallationPriceBookService.publish(
                session, scope, actor="system:installation-grid-rollout", commit=False,
            )
            session.add(TenantAuditEvent(
                tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
                actor_username="system:installation-grid-rollout",
                action="installation_grid.reviewed_reset_published",
                entity_type="installation_price_book", entity_id=published.price_book_id,
                request_id=current_request_id(),
                change_set={
                    "plan_digest": report["plan_digest"],
                    "seed_version": SEED_VERSION,
                    "before_installation_drafts": before,
                    "retained_inactive_ids": [row.id for row in old_tariffs],
                    "new_active_ids": [row.id for row in new_rows],
                    "book_revision": published.revision,
                    "book_fingerprint": published.fingerprint,
                },
            ))
            summaries.append({
                "tenant_id": scope.tenant_id, "storefront_id": scope.storefront_id,
                "retired_drafts": sum(row["is_active"] for row in before),
                "new_drafts": len(new_rows), "new_price_book_id": published.price_book_id,
                "new_revision": published.revision,
                "new_fingerprint": published.fingerprint,
            })
        await session.flush()
        return {"status": "applied", "plan_digest": report["plan_digest"],
                "seed_version": SEED_VERSION, "scopes": summaries}
