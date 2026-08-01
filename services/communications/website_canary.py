from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    CommunicationWebsiteCanaryRun,
    ConsumerInbox,
    IntegrationOutboxEvent,
)
from services.communications.canary import CommunicationsTelegramCanary
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.canary_run_id import normalize_canary_run_id
from services.communications.recipient_directory import (
    TenantWebsiteManagementRecipientDirectory,
)
from services.communications.runtime_config import CommunicationRuntimeConfig
from services.communications.runtime_state import (
    CommunicationRuntimeControl,
    CommunicationRuntimeMode,
    CommunicationRuntimeStateService,
    CommunicationRuntimeStatus,
)
from services.communications.template_registry import (
    CONSUMER_NAME,
    WebsiteTemplateRegistry,
)
from services.communications.website_canary_runtime import (
    WebsiteCanaryRuntimeError,
    WebsiteCanaryRuntimeStore,
)
from services.communications.website_canary_target import (
    WebsiteCanaryScopeMismatch,
    WebsiteCanaryTarget,
)


TerminalOutcome = Literal["sent", "dead", "canceled", "ambiguous", "aborted"]


class WebsiteCanaryControlRejected(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = str(error_code)
        super().__init__(self.error_code)


@dataclass(frozen=True)
class WebsiteCanarySnapshot:
    mode: Literal["plan", "armed", "status", "completed"]
    run_id: str
    event_id: str
    event_type: str
    tenant_id: int
    storefront_id: int
    recipient_key: str
    control_revision: int
    runtime_mode: str
    lifecycle: Literal["pending", "ambiguous", "terminal"]
    terminal_outcome: TerminalOutcome | None
    event_status: str
    delivery_status: str | None
    provider_acknowledged: bool
    ambiguous_attempt_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _CanaryEvidence:
    event: IntegrationOutboxEvent
    delivery: CommunicationDelivery | None
    latest_attempt: CommunicationDeliveryAttempt | None
    ambiguous_attempt_count: int


class TenantWebsiteCommunicationsCanary:
    """Arm and inspect one exact tenant website delivery without widening scope."""

    CHANNEL = "telegram"

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def validate_deployment_profile(
        cls,
        config: CommunicationRuntimeConfig,
    ) -> None:
        if not config.enabled or config.allow_all_mode:
            raise WebsiteCanaryControlRejected(
                "website_canary_deployment_profile_invalid"
            )

    @classmethod
    async def _preflight_environment(
        cls,
        session: AsyncSession,
        *,
        config: CommunicationRuntimeConfig,
        bot_token: str | None,
    ) -> None:
        cls.validate_deployment_profile(config)
        try:
            await CommunicationsTelegramCanary.preflight_runtime(
                session,
                app_role=config.app_role,
                bot_token=bot_token,
            )
        except CommunicationsCanarySafetyError as error:
            raise WebsiteCanaryControlRejected(error.error_code) from None

    @classmethod
    async def _assert_runtime_ready(
        cls,
        session: AsyncSession,
        *,
        control: CommunicationRuntimeControl,
        config: CommunicationRuntimeConfig,
    ) -> None:
        if control.mode != CommunicationRuntimeMode.OFF:
            raise WebsiteCanaryControlRejected("website_canary_runtime_not_off")
        if control.status != CommunicationRuntimeStatus.DISABLED:
            raise WebsiteCanaryControlRejected(
                "website_canary_runtime_not_dormant"
            )
        heartbeat = cls._as_utc(control.heartbeat_at)
        now = await CommunicationRuntimeStateService.database_now(session)
        max_age = max(30.0, 3.0 * config.heartbeat_seconds)
        if (
            not control.instance_id
            or heartbeat is None
            or not 0 <= (now - heartbeat).total_seconds() <= max_age
        ):
            raise WebsiteCanaryControlRejected(
                "website_canary_runtime_owner_not_fresh"
            )

    @classmethod
    async def preflight_runtime(
        cls,
        session: AsyncSession,
        *,
        config: CommunicationRuntimeConfig,
        bot_token: str | None,
    ) -> CommunicationRuntimeControl:
        await cls._preflight_environment(
            session,
            config=config,
            bot_token=bot_token,
        )
        control = await CommunicationRuntimeStateService.read_control(
            session,
            channel=cls.CHANNEL,
        )
        await cls._assert_runtime_ready(session, control=control, config=config)
        return control

    @staticmethod
    async def _event_for_target(
        session: AsyncSession,
        *,
        target: WebsiteCanaryTarget,
        lock: bool,
    ) -> IntegrationOutboxEvent:
        event = await session.get(
            IntegrationOutboxEvent,
            target.event_id,
            populate_existing=lock,
            with_for_update=(lock and session.get_bind().dialect.name == "postgresql"),
        )
        if event is None:
            raise WebsiteCanaryControlRejected("website_canary_event_not_found")
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
        except (ValueError, WebsiteCanaryScopeMismatch):
            raise WebsiteCanaryControlRejected(
                "website_canary_event_scope_invalid"
            ) from None
        return event

    @classmethod
    async def _assert_exact_recipient(
        cls,
        session: AsyncSession,
        *,
        target: WebsiteCanaryTarget,
    ) -> None:
        try:
            recipients = await TenantWebsiteManagementRecipientDirectory.list_telegram(
                session,
                tenant_id=target.tenant_id,
                storefront_id=target.storefront_id,
            )
        except CommunicationsCanarySafetyError as error:
            raise WebsiteCanaryControlRejected(error.error_code) from None
        matches = [
            recipient
            for recipient in recipients
            if recipient.recipient_key == target.recipient_key
        ]
        if len(matches) != 1:
            raise WebsiteCanaryControlRejected(
                "website_canary_recipient_scope_invalid"
            )

    @classmethod
    async def _validate_armable_event(
        cls,
        session: AsyncSession,
        *,
        target: WebsiteCanaryTarget,
        lock: bool,
    ) -> IntegrationOutboxEvent:
        event = await cls._event_for_target(session, target=target, lock=lock)
        now = await CommunicationRuntimeStateService.database_now(session)
        if (
            event.status != "pending"
            or int(event.attempts) != 0
            or event.worker_id is not None
            or event.lease_token is not None
            or event.lease_expires_at is not None
            or cls._as_utc(event.available_at) is None
            or cls._as_utc(event.available_at) > now
        ):
            raise WebsiteCanaryControlRejected(
                "website_canary_event_not_armable"
            )
        delivery = await session.scalar(
            select(CommunicationDelivery.delivery_id)
            .where(CommunicationDelivery.event_id == target.event_id)
            .limit(1)
        )
        inbox = await session.get(ConsumerInbox, (CONSUMER_NAME, target.event_id))
        attempt = await session.scalar(
            select(CommunicationDeliveryAttempt.delivery_id)
            .join(
                CommunicationDelivery,
                CommunicationDelivery.delivery_id
                == CommunicationDeliveryAttempt.delivery_id,
            )
            .where(CommunicationDelivery.event_id == target.event_id)
            .limit(1)
        )
        if delivery is not None or inbox is not None or attempt is not None:
            raise WebsiteCanaryControlRejected(
                "website_canary_event_already_materialized"
            )
        await cls._assert_exact_recipient(session, target=target)
        return event

    @staticmethod
    async def _assert_unused_run(
        session: AsyncSession,
        *,
        run_id: str,
        target: WebsiteCanaryTarget,
    ) -> None:
        if await session.get(CommunicationWebsiteCanaryRun, run_id) is not None:
            raise WebsiteCanaryControlRejected("website_canary_run_id_reused")
        existing_event = await session.scalar(
            select(CommunicationWebsiteCanaryRun.run_id)
            .where(CommunicationWebsiteCanaryRun.event_id == target.event_id)
            .limit(1)
        )
        if existing_event is not None:
            raise WebsiteCanaryControlRejected(
                "website_canary_event_already_used"
            )

    @classmethod
    async def plan(
        cls,
        session: AsyncSession,
        *,
        run_id: str,
        target: WebsiteCanaryTarget,
        config: CommunicationRuntimeConfig,
        bot_token: str | None,
    ) -> WebsiteCanarySnapshot:
        normalized_run_id = normalize_canary_run_id(run_id)
        control = await cls.preflight_runtime(
            session,
            config=config,
            bot_token=bot_token,
        )
        await cls._assert_unused_run(
            session,
            run_id=normalized_run_id,
            target=target,
        )
        event = await cls._validate_armable_event(
            session,
            target=target,
            lock=False,
        )
        return cls._snapshot(
            mode="plan",
            run_id=normalized_run_id,
            target=target,
            control=control,
            evidence=_CanaryEvidence(event, None, None, 0),
        )

    @classmethod
    async def arm(
        cls,
        session: AsyncSession,
        *,
        run_id: str,
        target: WebsiteCanaryTarget,
        expected_control_revision: int,
        config: CommunicationRuntimeConfig,
        bot_token: str | None,
    ) -> WebsiteCanarySnapshot:
        normalized_run_id = normalize_canary_run_id(run_id)
        await cls._preflight_environment(
            session,
            config=config,
            bot_token=bot_token,
        )
        state = await CommunicationRuntimeStateService.lock_state_for_update(
            session,
            channel=cls.CHANNEL,
        )
        control = await CommunicationRuntimeStateService.control_from_locked_state(
            session,
            state=state,
        )
        if (
            control.mode == CommunicationRuntimeMode.CANARY
            and control.canary_run_id == normalized_run_id
            and control.website_canary_target == target
        ):
            evidence = await cls._load_evidence(
                session,
                target=target,
                lock=True,
            )
            return cls._snapshot(
                mode="armed",
                run_id=normalized_run_id,
                target=target,
                control=control,
                evidence=evidence,
            )
        await cls._assert_runtime_ready(session, control=control, config=config)
        event = await cls._validate_armable_event(
            session,
            target=target,
            lock=True,
        )
        try:
            await WebsiteCanaryRuntimeStore.arm_locked(
                session,
                state=state,
                run_id=normalized_run_id,
                expected_control_revision=expected_control_revision,
                target=target,
                now=await CommunicationRuntimeStateService.database_now(session),
            )
            control = (
                await CommunicationRuntimeStateService.control_from_locked_state(
                    session,
                    state=state,
                )
            )
        except WebsiteCanaryRuntimeError as error:
            raise WebsiteCanaryControlRejected(error.error_code) from None
        return cls._snapshot(
            mode="armed",
            run_id=normalized_run_id,
            target=target,
            control=control,
            evidence=_CanaryEvidence(event, None, None, 0),
        )

    @classmethod
    async def status(
        cls,
        session: AsyncSession,
        *,
        run_id: str,
        target: WebsiteCanaryTarget,
    ) -> WebsiteCanarySnapshot:
        normalized_run_id = normalize_canary_run_id(run_id)
        run = await WebsiteCanaryRuntimeStore.load_run(
            session,
            run_id=normalized_run_id,
        )
        if run is None or WebsiteCanaryRuntimeStore.target_from_run(run) != target:
            raise WebsiteCanaryControlRejected(
                "website_canary_run_scope_invalid"
            )
        control = await CommunicationRuntimeStateService.read_control(
            session,
            channel=cls.CHANNEL,
        )
        if run.state == "armed" and (
            control.mode != CommunicationRuntimeMode.CANARY
            or control.canary_run_id != normalized_run_id
            or control.website_canary_target != target
        ):
            raise WebsiteCanaryControlRejected(
                "website_canary_control_scope_changed"
            )
        evidence = await cls._load_evidence(
            session,
            target=target,
            lock=False,
        )
        return cls._snapshot(
            mode="status",
            run_id=normalized_run_id,
            target=target,
            control=control,
            evidence=evidence,
            recorded_outcome=(
                run.terminal_outcome if run.state == "terminal" else None
            ),
        )

    @classmethod
    async def complete(
        cls,
        session: AsyncSession,
        *,
        run_id: str,
        target: WebsiteCanaryTarget,
    ) -> WebsiteCanarySnapshot:
        normalized_run_id = normalize_canary_run_id(run_id)
        state = await CommunicationRuntimeStateService.lock_state_for_update(
            session,
            channel=cls.CHANNEL,
        )
        control = await CommunicationRuntimeStateService.control_from_locked_state(
            session,
            state=state,
        )
        if (
            control.mode != CommunicationRuntimeMode.CANARY
            or control.canary_run_id != normalized_run_id
            or control.website_canary_target != target
        ):
            run = await WebsiteCanaryRuntimeStore.load_run(
                session,
                run_id=normalized_run_id,
                lock=True,
            )
            if (
                run is None
                or run.state != "terminal"
                or WebsiteCanaryRuntimeStore.target_from_run(run) != target
            ):
                raise WebsiteCanaryControlRejected(
                    "website_canary_control_scope_changed"
                )
            evidence = await cls._load_evidence(
                session,
                target=target,
                lock=True,
            )
            replay = cls._snapshot(
                mode="status",
                run_id=normalized_run_id,
                target=target,
                control=control,
                evidence=evidence,
                recorded_outcome=run.terminal_outcome,
            )
            return WebsiteCanarySnapshot(
                **{
                    **replay.to_dict(),
                    "mode": "completed",
                }
            )
        evidence = await cls._load_evidence(
            session,
            target=target,
            lock=True,
        )
        snapshot = cls._snapshot(
            mode="status",
            run_id=normalized_run_id,
            target=target,
            control=control,
            evidence=evidence,
        )
        if snapshot.lifecycle != "terminal" or snapshot.terminal_outcome is None:
            raise WebsiteCanaryControlRejected(
                "website_canary_terminal_outcome_required"
            )
        try:
            await WebsiteCanaryRuntimeStore.complete_locked(
                session,
                state=state,
                run_id=normalized_run_id,
                expected_control_revision=control.control_revision,
                target=target,
                terminal_outcome=snapshot.terminal_outcome,
                now=await CommunicationRuntimeStateService.database_now(session),
            )
        except WebsiteCanaryRuntimeError as error:
            raise WebsiteCanaryControlRejected(error.error_code) from None
        off = CommunicationRuntimeStateService._to_control(state)
        return WebsiteCanarySnapshot(
            **{
                **snapshot.to_dict(),
                "mode": "completed",
                "runtime_mode": off.mode.value,
                "control_revision": off.control_revision,
            }
        )

    @classmethod
    async def _load_evidence(
        cls,
        session: AsyncSession,
        *,
        target: WebsiteCanaryTarget,
        lock: bool,
    ) -> _CanaryEvidence:
        event = await cls._event_for_target(session, target=target, lock=lock)
        inbox = await session.get(
            ConsumerInbox,
            (CONSUMER_NAME, target.event_id),
            populate_existing=lock,
            with_for_update=(lock and session.get_bind().dialect.name == "postgresql"),
        )
        delivery_query = select(CommunicationDelivery).where(
            CommunicationDelivery.event_id == target.event_id
        )
        if lock and session.get_bind().dialect.name == "postgresql":
            delivery_query = delivery_query.with_for_update()
        deliveries = list((await session.execute(delivery_query)).scalars())
        if len(deliveries) > 1:
            raise WebsiteCanaryControlRejected(
                "website_canary_delivery_scope_invalid"
            )
        delivery = deliveries[0] if deliveries else None
        if delivery is not None and (
            delivery.recipient_key != target.recipient_key
            or delivery.template_key != target.template_key
        ):
            raise WebsiteCanaryControlRejected(
                "website_canary_delivery_scope_invalid"
            )
        if (inbox is None) != (delivery is None) and event.status == "published":
            raise WebsiteCanaryControlRejected(
                "website_canary_materialization_inconsistent"
            )

        attempts: list[CommunicationDeliveryAttempt] = []
        if delivery is not None:
            attempt_query = (
                select(CommunicationDeliveryAttempt)
                .where(
                    CommunicationDeliveryAttempt.delivery_id
                    == delivery.delivery_id
                )
                .order_by(CommunicationDeliveryAttempt.attempt_no.asc())
            )
            if lock and session.get_bind().dialect.name == "postgresql":
                attempt_query = attempt_query.with_for_update()
            attempts = list((await session.execute(attempt_query)).scalars())
        return _CanaryEvidence(
            event=event,
            delivery=delivery,
            latest_attempt=attempts[-1] if attempts else None,
            ambiguous_attempt_count=sum(
                1 for attempt in attempts if attempt.ambiguous
            ),
        )

    @staticmethod
    def _classify(
        evidence: _CanaryEvidence,
    ) -> tuple[
        Literal["pending", "ambiguous", "terminal"],
        TerminalOutcome | None,
    ]:
        event = evidence.event
        delivery = evidence.delivery
        latest_attempt = evidence.latest_attempt
        if (
            delivery is not None
            and delivery.status == "sent"
            and delivery.provider_message_id
        ):
            return "terminal", "sent"
        if evidence.ambiguous_attempt_count:
            # Claim selection permanently excludes any ambiguous history, so
            # this is a terminal manual-reconciliation outcome even if an
            # older row still says retry.
            return "terminal", "ambiguous"
        if delivery is not None and delivery.status == "dead":
            return "terminal", "dead"
        if delivery is not None and delivery.status == "canceled":
            return "terminal", "canceled"
        if event.status == "dead" and delivery is None:
            return "terminal", "dead"
        if (
            latest_attempt is not None
            and latest_attempt.outcome == "running"
        ):
            return "pending", None
        return "pending", None

    @classmethod
    def _snapshot(
        cls,
        *,
        mode: Literal["plan", "armed", "status"],
        run_id: str,
        target: WebsiteCanaryTarget,
        control: CommunicationRuntimeControl,
        evidence: _CanaryEvidence,
        recorded_outcome: str | None = None,
    ) -> WebsiteCanarySnapshot:
        if recorded_outcome is None:
            lifecycle, terminal_outcome = cls._classify(evidence)
        else:
            if recorded_outcome not in {
                "sent",
                "dead",
                "canceled",
                "ambiguous",
                "aborted",
            }:
                raise WebsiteCanaryControlRejected(
                    "website_canary_terminal_outcome_invalid"
                )
            lifecycle = "terminal"
            terminal_outcome = recorded_outcome
        delivery = evidence.delivery
        return WebsiteCanarySnapshot(
            mode=mode,
            run_id=run_id,
            event_id=target.event_id,
            event_type=target.event_type,
            tenant_id=target.tenant_id,
            storefront_id=target.storefront_id,
            recipient_key=target.recipient_key,
            control_revision=control.control_revision,
            runtime_mode=control.mode.value,
            lifecycle=lifecycle,
            terminal_outcome=terminal_outcome,
            event_status=evidence.event.status,
            delivery_status=delivery.status if delivery is not None else None,
            provider_acknowledged=bool(
                delivery is not None
                and delivery.status == "sent"
                and delivery.provider_message_id
            ),
            ambiguous_attempt_count=evidence.ambiguous_attempt_count,
        )
