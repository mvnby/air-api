"""Trusted actor shared by Manager and external application commands."""

from dataclasses import dataclass

from fastapi import Header, HTTPException

from core.security import AuthenticatedUser
from models.tenancy import TenantScope
from services.public_write_idempotency_service import PublicWriteIdempotencyService


@dataclass(frozen=True)
class CommandActor:
    staff_user_id: int
    username: str
    tenant_scope: TenantScope
    channel: str = "manager"

    @classmethod
    def from_auth(
        cls, auth: AuthenticatedUser, channel: str = "manager"
    ) -> "CommandActor":
        if not auth.staff_user_id or auth.role not in {"owner", "admin", "manager"}:
            raise HTTPException(status_code=403, detail="Staff account required")
        if auth.must_change_password:
            raise HTTPException(status_code=403, detail="Change your password first")
        return cls(auth.staff_user_id, auth.username, auth.tenant_scope(), channel)


async def get_command_idempotency_key(
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> str:
    try:
        return PublicWriteIdempotencyService.normalize_key(idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
