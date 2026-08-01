from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CommunicationRuntimeState, CommunicationWebsiteCanaryRun
from services.communications.canary_run_id import normalize_canary_run_id
from services.communications.website_canary_target import (
    CANARY_KIND_OPERATIONS,
    CANARY_KIND_WEBSITE,
    WebsiteCanaryTarget,
)


class WebsiteCanaryRuntimeError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


class WebsiteCanaryRuntimeStore:
    """Drive the DB-enforced single armed-to-terminal canary transition."""

    @staticmethod
    def target_from_run(run: CommunicationWebsiteCanaryRun) -> WebsiteCanaryTarget:
        return WebsiteCanaryTarget(
            event_id=run.event_id,
            event_type=run.event_type,
            tenant_id=int(run.tenant_id),
            storefront_id=int(run.storefront_id),
            recipient_key=run.recipient_key,
        )

    @classmethod
    async def load_run(
        cls,
        session: AsyncSession,
        *,
        run_id: str,
        lock: bool = False,
    ) -> CommunicationWebsiteCanaryRun | None:
        return await session.get(
            CommunicationWebsiteCanaryRun,
            normalize_canary_run_id(run_id),
            populate_existing=lock,
            with_for_update=(lock and session.get_bind().dialect.name == "postgresql"),
        )

    @classmethod
    async def load_active_target(
        cls,
        session: AsyncSession,
        *,
        state: CommunicationRuntimeState,
        lock: bool = False,
    ) -> WebsiteCanaryTarget | None:
        if state.canary_kind == CANARY_KIND_OPERATIONS:
            if state.website_canary_run_id is not None:
                raise WebsiteCanaryRuntimeError(
                    "website_canary_runtime_reference_invalid"
                )
            return None
        if (
            state.canary_kind != CANARY_KIND_WEBSITE
            or state.mode != "canary"
            or state.canary_run_id is None
            or state.website_canary_run_id != state.canary_run_id
        ):
            raise WebsiteCanaryRuntimeError(
                "website_canary_runtime_reference_invalid"
            )
        run = await cls.load_run(
            session,
            run_id=state.website_canary_run_id,
            lock=lock,
        )
        if (
            run is None
            or run.state != "armed"
            or int(run.armed_control_revision) != int(state.control_revision)
        ):
            raise WebsiteCanaryRuntimeError(
                "website_canary_runtime_reference_invalid"
            )
        return cls.target_from_run(run)

    @classmethod
    async def arm_locked(
        cls,
        session: AsyncSession,
        *,
        state: CommunicationRuntimeState,
        run_id: str,
        expected_control_revision: int,
        target: WebsiteCanaryTarget,
        now: datetime,
    ) -> WebsiteCanaryTarget:
        normalized_run_id = normalize_canary_run_id(run_id)
        if (
            isinstance(expected_control_revision, bool)
            or not isinstance(expected_control_revision, int)
            or expected_control_revision < 0
        ):
            raise ValueError("Expected communication control revision is invalid")

        if state.canary_kind == CANARY_KIND_WEBSITE:
            active_target = await cls.load_active_target(
                session,
                state=state,
                lock=True,
            )
            if (
                state.canary_run_id == normalized_run_id
                and active_target == target
            ):
                return active_target
            raise WebsiteCanaryRuntimeError("website_canary_runtime_not_off")
        if (
            state.canary_kind != CANARY_KIND_OPERATIONS
            or state.website_canary_run_id is not None
        ):
            raise WebsiteCanaryRuntimeError(
                "website_canary_runtime_reference_invalid"
            )
        if state.mode != "off":
            raise WebsiteCanaryRuntimeError("website_canary_runtime_not_off")
        if int(state.control_revision) != expected_control_revision:
            raise WebsiteCanaryRuntimeError(
                "website_canary_control_revision_stale"
            )

        existing_run = await cls.load_run(
            session,
            run_id=normalized_run_id,
            lock=True,
        )
        if existing_run is not None:
            raise WebsiteCanaryRuntimeError("website_canary_run_id_reused")
        event_run_query = select(CommunicationWebsiteCanaryRun).where(
            CommunicationWebsiteCanaryRun.event_id == target.event_id
        )
        if session.get_bind().dialect.name == "postgresql":
            event_run_query = event_run_query.with_for_update()
        if await session.scalar(event_run_query) is not None:
            raise WebsiteCanaryRuntimeError("website_canary_event_already_used")

        next_revision = int(state.control_revision) + 1
        session.add(
            CommunicationWebsiteCanaryRun(
                run_id=normalized_run_id,
                event_id=target.event_id,
                event_type=target.event_type,
                tenant_id=target.tenant_id,
                storefront_id=target.storefront_id,
                recipient_key=target.recipient_key,
                armed_control_revision=next_revision,
                state="armed",
                created_at=now,
            )
        )
        state.mode = "canary"
        state.canary_run_id = normalized_run_id
        state.canary_kind = CANARY_KIND_WEBSITE
        state.website_canary_run_id = normalized_run_id
        state.control_revision = next_revision
        state.control_updated_at = now
        state.updated_at = now
        await session.flush()
        return target

    @classmethod
    async def complete_locked(
        cls,
        session: AsyncSession,
        *,
        state: CommunicationRuntimeState,
        run_id: str,
        expected_control_revision: int,
        target: WebsiteCanaryTarget,
        terminal_outcome: str,
        now: datetime,
    ) -> None:
        if terminal_outcome not in {"sent", "dead", "canceled", "ambiguous"}:
            raise ValueError("Website canary terminal outcome is invalid")
        normalized_run_id = normalize_canary_run_id(run_id)
        active_target = await cls.load_active_target(
            session,
            state=state,
            lock=True,
        )
        if (
            state.canary_run_id != normalized_run_id
            or active_target != target
        ):
            raise WebsiteCanaryRuntimeError(
                "website_canary_control_scope_changed"
            )
        if int(state.control_revision) != expected_control_revision:
            raise WebsiteCanaryRuntimeError(
                "website_canary_control_revision_stale"
            )
        run = await cls.load_run(session, run_id=normalized_run_id, lock=True)
        if run is None:  # pragma: no cover - load_active_target already checked
            raise WebsiteCanaryRuntimeError(
                "website_canary_runtime_reference_invalid"
            )
        cls._terminalize(state=state, run=run, outcome=terminal_outcome, now=now)
        await session.flush()

    @classmethod
    async def abort_locked(
        cls,
        session: AsyncSession,
        *,
        state: CommunicationRuntimeState,
        now: datetime,
    ) -> None:
        if state.canary_kind != CANARY_KIND_WEBSITE:
            raise WebsiteCanaryRuntimeError(
                "website_canary_emergency_off_not_active"
            )
        await cls.load_active_target(session, state=state, lock=True)
        run = await cls.load_run(
            session,
            run_id=state.website_canary_run_id or "",
            lock=True,
        )
        if run is None:  # pragma: no cover - load_active_target already checked
            raise WebsiteCanaryRuntimeError(
                "website_canary_emergency_off_audit_blocked"
            )
        cls._terminalize(state=state, run=run, outcome="aborted", now=now)
        await session.flush()

    @staticmethod
    def _terminalize(
        *,
        state: CommunicationRuntimeState,
        run: CommunicationWebsiteCanaryRun,
        outcome: str,
        now: datetime,
    ) -> None:
        next_revision = int(state.control_revision) + 1
        run.state = "terminal"
        run.terminal_outcome = outcome
        run.terminal_control_revision = next_revision
        run.finished_at = now
        state.mode = "off"
        state.canary_run_id = None
        state.canary_kind = CANARY_KIND_OPERATIONS
        state.website_canary_run_id = None
        state.control_revision = next_revision
        state.control_updated_at = now
        state.updated_at = now
