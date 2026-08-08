from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CommunicationRuntimeState
from services.communications.canary_run_id import normalize_canary_run_id
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.website_canary_runtime import (
    WebsiteCanaryRuntimeError,
    WebsiteCanaryRuntimeStore,
)
from services.communications.website_canary_target import (
    CANARY_KIND_OPERATIONS,
    WebsiteCanaryTarget,
)


class CommunicationRuntimeMode(str, Enum):
    OFF = "off"
    CANARY = "canary"
    ALL = "all"


class CommunicationRuntimeStatus(str, Enum):
    STOPPED = "stopped"
    FENCING = "fencing"
    DISABLED = "disabled"
    PAUSED = "paused"
    RUNNING = "running"
    STOPPING = "stopping"
    FAULTED = "faulted"


class CommunicationRuntimeStateOwnershipLost(RuntimeError):
    pass


class CommunicationRuntimeControlConflict(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


class CommunicationRuntimeModeBlocked(RuntimeError):
    def __init__(
        self,
        mode: CommunicationRuntimeMode,
        *,
        canary_run_id: str | None,
        control_revision: int,
    ) -> None:
        super().__init__("Communication runtime mode does not allow delivery work")
        self.mode = mode
        self.canary_run_id = canary_run_id
        self.control_revision = control_revision


@dataclass(frozen=True)
class CommunicationRuntimeControl:
    channel: str
    mode: CommunicationRuntimeMode
    canary_run_id: str | None
    control_revision: int
    status: CommunicationRuntimeStatus
    instance_id: str | None
    heartbeat_at: datetime | None
    installation_estimate_watermark_at: datetime | None
    canary_kind: str = CANARY_KIND_OPERATIONS
    website_canary_run_id: str | None = None
    website_canary_target: WebsiteCanaryTarget | None = None


class CommunicationRuntimeStateService:
    """Caller-transactional control and ownership operations.

    Operator-owned ``mode`` is intentionally absent from heartbeat updates.
    Every lifecycle write is fenced by ``instance_id`` so an old process cannot
    overwrite the state of a replacement after losing the advisory lock.
    """

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    async def database_now(cls, session: AsyncSession) -> datetime:
        clock = (
            func.clock_timestamp()
            if session.get_bind().dialect.name == "postgresql"
            else func.current_timestamp()
        )
        value = (await session.execute(select(clock))).scalar_one()
        return cls._as_utc(value)

    @staticmethod
    def _as_utc(value: object) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace(" ", "T"))
        if not isinstance(value, datetime):
            raise TypeError("Database clock did not return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _normalize_channel(channel: str) -> str:
        value = str(channel or "").strip().lower()
        if not value or len(value) > 32:
            raise ValueError("Communication runtime channel is invalid")
        return value

    @staticmethod
    def _normalize_instance_id(instance_id: str) -> str:
        value = str(instance_id or "").strip()
        if not value or len(value) > 128:
            raise ValueError("Communication runtime instance ID is invalid")
        return value

    @staticmethod
    def _normalize_error_code(error_code: str | None) -> str | None:
        if error_code is None:
            return None
        value = str(error_code).strip()
        if not value:
            return None
        return value[:100]

    @classmethod
    async def ensure_state(
        cls,
        session: AsyncSession,
        *,
        channel: str,
    ) -> CommunicationRuntimeState:
        normalized_channel = cls._normalize_channel(channel)
        state = await session.get(CommunicationRuntimeState, normalized_channel)
        if state is not None:
            return state
        now = cls._now()
        state = CommunicationRuntimeState(
            channel=normalized_channel,
            mode=CommunicationRuntimeMode.OFF.value,
            canary_run_id=None,
            canary_kind=CANARY_KIND_OPERATIONS,
            website_canary_run_id=None,
            control_revision=0,
            installation_estimate_watermark_at=None,
            status=CommunicationRuntimeStatus.STOPPED.value,
            control_updated_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            # The migration seeds the production row. The savepoint also makes
            # first-use initialization safe for isolated databases and tests:
            # concurrent callers race on the primary key without poisoning the
            # caller-owned outer transaction.
            async with session.begin_nested():
                session.add(state)
                await session.flush()
            return state
        except IntegrityError:
            concurrent_state = await session.get(
                CommunicationRuntimeState,
                normalized_channel,
                populate_existing=True,
            )
            if concurrent_state is None:  # pragma: no cover - defensive DB fence
                raise
            return concurrent_state

    @classmethod
    async def _lock_state(
        cls,
        session: AsyncSession,
        *,
        channel: str,
    ) -> CommunicationRuntimeState:
        normalized_channel = cls._normalize_channel(channel)
        state = await cls.ensure_state(session, channel=normalized_channel)
        if session.get_bind().dialect.name == "postgresql":
            state = await session.get(
                CommunicationRuntimeState,
                normalized_channel,
                populate_existing=True,
                with_for_update=True,
            )
            if state is None:  # pragma: no cover - protected by ensure_state
                raise RuntimeError("Communication runtime state disappeared")
        return state

    @classmethod
    async def lock_state_for_update(
        cls,
        session: AsyncSession,
        *,
        channel: str,
    ) -> CommunicationRuntimeState:
        """Expose the runtime row lock to typed control transactions."""

        return await cls._lock_state(session, channel=channel)

    @staticmethod
    def _normalize_canary_scope(
        mode: CommunicationRuntimeMode,
        canary_run_id: str | None,
    ) -> str | None:
        if mode == CommunicationRuntimeMode.CANARY:
            if canary_run_id is None:
                raise ValueError("Canary runtime mode requires a run ID")
            return normalize_canary_run_id(canary_run_id)
        if canary_run_id is not None:
            raise ValueError("Only canary runtime mode accepts a run ID")
        return None

    @classmethod
    def _apply_control(
        cls,
        state: CommunicationRuntimeState,
        *,
        mode: CommunicationRuntimeMode,
        canary_run_id: str | None,
        now: datetime,
        installation_estimate_watermark_at: datetime | None,
    ) -> None:
        if (
            state.canary_kind != CANARY_KIND_OPERATIONS
            or state.website_canary_run_id is not None
        ):
            raise CommunicationRuntimeControlConflict(
                "website_canary_runtime_reference_invalid"
            )
        current_watermark = (
            cls._as_utc(state.installation_estimate_watermark_at)
            if state.installation_estimate_watermark_at is not None
            else None
        )
        requested_watermark = (
            cls._as_utc(installation_estimate_watermark_at)
            if installation_estimate_watermark_at is not None
            else None
        )
        if (
            current_watermark is not None
            and requested_watermark != current_watermark
        ):
            raise CommunicationRuntimeControlConflict(
                "installation_activation_watermark_immutable"
            )
        if (
            mode == CommunicationRuntimeMode.ALL
            and requested_watermark is None
        ):
            raise CommunicationRuntimeControlConflict(
                "installation_activation_watermark_required"
            )
        state.mode = mode.value
        state.canary_run_id = canary_run_id
        state.canary_kind = CANARY_KIND_OPERATIONS
        state.website_canary_run_id = None
        state.control_revision = int(state.control_revision) + 1
        state.installation_estimate_watermark_at = requested_watermark
        state.control_updated_at = now
        state.updated_at = now

    @classmethod
    async def set_mode(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        mode: CommunicationRuntimeMode | str,
        canary_run_id: str | None = None,
    ) -> CommunicationRuntimeControl:
        normalized_mode = CommunicationRuntimeMode(mode)
        if normalized_mode == CommunicationRuntimeMode.ALL:
            raise CommunicationRuntimeControlConflict(
                "installation_activation_requires_typed_control"
            )
        normalized_run_id = cls._normalize_canary_scope(
            normalized_mode,
            canary_run_id,
        )
        state = await cls._lock_state(session, channel=channel)
        current_mode = CommunicationRuntimeMode(state.mode)
        if (
            current_mode == normalized_mode
            and state.canary_run_id == normalized_run_id
            and state.canary_kind == CANARY_KIND_OPERATIONS
            and state.website_canary_run_id is None
        ):
            return cls._to_control(state)
        if (
            current_mode != CommunicationRuntimeMode.OFF
            and normalized_mode != CommunicationRuntimeMode.OFF
        ):
            raise CommunicationRuntimeControlConflict(
                "runtime_control_transition_requires_off"
            )
        now = await cls.database_now(session)
        if state.canary_kind != CANARY_KIND_OPERATIONS:
            if normalized_mode != CommunicationRuntimeMode.OFF:
                raise CommunicationRuntimeControlConflict(
                    "runtime_control_transition_requires_off"
                )
            try:
                await WebsiteCanaryRuntimeStore.abort_locked(
                    session,
                    state=state,
                    now=now,
                )
            except WebsiteCanaryRuntimeError as error:
                raise CommunicationRuntimeControlConflict(error.error_code) from None
            return cls._to_control(state)
        cls._apply_control(
            state,
            mode=normalized_mode,
            canary_run_id=normalized_run_id,
            now=now,
            installation_estimate_watermark_at=(
                state.installation_estimate_watermark_at
            ),
        )
        await session.flush()
        return cls._to_control(state)

    @classmethod
    async def arm_canary_from_off(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        run_id: str,
    ) -> CommunicationRuntimeControl:
        normalized_run_id = normalize_canary_run_id(run_id)
        state = await cls._lock_state(session, channel=channel)
        if CommunicationRuntimeMode(state.mode) != CommunicationRuntimeMode.OFF:
            raise CommunicationRuntimeControlConflict("canary_runtime_not_off")
        now = await cls.database_now(session)
        cls._apply_control(
            state,
            mode=CommunicationRuntimeMode.CANARY,
            canary_run_id=normalized_run_id,
            now=now,
            installation_estimate_watermark_at=(
                state.installation_estimate_watermark_at
            ),
        )
        await session.flush()
        return await cls._hydrate_control(session, state=state, lock=True)

    @classmethod
    async def take_ownership(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        instance_id: str,
    ) -> CommunicationRuntimeControl:
        normalized_channel = cls._normalize_channel(channel)
        normalized_instance_id = cls._normalize_instance_id(instance_id)
        state = await cls._lock_state(session, channel=normalized_channel)
        now = cls._now()
        state.status = CommunicationRuntimeStatus.FENCING.value
        state.instance_id = normalized_instance_id
        state.started_at = now
        state.heartbeat_at = now
        state.last_activity_at = None
        state.last_error_code = None
        state.updated_at = now
        await session.flush()
        return await cls._hydrate_control(session, state=state, lock=True)

    @classmethod
    async def read_owned_control(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        instance_id: str,
    ) -> CommunicationRuntimeControl:
        normalized_channel = cls._normalize_channel(channel)
        normalized_instance_id = cls._normalize_instance_id(instance_id)
        state = await session.get(CommunicationRuntimeState, normalized_channel)
        if state is None or state.instance_id != normalized_instance_id:
            raise CommunicationRuntimeStateOwnershipLost(
                "Communication runtime state ownership was lost"
            )
        return await cls._hydrate_control(session, state=state)

    @classmethod
    async def read_control(
        cls,
        session: AsyncSession,
        *,
        channel: str,
    ) -> CommunicationRuntimeControl:
        state = await cls.ensure_state(session, channel=channel)
        return await cls._hydrate_control(session, state=state)

    @classmethod
    async def assert_owned_processing_scope(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        instance_id: str,
        scope: CommunicationProcessingScope,
    ) -> CommunicationRuntimeControl:
        control = await cls.read_owned_control(
            session,
            channel=channel,
            instance_id=instance_id,
        )
        if not scope.matches_control(
            mode=control.mode.value,
            canary_run_id=control.canary_run_id,
            control_revision=control.control_revision,
            event_created_at_watermark=(
                control.installation_estimate_watermark_at
            ),
            website_canary_target=control.website_canary_target,
        ):
            raise CommunicationRuntimeModeBlocked(
                control.mode,
                canary_run_id=control.canary_run_id,
                control_revision=control.control_revision,
            )
        return control

    @classmethod
    async def lock_owned_processing_scope(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        instance_id: str,
        scope: CommunicationProcessingScope,
    ) -> CommunicationRuntimeControl:
        """Linearize the provider boundary against operator control changes."""

        normalized_instance_id = cls._normalize_instance_id(instance_id)
        state = await cls._lock_state(session, channel=channel)
        if state.instance_id != normalized_instance_id:
            raise CommunicationRuntimeStateOwnershipLost(
                "Communication runtime state ownership was lost"
            )
        control = await cls._hydrate_control(session, state=state, lock=True)
        if not scope.matches_control(
            mode=control.mode.value,
            canary_run_id=control.canary_run_id,
            control_revision=control.control_revision,
            event_created_at_watermark=(
                control.installation_estimate_watermark_at
            ),
            website_canary_target=control.website_canary_target,
        ):
            raise CommunicationRuntimeModeBlocked(
                control.mode,
                canary_run_id=control.canary_run_id,
                control_revision=control.control_revision,
            )
        return control

    @classmethod
    async def record_status(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        instance_id: str,
        status: CommunicationRuntimeStatus | str,
        last_error_code: str | None = None,
        activity: bool = False,
    ) -> None:
        normalized_channel = cls._normalize_channel(channel)
        normalized_instance_id = cls._normalize_instance_id(instance_id)
        normalized_status = CommunicationRuntimeStatus(status)
        now = cls._now()
        values: dict[str, object] = {
            "status": normalized_status.value,
            "heartbeat_at": now,
            "last_error_code": cls._normalize_error_code(last_error_code),
            "updated_at": now,
        }
        if activity:
            values["last_activity_at"] = now
        result = await session.execute(
            update(CommunicationRuntimeState)
            .where(
                CommunicationRuntimeState.channel == normalized_channel,
                CommunicationRuntimeState.instance_id == normalized_instance_id,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise CommunicationRuntimeStateOwnershipLost(
                "Communication runtime state ownership was lost"
            )

    @classmethod
    async def control_from_locked_state(
        cls,
        session: AsyncSession,
        *,
        state: CommunicationRuntimeState,
    ) -> CommunicationRuntimeControl:
        return await cls._hydrate_control(session, state=state, lock=True)

    @classmethod
    async def _hydrate_control(
        cls,
        session: AsyncSession,
        *,
        state: CommunicationRuntimeState,
        lock: bool = False,
    ) -> CommunicationRuntimeControl:
        control = cls._to_control(state)
        try:
            target = await WebsiteCanaryRuntimeStore.load_active_target(
                session,
                state=state,
                lock=lock,
            )
        except WebsiteCanaryRuntimeError as error:
            raise CommunicationRuntimeControlConflict(error.error_code) from None
        return replace(control, website_canary_target=target)

    @staticmethod
    def _to_control(state: CommunicationRuntimeState) -> CommunicationRuntimeControl:
        return CommunicationRuntimeControl(
            channel=state.channel,
            mode=CommunicationRuntimeMode(state.mode),
            canary_run_id=state.canary_run_id,
            control_revision=int(state.control_revision),
            status=CommunicationRuntimeStatus(state.status),
            instance_id=state.instance_id,
            heartbeat_at=state.heartbeat_at,
            installation_estimate_watermark_at=(
                CommunicationRuntimeStateService._as_utc(
                    state.installation_estimate_watermark_at
                )
                if state.installation_estimate_watermark_at is not None
                else None
            ),
            canary_kind=state.canary_kind,
            website_canary_run_id=state.website_canary_run_id,
        )
