from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings


class ReadinessService:
    _SCHEDULER_STATUSES = {
        "disabled",
        "waiting_lock",
        "fencing",
        "running",
        "retrying",
        "faulted",
        "stopped",
    }
    _SCHEDULER_REASONS = {
        "runtime_control_disabled",
        "lock_acquisition_pending",
        "previous_owner_fencing",
        "scheduler_loop_running",
        "attempt_failed_retry_scheduled",
        "ownership_lost",
        "scheduler_loop_failed",
        "application_shutdown",
    }

    @staticmethod
    def _scheduler_runtime_payload(
        snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        decision = settings.scheduler_control_decision
        fallback = {
            "expected": decision.enabled,
            "status": "waiting_lock" if decision.enabled else "disabled",
            "reason": "runtime_state_unavailable",
            "changed_at": None,
        }
        if not isinstance(snapshot, dict):
            return fallback

        expected = snapshot.get("expected")
        status = snapshot.get("status")
        reason = snapshot.get("reason")
        changed_at = snapshot.get("changed_at")
        changed_at_valid = False
        if isinstance(changed_at, str) and len(changed_at) <= 64:
            try:
                changed_at_valid = datetime.fromisoformat(changed_at).tzinfo is not None
            except ValueError:
                changed_at_valid = False
        if (
            not isinstance(expected, bool)
            or status not in ReadinessService._SCHEDULER_STATUSES
            or reason not in ReadinessService._SCHEDULER_REASONS
            or not changed_at_valid
        ):
            return fallback
        return {
            "expected": expected,
            "status": status,
            "reason": reason,
            "changed_at": changed_at,
        }

    @staticmethod
    async def check(
        session: AsyncSession,
        *,
        scheduler_runtime: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        decision = settings.api_ready_control_decision
        payload: dict[str, Any] = {
            "status": "ok",
            "api": "ready",
            "app_role": settings.APP_ROLE,
            "traffic": "enabled" if decision.enabled else "disabled",
            "reason": decision.reason,
            "scheduler_runtime": ReadinessService._scheduler_runtime_payload(
                scheduler_runtime
            ),
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
