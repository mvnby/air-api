"""Mutation fence for the durable legacy-owner StaffUser binding."""

from __future__ import annotations

import json
import secrets

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import LegacyOwnerAuthState, StaffUser, Tenant, TenantMembership
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_auth_state_service import LegacyOwnerAuthStateService


def _normalized_roles(value: object) -> list[str]:
    roles = value
    if isinstance(roles, str):
        try:
            parsed = json.loads(roles)
        except json.JSONDecodeError:
            parsed = [roles]
        roles = parsed if isinstance(parsed, list) else [roles]
    normalized: list[str] = []
    for item in roles if isinstance(roles, list) else []:
        role = str(item or "").strip().lower()
        if role and role not in normalized:
            normalized.append(role)
    return normalized


class LegacyOwnerManagedIdentityError(ValueError):
    code = "legacy_owner_managed"

    def __init__(self, message: str = "Legacy owner is managed by the dedicated cutover workflow") -> None:
        super().__init__(message)


class LegacyOwnerManagedIdentityService:
    @staticmethod
    def is_bound(state: LegacyOwnerAuthState, *, staff_user_id: int) -> bool:
        return (
            state.owner_staff_user_id is not None
            and secrets.compare_digest(
                str(int(state.owner_staff_user_id)),
                str(int(staff_user_id)),
            )
        )

    @classmethod
    async def ensure_generic_mutation_allowed(
        cls,
        session: AsyncSession,
        *,
        staff_user_id: int,
        tenant_id: int,
    ) -> LegacyOwnerAuthState | None:
        visible = await session.scalar(
            select(TenantMembership.id).where(
                TenantMembership.staff_user_id == staff_user_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )
        if visible is None:
            return None
        state = await LegacyOwnerAuthStateService.get(session, for_update=True)
        if cls.is_bound(state, staff_user_id=staff_user_id):
            raise LegacyOwnerManagedIdentityError()
        return state

    @classmethod
    async def ensure_self_service_allowed(
        cls,
        session: AsyncSession,
        *,
        staff_user_id: int,
    ) -> LegacyOwnerAuthState:
        state = await LegacyOwnerAuthStateService.get(session, for_update=True)
        if (
            cls.is_bound(state, staff_user_id=staff_user_id)
            and state.mode == LegacyOwnerAuthStateService.MODE_LEGACY
        ):
            raise LegacyOwnerManagedIdentityError(
                "Legacy owner self-service is unavailable while legacy authentication is active"
            )
        if cls.is_bound(state, staff_user_id=staff_user_id):
            user = await session.get(StaffUser, staff_user_id)
            if user is None or not await cls.exact_bound_staff_identity_allowed(
                session,
                state=state,
                user=user,
            ):
                raise LegacyOwnerManagedIdentityError(
                    "Bound legacy owner identity is not in the reviewed staff state"
                )
        return state

    @classmethod
    async def exact_bound_staff_identity_allowed(
        cls,
        session: AsyncSession,
        *,
        state: LegacyOwnerAuthState,
        user: StaffUser,
    ) -> bool:
        if not (
            user.id is not None
            and cls.is_bound(state, staff_user_id=int(user.id))
            and state.mode
            in {
                LegacyOwnerAuthStateService.MODE_STAFF_SHADOW,
                LegacyOwnerAuthStateService.MODE_STAFF,
            }
            and LegacyOwnerAuthGuard.configured_username_matches(
                str(user.username or "")
            )
            and str(user.status or "").strip().lower() == "active"
            and str(user.primary_role or "").strip().lower() == "owner"
            and _normalized_roles(user.roles) == ["owner"]
            and user.legacy_installer_id is None
        ):
            return False
        memberships = list(
            (
                await session.execute(
                    select(TenantMembership, Tenant)
                    .join(Tenant, Tenant.id == TenantMembership.tenant_id)
                    .where(TenantMembership.staff_user_id == int(user.id))
                )
            ).all()
        )
        if len(memberships) != 1:
            return False
        membership, tenant = memberships[0]
        return bool(
            membership.status == "active"
            and membership.role == "owner"
            and tenant.slug == "mvn"
            and tenant.status == "active"
            and tenant.is_system
        )

    @classmethod
    async def telegram_login_allowed(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
    ) -> bool:
        state = await LegacyOwnerAuthStateService.get(session, for_update=True)
        user = (
            await session.execute(
                select(StaffUser).where(StaffUser.telegram_id == telegram_id)
            )
        ).scalar_one_or_none()
        if user is None:
            return True
        if not LegacyOwnerAuthGuard.allows_staff_identity(
            state,
            staff_user_id=int(user.id or 0),
            username=str(user.username or ""),
        ):
            return False
        if not cls.is_bound(state, staff_user_id=int(user.id or 0)):
            return True
        return await cls.exact_bound_staff_identity_allowed(
            session,
            state=state,
            user=user,
        )


__all__ = [
    "LegacyOwnerManagedIdentityError",
    "LegacyOwnerManagedIdentityService",
]
