"""Reviewed creation of one domainless private teaching tenant and CRM fixture."""

from __future__ import annotations

import hashlib
import hmac
import json

from sqlalchemy import text
from sqlmodel import select

from core.config import settings
from core.request_context import current_request_id
from models import (
    DocumentLegalEntity, Product, Storefront, StorefrontDomain, Tenant,
    TenantAuditEvent, TenantCatalogGrant, TenantOffer,
)
from services.catalog_decision_projection import CatalogDecisionQueryService
from services.storefront_onboarding_plan_token import StorefrontOnboardingPlanToken
from services.tenant_training_setup_service import (
    TenantTrainingPlanToken, TenantTrainingSetupBlockedError, TenantTrainingSetupService,
)


SLUG = "training-kitlane"
DISPLAY_NAME = "[ОБУЧЕНИЕ] Учебная компания Kitlane"
ACTION = "tenant_training.private_bootstrap"


class TenantTrainingBootstrapToken(StorefrontOnboardingPlanToken):
    @staticmethod
    def _key():
        return hashlib.sha256(
            b"mvn:tenant-training-bootstrap:plan-token:v1\0" + settings.SECRET_KEY.encode()
        ).digest()


class TenantTrainingBootstrapService:
    @classmethod
    async def plan(cls, session, *, product_ids: list[int], lock=False):
        if len(product_ids) != 2 or len(set(product_ids)) != 2 or any(type(i) is not int or i <= 0 for i in product_ids):
            raise TenantTrainingSetupBlockedError("Exactly two distinct positive product IDs are required")
        if lock and session.get_bind().dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                                  {"key": f"mvn:{ACTION}:{SLUG}"})
        tenant_stmt = select(Tenant).where(Tenant.slug == SLUG)
        product_stmt = select(Product).where(Product.id.in_(product_ids)).order_by(Product.id)
        if lock:
            tenant_stmt = tenant_stmt.with_for_update()
            product_stmt = product_stmt.with_for_update()
        tenant = (await session.execute(tenant_stmt)).scalar_one_or_none()
        products = list((await session.execute(product_stmt)).scalars())
        eligible_ids = await CatalogDecisionQueryService.eligible_system_product_ids(session, product_ids)
        blockers = []
        selected = [dict(product_id=p.id, title=p.title, slug=p.slug,
                         product_kind=p.product_kind, is_published=p.is_published,
                         retail_price=p.price, created_at=p.created_at.isoformat() if p.created_at else None)
                    for p in products]
        if len(products) != 2 or any(not p.is_published or p.price <= 0 or p.product_kind != "complete_split_system" for p in products):
            blockers.append("exact two published complete split systems with positive public retail prices are required")
        if eligible_ids != set(product_ids):
            blockers.append("both reviewed products must pass current complete-split selection admission")
        receipt = None
        target = None
        fixture = None
        grant_state = None
        if tenant:
            receipts = list((await session.execute(select(TenantAuditEvent).where(
                TenantAuditEvent.tenant_id == tenant.id, TenantAuditEvent.action == ACTION,
            ))).scalars())
            if len(receipts) != 1:
                blockers.append("existing tenant lacks one exact bootstrap receipt; never adopt existing tenants")
            else:
                receipt = receipts[0]
                target = receipt.change_set.get("target", {})
                recorded_products = receipt.change_set.get("product_ids")
                if recorded_products != sorted(product_ids):
                    blockers.append("reviewed product allowlist conflicts with bootstrap receipt")
                storefront = await session.get(Storefront, target.get("storefront_id", -1))
                issuer = await session.get(DocumentLegalEntity, target.get("legal_entity_id", -1))
                grant = await session.get(TenantCatalogGrant, target.get("catalog_grant_id", -1))
                if (tenant.is_system or tenant.kind != "independent_seller" or tenant.status != "active"
                        or tenant.demo_read_only or not storefront or storefront.tenant_id != tenant.id
                        or storefront.status != "active" or not storefront.is_default
                        or not issuer or issuer.tenant_id != tenant.id or issuer.status != "active"):
                    blockers.append("private bootstrap target identity or active policy changed")
                if (not grant or grant.tenant_id != tenant.id
                        or not storefront or grant.storefront_id != storefront.id
                        or grant.status != "active" or grant.owner_type != "system"
                        or grant.mode != "all_published" or grant.price_policy != "inherit_master"):
                    blockers.append("reviewed system-owned scoped grant identity or policy changed")
                if grant:
                    grant_state = {"id": grant.id, "tenant_id": grant.tenant_id,
                        "storefront_id": grant.storefront_id, "mode": grant.mode,
                        "price_policy": grant.price_policy, "owner_type": grant.owner_type,
                        "status": grant.status, "revision": grant.revision,
                        "updated_at": grant.updated_at.isoformat()}
                domains = (await session.execute(select(StorefrontDomain.id)
                    .join(Storefront, Storefront.id == StorefrontDomain.storefront_id)
                    .where(Storefront.tenant_id == tenant.id))).first()
                if domains:
                    blockers.append("private teaching tenant must have no public domain rows")
                if storefront:
                    fixture = await TenantTrainingSetupService.plan(session, tenant_id=int(tenant.id),
                        storefront_id=int(storefront.id), tenant_slug=SLUG, lock=lock)
                    blockers.extend(fixture["blockers"])
                    if fixture["status"] != "already_created":
                        blockers.append("teaching fixture receipt missing; no automatic reset")
                actual_offers = list((await session.execute(select(TenantOffer).where(
                    TenantOffer.tenant_id == tenant.id,
                ))).scalars())
                if ({o.product_id for o in actual_offers} != set(product_ids) or len(actual_offers) != 2
                        or not grant or any(o.catalog_grant_id != grant.id for o in actual_offers)):
                    blockers.append("private offer allowlist changed; no automatic reset")
        report = {
            "operation": ACTION, "status": "blocked" if blockers else "already_created" if receipt else "planned",
            "tenant_slug": SLUG, "display_name": DISPLAY_NAME, "target": target,
            "product_ids": sorted(product_ids), "chosen_products": selected,
            "selection_eligible_product_ids": sorted(eligible_ids),
            "existing_tenant_id": tenant.id if tenant else None,
            "bootstrap_receipt_id": receipt.id if receipt else None,
            "grant_policy": {"owner_type": "system", "mode": "all_published",
                "price_policy": "inherit_master", "status": "active", "revision": 1,
                "materialized_product_ids": sorted(product_ids), "run_catalog_sync": False,
                "note": "Current access requires these two materialized offers. A later reviewed catalog sync would expand this grant."},
            "grant_state": grant_state,
            "fixture_digest": fixture["plan_digest"] if fixture else None,
            "planned_records": {"tenants": 1, "active_default_storefronts": 1,
                "materialized_offers": 2, "system_owned_catalog_grants": 1,
                "synthetic_issuers": 1, "customers": 2,
                "new_leads": 1, "negotiation_orders": 2, "draft_proposals": 4, "product_lines": 4,
                "domains": 0, "catalog_sync_runs": 0, "staff_accounts": 0, "business_documents": 0,
                "notifications": 0, "outbox_events": 0},
            "remaining_readiness": ["Provision private scoped owner through reviewed tenant-manager workflow",
                "Import tenant-owned synthetic native DOCX templates with reviewed native bundle procedure",
                "Configure teaching-only document numbering and verify document preflight"],
            "blockers": blockers,
        }
        report["plan_digest"] = hashlib.sha256(json.dumps(report, ensure_ascii=False,
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return report

    @classmethod
    async def execute(cls, session, *, product_ids, plan_token):
        verified = TenantTrainingBootstrapToken.verify(plan_token)
        report = await cls.plan(session, product_ids=product_ids, lock=True)
        if not hmac.compare_digest(verified.plan_digest, report["plan_digest"]):
            raise TenantTrainingSetupBlockedError("State changed; review a fresh bootstrap plan")
        if report["blockers"]:
            raise TenantTrainingSetupBlockedError("; ".join(report["blockers"]))
        if report["status"] == "already_created":
            return {"status": "already_created", "target": report["target"]}
        tenant = Tenant(slug=SLUG, display_name=DISPLAY_NAME, kind="independent_seller",
                        status="active", is_system=False, demo_read_only=False)
        session.add(tenant)
        await session.flush()
        storefront = Storefront(tenant_id=int(tenant.id), slug="main", display_name=DISPLAY_NAME,
                                city="Минск (учебный пример)", status="active", is_default=True)
        session.add(storefront)
        issuer = DocumentLegalEntity(tenant_id=int(tenant.id), slug="training",
            display_name=DISPLAY_NAME, legal_name='[ОБУЧЕНИЕ] ООО «Учебная компания Kitlane»',
            unp=None, status="active", is_default=True,
            requisites={"city": "Минск (учебный пример)",
                        "legal_address": "[ОБУЧЕНИЕ] ул. Примерная, 10",
                        "email": "training.seller@example.invalid",
                        "signing_mode": "statutory_body", "signer_position": "Директор (учебный пример)",
                        "signer_name": "Иван Примеров (учебный пример)", "acting_basis": "Устав (учебный пример)"})
        session.add(issuer)
        await session.flush()
        grant = TenantCatalogGrant(tenant_id=int(tenant.id), storefront_id=int(storefront.id),
            mode="all_published", price_policy="inherit_master", owner_type="system",
            status="active", revision=1, created_by_username="system:tenant-training-bootstrap",
            updated_by_username="system:tenant-training-bootstrap")
        session.add(grant)
        await session.flush()
        for product in report["chosen_products"]:
            session.add(TenantOffer(tenant_id=int(tenant.id), storefront_id=int(storefront.id),
                product_id=product["product_id"], price=product["retail_price"], status="active",
                is_published=True, price_source="inherited_master", catalog_grant_id=int(grant.id),
                created_by_username="system:tenant-training-bootstrap",
                updated_by_username="system:tenant-training-bootstrap"))
        await session.flush()
        fixture_args = dict(tenant_id=int(tenant.id), storefront_id=int(storefront.id), tenant_slug=SLUG)
        fixture_plan = await TenantTrainingSetupService.plan(session, **fixture_args)
        fixture_result = await TenantTrainingSetupService.execute(session, **fixture_args,
            plan_token=TenantTrainingPlanToken.issue(plan_digest=fixture_plan["plan_digest"]))
        target = {**fixture_args, "legal_entity_id": int(issuer.id), "catalog_grant_id": int(grant.id)}
        session.add(TenantAuditEvent(tenant_id=int(tenant.id), storefront_id=int(storefront.id),
            actor_username="system:tenant-training-bootstrap", action=ACTION, entity_type="tenant",
            entity_id=int(tenant.id), request_id=current_request_id(), change_set={
                "plan_digest": report["plan_digest"], "target": target,
                "product_ids": sorted(product_ids), "records": fixture_result["records"],
            }))
        await session.flush()
        return {"status": "created", "target": target, "records": fixture_result["records"],
                "remaining_readiness": report["remaining_readiness"]}
