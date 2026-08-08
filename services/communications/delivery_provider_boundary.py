from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from models import CommunicationDelivery
from services.communications.delivery_service import (
    ClaimedCommunicationDelivery,
    CommunicationDeliveryService,
)
from services.communications.provider_boundary_authorization import (
    WebsiteProviderBoundaryDeliveryAuthorizer,
)


ProviderBoundaryCheck = Callable[[AsyncSession], Awaitable[None]]
ProviderBoundaryAuthorizer = Callable[
    [AsyncSession, ClaimedCommunicationDelivery],
    Awaitable[WebsiteProviderBoundaryDeliveryAuthorizer],
]


class ProviderBoundaryCheckFailed(RuntimeError):
    def __init__(self, error: BaseException) -> None:
        super().__init__("Provider boundary safety check failed")
        self.error = error


async def mark_provider_started_at_authorized_boundary(
    session: AsyncSession,
    *,
    claim: ClaimedCommunicationDelivery,
    worker_id: str,
    lease_seconds: int,
    boundary_check: ProviderBoundaryCheck | None,
    boundary_authorizer: ProviderBoundaryAuthorizer | None,
) -> None:
    """Cross the provider boundary using the shared global lock order."""

    delivery_authorizer: WebsiteProviderBoundaryDeliveryAuthorizer | None = None
    try:
        # Global order: runtime state -> canary run -> event/inbox. Delivery,
        # recipient authorization, and attempt are locked later by the service
        # and the prepared callback.
        if boundary_check is not None:
            await boundary_check(session)
        if boundary_authorizer is not None:
            delivery_authorizer = await boundary_authorizer(session, claim)
    except BaseException as error:
        raise ProviderBoundaryCheckFailed(error) from error

    async def authorize_locked_delivery(
        _locked_session: AsyncSession,
        delivery: CommunicationDelivery,
    ) -> None:
        if delivery_authorizer is None:
            return
        try:
            await delivery_authorizer(delivery)
        except BaseException as error:
            raise ProviderBoundaryCheckFailed(error) from error

    await CommunicationDeliveryService.mark_provider_started(
        session,
        delivery_id=claim.delivery_id,
        worker_id=worker_id,
        lease_token=claim.lease_token,
        lease_seconds=lease_seconds,
        authorization_check=(
            authorize_locked_delivery if delivery_authorizer is not None else None
        ),
    )
