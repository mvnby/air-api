from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings


class ReadinessService:
    @staticmethod
    async def check(session: AsyncSession) -> tuple[int, dict[str, Any]]:
        decision = settings.api_ready_control_decision
        payload: dict[str, Any] = {
            "status": "ok",
            "api": "ready",
            "app_role": settings.APP_ROLE,
            "traffic": "enabled" if decision.enabled else "disabled",
            "reason": decision.reason,
        }
        if not decision.enabled:
            payload.update({"status": "error", "api": "not_ready"})
            return 503, payload

        try:
            await session.execute(text("SELECT 1"))
        except Exception as exc:
            payload.update(
                {
                    "status": "error",
                    "api": "not_ready",
                    "database": "offline",
                    "detail": str(exc),
                }
            )
            return 503, payload

        payload["database"] = "online"
        bind = session.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
        if settings.READINESS_REQUIRE_WRITABLE_DB and dialect_name == "postgresql":
            recovery_result = await session.execute(text("SELECT pg_is_in_recovery()"))
            in_recovery = bool(recovery_result.scalar())
            read_only_result = await session.execute(text("SHOW transaction_read_only"))
            transaction_read_only = str(read_only_result.scalar() or "").lower() == "on"
            payload["database_writable"] = not in_recovery and not transaction_read_only
            if in_recovery or transaction_read_only:
                payload.update(
                    {
                        "status": "error",
                        "api": "not_ready",
                        "database": "read_only",
                    }
                )
                return 503, payload
        else:
            payload["database_writable"] = None

        return 200, payload
