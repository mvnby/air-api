"""Reviewed initial settings and detached prices for one existing partner."""

import hashlib
import hmac
import json

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.request_context import current_request_id
from models import Storefront, Tenant, TenantAuditEvent
from models.tenancy import TenantScope
from schemas_storefront_settings import (
    ServiceDirection, StorefrontSettingsPayload, StorefrontSiteSettings,
    default_service_directions,
)
from services.service_catalog_template_service import ServiceCatalogTemplateService
from services.storefront_onboarding_plan_token import StorefrontOnboardingPlanToken
from services.storefront_onboarding_state import StorefrontOnboardingBlockedError
from services.storefront_settings_service import StorefrontSettingsService


class PartnerSiteSetupManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    storefront_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    site: StorefrontSiteSettings
    enabled_services: list[ServiceDirection]

    def settings_payload(self) -> StorefrontSettingsPayload:
        directions = default_service_directions(enabled=False)
        for item in directions:
            item.enabled = item.key in self.enabled_services
        return StorefrontSettingsPayload(site=self.site, services=directions, version=0)


class PartnerSiteSetupPlanToken(StorefrontOnboardingPlanToken):
    @staticmethod
    def _key() -> bytes:
        return hashlib.sha256(
            b"mvn:partner-site-setup:plan-token:v1\0"
            + settings.SECRET_KEY.encode("utf-8")
        ).digest()


class PartnerSiteSetupService:
    @staticmethod
    async def plan(
        session: AsyncSession, manifest: PartnerSiteSetupManifest, *, lock=False,
    ) -> tuple[dict, TenantScope]:
        statement = select(Tenant, Storefront).join(
            Storefront, Storefront.tenant_id == Tenant.id,
        ).where(Tenant.slug == manifest.tenant_slug,
                Storefront.slug == manifest.storefront_slug)
        if lock:
            statement = statement.with_for_update()
        pair = (await session.execute(statement)).first()
        if pair is None:
            raise StorefrontOnboardingBlockedError("Bootstrap the exact partner first")
        tenant, storefront = pair
        if tenant.is_system or tenant.status != "active" or storefront.status == "disabled":
            raise StorefrontOnboardingBlockedError("Only an enabled non-system partner is supported")
        scope = TenantScope(tenant_id=tenant.id, storefront_id=storefront.id)
        current = await StorefrontSettingsService.get_settings(session, tenant_scope=scope)
        template = await ServiceCatalogTemplateService.preview(session, tenant_scope=scope)
        blockers = []
        if current.version != 0:
            blockers.append("Settings already initialized; use Manager to edit")
        if not template.can_clone:
            blockers.append("Partner already has service data; no overwrite is permitted")
        report = {
            "operation": "partner_site_initial_setup_v1",
            "tenant_id": tenant.id,
            "storefront_id": storefront.id,
            "manifest": manifest.model_dump(mode="json"),
            "current_settings_version": current.version,
            "template": template.model_dump(mode="json"),
            "blockers": blockers,
        }
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        report["plan_digest"] = hashlib.sha256(encoded.encode()).hexdigest()
        return report, scope

    @classmethod
    async def execute(cls, session, manifest, *, plan_token: str) -> dict:
        verified = PartnerSiteSetupPlanToken.verify(plan_token)
        report, scope = await cls.plan(session, manifest, lock=True)
        if not hmac.compare_digest(verified.plan_digest, report["plan_digest"]):
            raise StorefrontOnboardingBlockedError("State changed; review a fresh plan")
        if report["blockers"]:
            raise StorefrontOnboardingBlockedError("; ".join(report["blockers"]))
        # Caller owns an explicit transaction, so prices and settings commit together.
        cloned = await ServiceCatalogTemplateService.clone(
            session, tenant_scope=scope,
            expected_fingerprint=report["template"]["source_fingerprint"],
        )
        saved = await StorefrontSettingsService.update_settings(
            session, tenant_scope=scope, payload=manifest.settings_payload(),
            actor_username="system:partner-site-setup", actor_staff_user_id=None,
            commit=False,
        )
        session.add(TenantAuditEvent(
            tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
            actor_username="system:partner-site-setup", action="service_catalog.template_cloned",
            entity_type="storefront", entity_id=scope.storefront_id,
            request_id=current_request_id(),
            change_set={"plan_digest": report["plan_digest"], **cloned.model_dump()},
        ))
        await session.flush()
        return {"status": "initialized", "tenant_id": scope.tenant_id,
                "storefront_id": scope.storefront_id, "settings_version": saved.version,
                "catalog": cloned.model_dump()}
