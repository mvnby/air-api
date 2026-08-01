from __future__ import annotations

from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    CommunicationDelivery,
    IntegrationOutboxEvent,
    StaffUser,
    Storefront,
    TenantMembership,
)
from services.communications.audience_resolver import CommunicationAudienceResolver
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.contracts import CommunicationTemplatePlanV1
from services.communications.delivery_materializer import (
    CommunicationDeliveryMaterializer,
)
from services.communications.delivery_service import ClaimedCommunicationDelivery
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.recipient_directory import (
    TenantWebsiteManagementRecipientDirectory,
)
from services.communications.scope_routing import (
    recipients_for_scope,
    routing_snapshot,
)
from services.communications.templates import TemplateRenderError
from services.communications.template_registry import (
    UnsupportedCommunicationEvent,
    WebsiteTemplateRegistry,
)
from services.communications.website_canary_target import (
    WebsiteCanaryScopeMismatch,
    WebsiteCanaryTarget,
)
from services.staff_user_service import StaffUserService


class WebsiteCanaryProviderBoundaryRejected(CommunicationsCanarySafetyError):
    """The selected website recipient lost authorization before provider I/O."""


def _reject() -> NoReturn:
    raise WebsiteCanaryProviderBoundaryRejected(
        "website_canary_provider_boundary_rejected"
    )


def _lock(statement, session: AsyncSession):
    if session.get_bind().dialect.name == "postgresql":
        return statement.with_for_update()
    return statement


async def recipient_is_current(
    session: AsyncSession,
    *,
    scope: CommunicationProcessingScope,
    claim: ClaimedCommunicationDelivery,
    plan: CommunicationTemplatePlanV1,
) -> bool:
    """Perform the early advisory recipient check before the final DB fence."""

    try:
        recipients = await CommunicationAudienceResolver.list_telegram(
            session,
            plan=plan,
        )
        recipients = recipients_for_scope(
            scope=scope,
            recipients=recipients,
            event_id=claim.event_id,
            template_key=claim.template_key,
        )
    except (
        CommunicationsCanarySafetyError,
        TemplateRenderError,
        UnsupportedCommunicationEvent,
        ValueError,
    ):
        return False
    if plan.audience in {
        "installation_estimate_owners",
        "tenant_website_management",
    }:
        deliveries = list(
            (
                await session.execute(
                    select(CommunicationDelivery).where(
                        CommunicationDelivery.event_id == claim.event_id,
                        CommunicationDelivery.channel == claim.channel,
                        CommunicationDelivery.template_key == claim.template_key,
                        CommunicationDelivery.template_version
                        == claim.template_version,
                    )
                )
            ).scalars()
        )
        if {
            (delivery.recipient_key, delivery.destination)
            for delivery in deliveries
        } != routing_snapshot(recipients):
            return False
    return any(
        recipient.recipient_key == claim.recipient_key
        and recipient.destination == claim.destination
        and recipient.channel == claim.channel
        for recipient in recipients
    )


def _assert_claim_snapshot(
    *,
    claim: ClaimedCommunicationDelivery,
    delivery: CommunicationDelivery,
) -> None:
    if (
        delivery.delivery_id != claim.delivery_id
        or delivery.event_id != claim.event_id
        or delivery.channel != claim.channel
        or delivery.recipient_key != claim.recipient_key
        or delivery.destination != claim.destination
        or delivery.template_key != claim.template_key
        or int(delivery.template_version) != int(claim.template_version)
        or dict(delivery.render_context or {}) != claim.render_context_dict()
        or int(delivery.attempts) != int(claim.attempts)
        or int(delivery.max_attempts) != int(claim.max_attempts)
    ):
        _reject()


async def lock_exact_website_recipient(
    session: AsyncSession,
    *,
    target: WebsiteCanaryTarget,
) -> str:
    """Lock the exact storefront, staff user, and membership authorization."""

    try:
        staff_user_id = int(target.recipient_key.removeprefix("staff:"))
    except ValueError:
        _reject()
    storefront = (
        await session.execute(
            _lock(
                select(Storefront).where(
                    Storefront.id == target.storefront_id,
                    Storefront.tenant_id == target.tenant_id,
                ),
                session,
            )
        )
    ).scalar_one_or_none()
    staff_user = (
        await session.execute(
            _lock(select(StaffUser).where(StaffUser.id == staff_user_id), session)
        )
    ).scalar_one_or_none()
    membership = (
        await session.execute(
            _lock(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == target.tenant_id,
                    TenantMembership.staff_user_id == staff_user_id,
                ),
                session,
            )
        )
    ).scalar_one_or_none()
    if (
        storefront is None
        or staff_user is None
        or membership is None
        or staff_user.status != StaffUserService.STATUS_ACTIVE
        or membership.status != "active"
        or membership.role
        not in TenantWebsiteManagementRecipientDirectory.ELIGIBLE_MEMBERSHIP_ROLES
        or staff_user.telegram_id is None
        or int(staff_user.telegram_id) <= 0
        or f"staff:{int(staff_user.id or 0)}" != target.recipient_key
    ):
        _reject()
    return str(int(staff_user.telegram_id))


async def authorize_website_provider_boundary(
    session: AsyncSession,
    *,
    scope: CommunicationProcessingScope,
    claim: ClaimedCommunicationDelivery,
    delivery: CommunicationDelivery,
) -> None:
    """Lock and authorize the exact website recipient at the provider boundary."""

    target = scope.website_canary_target
    if target is None:
        return
    _assert_claim_snapshot(claim=claim, delivery=delivery)
    event = (
        await session.execute(
            _lock(
                select(IntegrationOutboxEvent).where(
                    IntegrationOutboxEvent.event_id == target.event_id
                ),
                session,
            )
        )
    ).scalar_one_or_none()
    if event is None or event.status != "published":
        _reject()
    try:
        plan = WebsiteTemplateRegistry.plan(event)
        WebsiteTemplateRegistry.render(plan)
        target.assert_event_plan(
            event_id=event.event_id,
            event_type=event.event_type,
            template_key=plan.template_key,
            audience=plan.audience,
            render_context=plan.render_context,
        )
    except (
        TemplateRenderError,
        UnsupportedCommunicationEvent,
        WebsiteCanaryScopeMismatch,
        ValueError,
    ):
        _reject()
    expected_delivery_id = CommunicationDeliveryMaterializer.build_delivery_id(
        event_id=target.event_id,
        channel=plan.channel,
        recipient_key=target.recipient_key,
        template_version=plan.template_version,
    )
    if (
        delivery.delivery_id != expected_delivery_id
        or delivery.event_id != target.event_id
        or delivery.channel != "telegram"
        or delivery.channel != plan.channel
        or delivery.recipient_key != target.recipient_key
        or delivery.template_key != target.template_key
        or delivery.template_key != plan.template_key
        or int(delivery.template_version) != int(plan.template_version)
        or dict(delivery.render_context or {}) != dict(plan.render_context)
        or int(delivery.max_attempts) != max(1, int(event.max_attempts))
    ):
        _reject()

    destination = await lock_exact_website_recipient(session, target=target)
    if destination != delivery.destination:
        _reject()
