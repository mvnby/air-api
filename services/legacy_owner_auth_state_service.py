"""Fail-closed access to the singleton legacy-owner authentication fence."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import LegacyOwnerAuthState


class LegacyOwnerAuthStateUnavailableError(RuntimeError):
    """The singleton state is absent or violates its reviewed contract."""


class LegacyOwnerAuthStateService:
    MODE_LEGACY = "legacy"
    MODE_STAFF_SHADOW = "staff_shadow"
    MODE_STAFF = "staff"
    MODES = frozenset({MODE_LEGACY, MODE_STAFF_SHADOW, MODE_STAFF})
    SINGLETON_ID = 1

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        *,
        for_update: bool = False,
        for_share: bool = False,
    ) -> LegacyOwnerAuthState:
        if for_update and for_share:
            raise ValueError("Legacy-owner state lock mode is ambiguous")
        statement = select(LegacyOwnerAuthState).where(
            LegacyOwnerAuthState.id == cls.SINGLETON_ID
        )
        if for_update:
            statement = statement.with_for_update(of=LegacyOwnerAuthState)
        elif for_share:
            statement = statement.with_for_update(
                read=True,
                of=LegacyOwnerAuthState,
            )
        state = (await session.execute(statement)).scalar_one_or_none()
        if state is None or state.mode not in cls.MODES:
            raise LegacyOwnerAuthStateUnavailableError(
                "Legacy-owner authentication state is unavailable"
            )
        if state.legacy_token_version < 1:
            raise LegacyOwnerAuthStateUnavailableError(
                "Legacy-owner authentication version is invalid"
            )
        if state.mode != cls.MODE_LEGACY and state.owner_staff_user_id is None:
            raise LegacyOwnerAuthStateUnavailableError(
                "Staff authentication state is not bound to an owner"
            )
        return state


__all__ = [
    "LegacyOwnerAuthStateService",
    "LegacyOwnerAuthStateUnavailableError",
]
