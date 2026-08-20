"""Atomic self-service credential rotation for authenticated manager staff."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.request_context import current_request_id
from models import StaffUser, TenantAuditEvent, TenantMembership
from models.tenancy import TenantScope
from services.credential_service import CredentialPolicyError, CredentialService
from services.legacy_owner_managed_identity_service import (
    LegacyOwnerManagedIdentityError,
    LegacyOwnerManagedIdentityService,
)


class ManagerAccountCredentialError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ManagerAccountCredentialService:
    AUDIT_ACTION = "staff_credential.changed"

    @classmethod
    async def change_password(
        cls,
        session: AsyncSession,
        *,
        staff_user_id: int,
        actor_username: str,
        tenant_scope: TenantScope,
        current_password: str,
        new_password: str,
    ) -> None:
        try:
            await LegacyOwnerManagedIdentityService.ensure_self_service_allowed(
                session,
                staff_user_id=staff_user_id,
            )
        except LegacyOwnerManagedIdentityError as exc:
            raise ManagerAccountCredentialError(
                "self_service_unavailable",
                "Для legacy-владельца смена пароля сейчас недоступна",
            ) from exc
        staff_user = (
            await session.execute(
                select(StaffUser)
                .join(
                    TenantMembership,
                    TenantMembership.staff_user_id == StaffUser.id,
                )
                .where(
                    StaffUser.id == staff_user_id,
                    TenantMembership.tenant_id == tenant_scope.tenant_id,
                    TenantMembership.status == "active",
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if staff_user is None:
            raise ManagerAccountCredentialError(
                "invalid_session",
                "Активная учётная запись сотрудника не найдена",
            )
        if not CredentialService.verify_password(
            current_password,
            staff_user.password_hash,
        ):
            raise ManagerAccountCredentialError(
                "invalid_current_password",
                "Текущий пароль указан неверно",
            )
        if CredentialService.verify_password(new_password, staff_user.password_hash):
            raise ManagerAccountCredentialError(
                "password_reuse",
                "Новый пароль должен отличаться от текущего",
            )
        try:
            validated_password = CredentialService.validate_password(new_password)
        except CredentialPolicyError as exc:
            raise ManagerAccountCredentialError(exc.code, str(exc)) from exc

        previous_version = int(staff_user.auth_version)
        changed_at = datetime.now(timezone.utc)
        staff_user.password_hash = CredentialService.hash_password(validated_password)
        staff_user.password_changed_at = changed_at
        staff_user.auth_version = previous_version + 1
        staff_user.must_change_password = False
        session.add(staff_user)
        session.add(
            TenantAuditEvent(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
                actor_staff_user_id=staff_user_id,
                actor_username=actor_username,
                action=cls.AUDIT_ACTION,
                entity_type="staff_user",
                entity_id=staff_user_id,
                request_id=current_request_id(),
                change_set={
                    "auth_version": {
                        "before": previous_version,
                        "after": previous_version + 1,
                    },
                    "required_change_cleared": True,
                },
            )
        )
        await session.commit()


__all__ = ["ManagerAccountCredentialError", "ManagerAccountCredentialService"]
