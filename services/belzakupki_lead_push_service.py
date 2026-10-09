"""Independent inbound transport, using the native importer persistence contract."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.api_write_fence import ApiWriteFenceMiddleware
from core.config import settings
from models import Tenant, Storefront
from schemas_belzakupki_intake import NativeOpportunity, TenderLeadPushResult
from services.belzakupki_import_service import BelzakupkiImportResult, BelzakupkiImportService
from services.tenant_scope_service import SystemTenantScopeResolver, TenantScopeResolutionError

logger = logging.getLogger(__name__)


class LeadPushUnavailable(RuntimeError):
    pass


class LeadPushScopeDenied(RuntimeError):
    pass


class BelzakupkiLeadPushService:
    @staticmethod
    def check_configuration() -> None:
        if not (settings.BELZAKUPKI_LEAD_PUSH_ENABLED
                and settings.BELZAKUPKI_LEAD_PUSH_API_KEY
                and settings.BELZAKUPKI_IMPORT_TENANT_SLUG.strip()
                and settings.BELZAKUPKI_IMPORT_STOREFRONT_SLUG.strip()):
            raise LeadPushUnavailable("Tender lead push is unavailable")
        if not ApiWriteFenceMiddleware._write_traffic_enabled():
            raise LeadPushUnavailable("Tender lead push is unavailable")

    @classmethod
    async def push(cls, session: AsyncSession, opportunity: NativeOpportunity, *, now: datetime | None = None) -> TenderLeadPushResult:
        cls.check_configuration()
        item = opportunity.model_dump(mode="json")
        importer = BelzakupkiImportService
        result = BelzakupkiImportResult()
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("Intake clock must be timezone-aware")
        async with session.begin():
            cls.check_configuration()
            if session.bind.dialect.name == "postgresql":
                writable = (await session.execute(text(
                    "SELECT NOT pg_is_in_recovery() AND current_setting('transaction_read_only') = 'off'"
                ))).scalar_one()
                if not writable:
                    raise LeadPushUnavailable("Tender lead push is unavailable")
            try:
                scope = await SystemTenantScopeResolver.resolve(
                    session, tenant_slug=settings.BELZAKUPKI_IMPORT_TENANT_SLUG.strip(),
                    storefront_slug=settings.BELZAKUPKI_IMPORT_STOREFRONT_SLUG.strip(),
                )
            except TenantScopeResolutionError:
                raise LeadPushScopeDenied("Tender lead destination is unavailable") from None
            # Same lock order as pull; acquiring this lock never advances its cursor.
            await importer._locked_checkpoint(session, tenant_scope=scope)
            target = (await session.execute(select(Tenant, Storefront).join(
                Storefront, Storefront.tenant_id == Tenant.id
            ).where(Tenant.id == scope.tenant_id, Storefront.id == scope.storefront_id)
                .with_for_update(read=True))).one_or_none()
            if (target is None or target[0].status != "active" or target[1].status != "active"
                    or target[0].demo_read_only or not target[0].is_system or not target[1].is_default
                    or target[0].slug != settings.BELZAKUPKI_IMPORT_TENANT_SLUG.strip()
                    or target[1].slug != settings.BELZAKUPKI_IMPORT_STOREFRONT_SLUG.strip()):
                raise LeadPushScopeDenied("Tender lead destination is unavailable")
            await importer._upsert_opportunity(session, tenant_scope=scope, item=item, result=result,
                                               allow_create=importer._is_accepted(item, now=current_time))
            source, external_id = importer._external_identity(item)
            order = await importer._find_order(session, tenant_scope=scope,
                fingerprint=importer._order_fingerprint(source=source, external_id=external_id))
            response = TenderLeadPushResult(order_id=order.id if order else None,
                outcome=next(name for name in ("created", "updated", "unchanged", "skipped")
                             if getattr(result, name)), source=source, external_id=external_id)
        from services.jev_shadow_service import JevShadowService
        await JevShadowService.enqueue_tenders(tenant_scope=scope, items=[item])
        logger.info("BELZAKUPKI_LEAD_PUSH outcome=%s", response.outcome)
        return response
