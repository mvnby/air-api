"""Mode-specific authentication guard for the runtime legacy owner cutover."""

from __future__ import annotations

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models import LegacyOwnerAuthState
from services.legacy_owner_auth_state_service import LegacyOwnerAuthStateService


class LegacyOwnerAuthGuard:
    MODE_LEGACY = LegacyOwnerAuthStateService.MODE_LEGACY
    STAFF_MODES = frozenset(
        {
            LegacyOwnerAuthStateService.MODE_STAFF_SHADOW,
            LegacyOwnerAuthStateService.MODE_STAFF,
        }
    )

    @staticmethod
    def configured_username_matches(username: str) -> bool:
        configured = str(settings.ADMIN_USERNAME or "")
        candidate = str(username or "")
        if not configured or not candidate:
            return False
        return secrets.compare_digest(
            candidate.encode("utf-8", errors="surrogatepass"),
            configured.encode("utf-8", errors="surrogatepass"),
        )

    @classmethod
    async def state(
        cls,
        session: AsyncSession,
        *,
        for_update: bool = False,
        for_share: bool = False,
    ) -> LegacyOwnerAuthState:
        return await LegacyOwnerAuthStateService.get(
            session,
            for_update=for_update,
            for_share=for_share,
        )

    @classmethod
    def allows_legacy_token(
        cls,
        state: LegacyOwnerAuthState,
        *,
        token_version: object,
    ) -> bool:
        if state.mode != cls.MODE_LEGACY:
            return False
        # Tokens issued before the compatibility migration had no version.
        # They are accepted only during the untouched initial epoch.
        if token_version is None:
            return int(state.legacy_token_version) == 1
        if isinstance(token_version, bool):
            return False
        try:
            parsed = int(token_version)
        except (TypeError, ValueError):
            return False
        return secrets.compare_digest(
            str(parsed),
            str(int(state.legacy_token_version)),
        )

    @classmethod
    def allows_bound_staff(
        cls,
        state: LegacyOwnerAuthState,
        *,
        staff_user_id: int,
    ) -> bool:
        return (
            state.mode in cls.STAFF_MODES
            and state.owner_staff_user_id is not None
            and secrets.compare_digest(
                str(int(staff_user_id)),
                str(int(state.owner_staff_user_id)),
            )
        )

    @classmethod
    def allows_staff_identity(
        cls,
        state: LegacyOwnerAuthState,
        *,
        staff_user_id: int,
        username: str,
    ) -> bool:
        """Fence both the configured name and the durable bound identity.

        The ID check prevents a renamed shadow owner (or a Telegram login for
        that owner) from surviving a rollback to legacy authentication.
        """
        is_bound_owner = (
            state.owner_staff_user_id is not None
            and secrets.compare_digest(
                str(int(staff_user_id)),
                str(int(state.owner_staff_user_id)),
            )
        )
        is_configured_identity = cls.configured_username_matches(username)
        if not is_bound_owner and not is_configured_identity:
            return True
        return (
            is_bound_owner
            and is_configured_identity
            and state.mode in cls.STAFF_MODES
        )


__all__ = ["LegacyOwnerAuthGuard"]
