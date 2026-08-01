from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CommunicationDelivery, ConsumerInbox, IntegrationOutboxEvent
from services.communications.audience_resolver import CommunicationAudienceResolver
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.contracts import DispatchOutcomeV1
from services.communications.delivery_materializer import (
    CommunicationDeliveryMaterializer,
    DeliveryMaterializationConflict,
    NoEligibleCommunicationRecipients,
)
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.runtime_state import (
    CommunicationRuntimeStateService,
)
from services.communications.template_registry import (
    CONSUMER_NAME,
    HANDLER_VERSION,
    InvalidCommunicationEventPayload,
    UnsupportedCommunicationEvent,
    WebsiteTemplateRegistry,
)
from services.communications.templates import TemplateRenderError


class ConsumerInboxConsistencyError(RuntimeError):
    pass


class CommunicationOutboxDispatcher:
    """Atomically convert one supported outbox event into queued deliveries.

    The caller owns commit/rollback. There is deliberately no lease here:
    selection, rendering, recipient lookup and persistence are short database
    work performed under one row lock. Leases belong to the later network
    delivery worker.
    """

    _RETRY_BASE_SECONDS = 30
    _RETRY_MAX_SECONDS = 3600

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    async def _select_next(
        cls,
        session: AsyncSession,
        *,
        now: datetime,
        scope: CommunicationProcessingScope,
    ) -> IntegrationOutboxEvent | None:
        query = (
            select(IntegrationOutboxEvent)
            .where(
                IntegrationOutboxEvent.status == "pending",
                IntegrationOutboxEvent.available_at <= now,
                IntegrationOutboxEvent.event_type.in_(scope.outbox_event_types),
            )
            .order_by(
                IntegrationOutboxEvent.priority.asc(),
                IntegrationOutboxEvent.occurred_at.asc(),
                IntegrationOutboxEvent.created_at.asc(),
                IntegrationOutboxEvent.event_id.asc(),
            )
            .limit(1)
        )
        if scope.exact_event_id is not None:
            query = query.where(
                IntegrationOutboxEvent.event_id == scope.exact_event_id
            )
        if scope.event_created_at_watermark is not None:
            query = query.where(
                IntegrationOutboxEvent.created_at
                >= scope.event_created_at_watermark
            )
        if session.get_bind().dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        return (await session.execute(query)).scalar_one_or_none()

    @classmethod
    def _retry_delay(cls, *, event_id: str, attempts: int) -> timedelta:
        exponent = max(0, min(int(attempts) - 1, 16))
        base_seconds = min(
            cls._RETRY_MAX_SECONDS,
            cls._RETRY_BASE_SECONDS * (2**exponent),
        )
        jitter_window = max(1, base_seconds // 5)
        digest = hashlib.sha256(f"{event_id}:{attempts}".encode()).digest()
        jitter_seconds = int.from_bytes(digest[:4], "big") % (jitter_window + 1)
        return timedelta(
            seconds=min(cls._RETRY_MAX_SECONDS, base_seconds + jitter_seconds)
        )

    @staticmethod
    def _mark_published(event: IntegrationOutboxEvent, *, now: datetime) -> None:
        event.status = "published"
        event.published_at = now
        event.worker_id = None
        event.lease_token = None
        event.lease_expires_at = None
        event.last_error_code = None
        event.last_error_message = None
        event.updated_at = now

    @classmethod
    def _record_failure(
        cls,
        event: IntegrationOutboxEvent,
        *,
        error: Exception,
        now: datetime,
        permanent: bool,
    ) -> DispatchOutcomeV1:
        is_dead = permanent or event.attempts >= event.max_attempts
        next_attempt_at = None
        if not is_dead:
            next_attempt_at = now + cls._retry_delay(
                event_id=event.event_id,
                attempts=event.attempts,
            )
            event.available_at = next_attempt_at
        event.status = "dead" if is_dead else "pending"
        event.worker_id = None
        event.lease_token = None
        event.lease_expires_at = None
        event.last_error_code = (
            error.error_code
            if isinstance(error, CommunicationsCanarySafetyError)
            else type(error).__name__[:100]
        )
        event.last_error_message = (str(error).strip() or type(error).__name__)[:1000]
        event.updated_at = now
        return DispatchOutcomeV1(
            outcome="dead" if is_dead else "retry_scheduled",
            event_id=event.event_id,
            attempts=event.attempts,
            delivery_count=0,
            next_attempt_at=next_attempt_at,
        )

    @classmethod
    async def _recover_processed_event(
        cls,
        session: AsyncSession,
        *,
        event: IntegrationOutboxEvent,
        now: datetime,
    ) -> DispatchOutcomeV1 | None:
        inbox = await session.get(ConsumerInbox, (CONSUMER_NAME, event.event_id))
        if inbox is None:
            return None
        if inbox.handler_version != HANDLER_VERSION:
            raise ConsumerInboxConsistencyError(
                "Consumer inbox handler version is inconsistent"
            )
        plan = WebsiteTemplateRegistry.plan(event)
        WebsiteTemplateRegistry.render(plan)
        deliveries = list(
            (
                await session.execute(
                    select(CommunicationDelivery).where(
                        CommunicationDelivery.event_id == event.event_id,
                        CommunicationDelivery.channel == plan.channel,
                        CommunicationDelivery.template_version
                        == plan.template_version,
                    )
                )
            ).scalars()
        )
        if not deliveries:
            raise ConsumerInboxConsistencyError(
                "Consumer inbox exists without materialized deliveries"
            )
        if plan.audience in {
            "installation_estimate_owners",
            "tenant_website_management",
            "operations_canary",
            "staff_assignee",
        }:
            expected_recipients = await CommunicationAudienceResolver.list_telegram(
                session,
                plan=plan,
            )
            expected_routing = {
                (recipient.recipient_key, recipient.destination)
                for recipient in expected_recipients
            }
            actual_routing = {
                (delivery.recipient_key, delivery.destination)
                for delivery in deliveries
            }
            if actual_routing != expected_routing:
                raise ConsumerInboxConsistencyError(
                    "Exact-audience inbox delivery recipients are inconsistent"
                )
        for delivery in deliveries:
            if (
                delivery.channel != plan.channel
                or delivery.template_key != plan.template_key
                or delivery.template_version != plan.template_version
                or delivery.render_context != plan.render_context
                or delivery.delivery_id
                != CommunicationDeliveryMaterializer.build_delivery_id(
                    event_id=event.event_id,
                    channel=delivery.channel,
                    recipient_key=delivery.recipient_key,
                    template_version=delivery.template_version,
                )
            ):
                raise ConsumerInboxConsistencyError(
                    "Consumer inbox delivery snapshot is inconsistent"
                )
        cls._mark_published(event, now=now)
        return DispatchOutcomeV1(
            outcome="already_materialized",
            event_id=event.event_id,
            attempts=event.attempts,
            delivery_count=len(deliveries),
        )

    @classmethod
    async def dispatch_next(
        cls,
        session: AsyncSession,
        *,
        dispatcher_id: str,
        scope: CommunicationProcessingScope,
        now: datetime | None = None,
    ) -> DispatchOutcomeV1 | None:
        normalized_dispatcher_id = str(dispatcher_id or "").strip()
        if not normalized_dispatcher_id:
            raise ValueError("Communication dispatcher_id is required")
        if len(normalized_dispatcher_id) > 128:
            raise ValueError("Communication dispatcher_id is too long")
        if (
            now is None
            and scope.mode == "all"
            and session.get_bind().dialect.name == "postgresql"
        ):
            dispatch_time = await CommunicationRuntimeStateService.database_now(
                session
            )
        else:
            dispatch_time = now or cls._utc_now()

        event = await cls._select_next(
            session,
            now=dispatch_time,
            scope=scope,
        )
        if event is None:
            return None

        event.status = "processing"
        event.attempts += 1
        event.worker_id = normalized_dispatcher_id
        event.lease_token = None
        event.lease_expires_at = None
        event.last_error_code = None
        event.last_error_message = None
        event.updated_at = dispatch_time
        session.add(event)

        try:
            recovered = await cls._recover_processed_event(
                session,
                event=event,
                now=dispatch_time,
            )
        except (
            ConsumerInboxConsistencyError,
            CommunicationsCanarySafetyError,
            InvalidCommunicationEventPayload,
            TemplateRenderError,
            UnsupportedCommunicationEvent,
        ) as exc:
            return cls._record_failure(
                event,
                error=exc,
                now=dispatch_time,
                permanent=True,
            )
        if recovered is not None:
            return recovered

        try:
            # A savepoint ensures a deterministic conflict cannot leave a
            # partially inserted recipient set when the caller commits the
            # failure state.
            async with session.begin_nested():
                plan = WebsiteTemplateRegistry.plan(event)
                WebsiteTemplateRegistry.render(plan)
                recipients = await CommunicationAudienceResolver.list_telegram(
                    session,
                    plan=plan,
                )
                materialized = await CommunicationDeliveryMaterializer.materialize(
                    session,
                    event=event,
                    plan=plan,
                    recipients=recipients,
                    now=dispatch_time,
                )
        except (
            CommunicationsCanarySafetyError,
            NoEligibleCommunicationRecipients,
        ) as exc:
            return cls._record_failure(
                event,
                error=exc,
                now=dispatch_time,
                permanent=False,
            )
        except (
            DeliveryMaterializationConflict,
            InvalidCommunicationEventPayload,
            TemplateRenderError,
            UnsupportedCommunicationEvent,
        ) as exc:
            return cls._record_failure(
                event,
                error=exc,
                now=dispatch_time,
                permanent=True,
            )

        session.add(
            ConsumerInbox(
                consumer_name=CONSUMER_NAME,
                event_id=event.event_id,
                handler_version=HANDLER_VERSION,
                received_at=dispatch_time,
                processed_at=dispatch_time,
            )
        )
        await session.flush()
        cls._mark_published(event, now=dispatch_time)
        return DispatchOutcomeV1(
            outcome=(
                "materialized"
                if materialized.created_count
                else "already_materialized"
            ),
            event_id=event.event_id,
            attempts=event.attempts,
            delivery_count=materialized.delivery_count,
        )
