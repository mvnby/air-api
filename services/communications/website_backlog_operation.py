from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CommunicationWebsiteBacklogOperation
from services.communications.backlog_reconciliation import (
    InstallationEstimateBacklogExecutionBlocked,
)
from services.communications.website_backlog_reconciliation import (
    WebsiteBacklogManifestItem,
    WebsiteBacklogManifestReport,
    WebsiteBacklogTypeReport,
    WebsiteCommunicationBacklogReconciliation,
)
from services.runtime_lock_service import RuntimeLock


class WebsiteBacklogOperationFailed(RuntimeError):
    def __init__(self, error_code: str = "website_backlog_operation_failed") -> None:
        self.error_code = error_code
        super().__init__(error_code)


class WebsiteBacklogOperationManifestMismatch(
    InstallationEstimateBacklogExecutionBlocked
):
    pass


class WebsiteBacklogOperationRunner:
    """Run mutations and a one-way PII-free operation audit transactionally."""

    @staticmethod
    def canonical_manifest(
        manifest: tuple[WebsiteBacklogManifestItem, ...],
    ) -> tuple[tuple[WebsiteBacklogManifestItem, ...], dict, str]:
        ordered = WebsiteCommunicationBacklogReconciliation._validate_manifest(
            manifest,
            execute=True,
        )
        summary = {
            "version": 1,
            "event_types": [
                {
                    "event_type": item.event_type,
                    "cutoff": item.cutoff.astimezone(timezone.utc).isoformat(),
                    "expected_count": item.expected_count,
                    "disposition": item.disposition,
                }
                for item in ordered
            ],
        }
        canonical = json.dumps(
            summary,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return ordered, summary, hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _fallback_counts(
        manifest_summary: dict,
    ) -> dict:
        return {
            "activation_safe": False,
            "event_types": [
                {
                    **entry,
                    "candidate_count": None,
                    "selected_count": None,
                    "nonterminal_delivery_count": None,
                    "ambiguous_delivery_count": None,
                    "conflict_count": None,
                    "inventory_overflow_count": None,
                    "terminalized_count": 0,
                    "terminalized_delivery_count": 0,
                    "remaining_candidate_count": None,
                    "activation_blocked": True,
                }
                for entry in manifest_summary["event_types"]
            ],
        }

    @staticmethod
    def _report_counts(report: WebsiteBacklogManifestReport) -> dict:
        payload = report.to_dict()
        return {
            "activation_safe": payload["activation_safe"],
            "event_types": payload["event_types"],
        }

    @staticmethod
    def _report_from_operation(
        operation: CommunicationWebsiteBacklogOperation,
    ) -> WebsiteBacklogManifestReport:
        counts = dict(operation.aggregate_counts or {})
        return WebsiteBacklogManifestReport(
            mode="execute",
            operation_id=operation.operation_id,
            event_types=tuple(
                WebsiteBacklogTypeReport(**item)
                for item in counts.get("event_types", [])
            ),
            activation_safe=bool(counts.get("activation_safe", False)),
        )

    @staticmethod
    def _raise_replayed_failure(
        operation: CommunicationWebsiteBacklogOperation,
    ) -> None:
        if operation.state == "blocked":
            raise InstallationEstimateBacklogExecutionBlocked(
                operation.outcome_code or "website_backlog_operation_blocked"
            )
        raise WebsiteBacklogOperationFailed(
            operation.outcome_code or "website_backlog_operation_failed"
        )

    @classmethod
    async def _ensure_started(
        cls,
        session_factory: Callable[[], AsyncSession],
        *,
        operation_id: str,
        manifest_fingerprint: str,
        manifest_summary: dict,
        created_at: datetime,
    ) -> None:
        async with session_factory() as session:
            values = {
                "operation_id": operation_id,
                "manifest_fingerprint": manifest_fingerprint,
                "manifest_summary": manifest_summary,
                "state": "started",
                "created_at": created_at,
            }
            dialect = session.get_bind().dialect.name
            if dialect == "postgresql":
                statement = postgresql_insert(
                    CommunicationWebsiteBacklogOperation
                ).values(**values)
            elif dialect == "sqlite":
                statement = sqlite_insert(
                    CommunicationWebsiteBacklogOperation
                ).values(**values)
            else:
                raise NotImplementedError(
                    f"Website backlog operation is unsupported for {dialect!r}"
                )
            await session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=["operation_id"]
                )
            )
            await session.commit()

    @staticmethod
    async def _lock_operation(
        session: AsyncSession,
        *,
        operation_id: str,
    ) -> CommunicationWebsiteBacklogOperation:
        statement = select(CommunicationWebsiteBacklogOperation).where(
            CommunicationWebsiteBacklogOperation.operation_id == operation_id
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        operation = (await session.execute(statement)).scalar_one_or_none()
        if operation is None:  # pragma: no cover - inserted immediately before
            raise WebsiteBacklogOperationFailed(
                "website_backlog_operation_missing"
            )
        return operation

    @staticmethod
    def _assert_manifest(
        operation: CommunicationWebsiteBacklogOperation,
        *,
        manifest_fingerprint: str,
        manifest_summary: dict,
    ) -> None:
        if (
            operation.manifest_fingerprint != manifest_fingerprint
            or dict(operation.manifest_summary or {}) != manifest_summary
        ):
            raise WebsiteBacklogOperationManifestMismatch(
                "website_backlog_operation_manifest_mismatch"
            )

    @classmethod
    async def _terminalize_failure(
        cls,
        session_factory: Callable[[], AsyncSession],
        *,
        operation_id: str,
        manifest_fingerprint: str,
        manifest_summary: dict,
        state: str,
        outcome_code: str,
        finished_at: datetime,
    ) -> None:
        async with session_factory() as session:
            operation = await cls._lock_operation(
                session,
                operation_id=operation_id,
            )
            cls._assert_manifest(
                operation,
                manifest_fingerprint=manifest_fingerprint,
                manifest_summary=manifest_summary,
            )
            if operation.state != "started":
                await session.rollback()
                return
            operation.state = state
            operation.outcome_code = outcome_code[:100]
            operation.aggregate_counts = cls._fallback_counts(manifest_summary)
            operation.finished_at = finished_at
            session.add(operation)
            await session.commit()

    @classmethod
    async def execute_manifest(
        cls,
        session_factory: Callable[[], AsyncSession],
        *,
        manifest: tuple[WebsiteBacklogManifestItem, ...],
        operation_id: str,
        runtime_lock: RuntimeLock | None,
        app_role: str | None,
        now: datetime | None = None,
    ) -> WebsiteBacklogManifestReport:
        normalized_operation_id = (
            WebsiteCommunicationBacklogReconciliation.normalize_operation_id(
                operation_id
            )
        )
        ordered, manifest_summary, fingerprint = cls.canonical_manifest(manifest)
        operation_time = now or datetime.now(timezone.utc)
        if operation_time.tzinfo is None or operation_time.utcoffset() is None:
            raise ValueError("now must include a timezone")
        operation_time = operation_time.astimezone(timezone.utc)
        await cls._ensure_started(
            session_factory,
            operation_id=normalized_operation_id,
            manifest_fingerprint=fingerprint,
            manifest_summary=manifest_summary,
            created_at=operation_time,
        )

        try:
            async with session_factory() as session:
                operation = await cls._lock_operation(
                    session,
                    operation_id=normalized_operation_id,
                )
                cls._assert_manifest(
                    operation,
                    manifest_fingerprint=fingerprint,
                    manifest_summary=manifest_summary,
                )
                if operation.state == "succeeded":
                    report = cls._report_from_operation(operation)
                    await session.rollback()
                    return report
                if operation.state != "started":
                    cls._raise_replayed_failure(operation)
                report = await WebsiteCommunicationBacklogReconciliation.reconcile_manifest(
                    session,
                    manifest=ordered,
                    operation_id=normalized_operation_id,
                    execute=True,
                    now=operation_time,
                    runtime_lock=runtime_lock,
                    app_role=app_role,
                )
                if runtime_lock is None or not await runtime_lock.is_held():
                    raise InstallationEstimateBacklogExecutionBlocked(
                        "communications_runtime_lock_lost"
                    )
                operation.state = "succeeded"
                operation.outcome_code = "succeeded"
                operation.aggregate_counts = cls._report_counts(report)
                operation.finished_at = operation_time
                session.add(operation)
                await session.commit()
                return report
        except WebsiteBacklogOperationManifestMismatch:
            raise
        except InstallationEstimateBacklogExecutionBlocked as error:
            await cls._terminalize_failure(
                session_factory,
                operation_id=normalized_operation_id,
                manifest_fingerprint=fingerprint,
                manifest_summary=manifest_summary,
                state="blocked",
                outcome_code=error.error_code,
                finished_at=operation_time,
            )
            raise
        except Exception:
            await cls._terminalize_failure(
                session_factory,
                operation_id=normalized_operation_id,
                manifest_fingerprint=fingerprint,
                manifest_summary=manifest_summary,
                state="failed",
                outcome_code="website_backlog_operation_failed",
                finished_at=operation_time,
            )
            raise
