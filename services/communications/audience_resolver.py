from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from services.communications.contracts import (
    CommunicationRecipientV1,
    CommunicationTemplatePlanV1,
    TelegramCanaryRequestedPayloadV1,
)
from services.communications.recipient_directory import (
    InstallationEstimateOwnerRecipientDirectory,
    ManagementRecipientDirectory,
    OperationsCanaryRecipientDirectory,
    TenantWebsiteManagementRecipientDirectory,
)
from services.communications.staff_task_contracts import (
    StaffTaskNotificationPayloadV1,
)
from services.communications.staff_task_recipient_directory import (
    StaffTaskRecipientDirectory,
)
from services.communications.template_registry import UnsupportedCommunicationEvent


class CommunicationAudienceResolver:
    @staticmethod
    async def list_telegram(
        session: AsyncSession,
        *,
        plan: CommunicationTemplatePlanV1,
    ) -> list[CommunicationRecipientV1]:
        if plan.audience == "management":
            from models import Order, Lead
            from services.tenant_scope_service import (
                SystemTenantScopeResolver,
                TenantScopeResolutionError,
            )

            order_id = plan.render_context.get("order_id")
            lead_id = plan.render_context.get("lead_id")
            from sqlmodel import select

            model, identity = (Order, order_id) if order_id else (Lead, lead_id)
            entity = (
                (
                    await session.execute(
                        select(model.tenant_id, model.storefront_id).where(
                            model.id == identity
                        )
                    )
                ).first()
                if identity
                else None
            )
            if entity is None:
                return []
            try:
                canonical = await SystemTenantScopeResolver.resolve(session)
            except TenantScopeResolutionError:
                return []
            # These two legacy templates are explicitly canonical-only. Partner
            # events use tenant_website_management, never global-role routing.
            if (entity.tenant_id, entity.storefront_id) != (
                canonical.tenant_id,
                canonical.storefront_id,
            ):
                return []
            return await ManagementRecipientDirectory.list_telegram(session)
        if plan.audience == "installation_estimate_owners":
            return await InstallationEstimateOwnerRecipientDirectory.list_telegram(
                session
            )
        if plan.audience == "tenant_website_management":
            return await TenantWebsiteManagementRecipientDirectory.list_telegram(
                session,
                tenant_id=int(plan.render_context["tenant_id"]),
                storefront_id=int(plan.render_context["storefront_id"]),
            )
        if plan.audience == "operations_canary":
            payload = TelegramCanaryRequestedPayloadV1.model_validate(
                plan.render_context
            )
            return await OperationsCanaryRecipientDirectory.list_telegram(
                session,
                required_recipient_keys=payload.recipient_keys,
            )
        if plan.audience == "staff_assignee":
            payload = StaffTaskNotificationPayloadV1.model_validate(plan.render_context)
            return await StaffTaskRecipientDirectory.list_telegram(
                session,
                payload=payload,
            )
        raise UnsupportedCommunicationEvent(
            f"Unsupported communication audience {plan.audience!r}"
        )
