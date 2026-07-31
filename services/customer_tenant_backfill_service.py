from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from crud.customer_tenant_backfill import (
    CustomerTenantBackfillDAO,
    TenantOwnedEntityCounts,
)
from models import Customer, CustomerRequisitesRecognition
from models.tenancy import TenantScope
from services.tenant_scope_service import SystemTenantScopeResolver


class CustomerTenantBackfillBlockedError(RuntimeError):
    """Raised when the reviewed Customer backfill is stale or unsafe."""


class CustomerTenantBackfillService:
    """Plan or stage one atomic Customer/OCR ownership batch."""

    MIN_LIMIT = 1
    MAX_LIMIT = 1000

    @classmethod
    async def run(
        cls,
        session: AsyncSession,
        *,
        execute: bool,
        limit_per_table: int = 100,
        expected_tenant_id: int | None = None,
        expected_storefront_id: int | None = None,
        plan_token: str | None = None,
    ) -> dict[str, Any]:
        limit = cls._validate_limit(limit_per_table)
        if execute:
            cls._validate_confirmation(
                expected_tenant_id=expected_tenant_id,
                expected_storefront_id=expected_storefront_id,
                plan_token=plan_token,
            )
            if not await CustomerTenantBackfillDAO.try_acquire_transaction_lock(
                session
            ):
                raise CustomerTenantBackfillBlockedError(
                    "Another Customer tenant backfill is already running"
                )

        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        if execute:
            cls._assert_expected_scope(
                tenant_scope,
                expected_tenant_id=expected_tenant_id,
                expected_storefront_id=expected_storefront_id,
            )

        before = await cls._inspect(session, tenant_scope=tenant_scope)
        candidate_ids = await cls._candidate_ids(
            session,
            limit=limit,
            lock_rows=execute,
        )
        blockers = cls._blocking_reasons(before)
        computed_token = cls._plan_token(
            tenant_scope=tenant_scope,
            limit=limit,
            reports=before,
            candidate_ids=candidate_ids,
        )
        result = {
            "dry_run": not execute,
            "tenant_id": tenant_scope.tenant_id,
            "storefront_id": tenant_scope.storefront_id,
            "limit_per_table": limit,
            "before": cls._reports_to_dict(before),
            "planned": candidate_ids,
            "plan_token": computed_token,
            "ready_for_backfill": not blockers,
            "blockers": blockers,
            "updated": {"customer": 0, "recognition": 0},
            "after": None,
            "contract_ready": cls._contract_ready(before, blockers),
        }
        if not execute:
            return result
        if blockers:
            raise CustomerTenantBackfillBlockedError(
                "Backfill preflight found ownership anomalies: "
                + "; ".join(blockers)
            )
        if not hmac.compare_digest(str(plan_token), computed_token):
            raise CustomerTenantBackfillBlockedError(
                "Backfill plan token is stale; run a fresh dry-run"
            )

        updated = {
            "customer": await CustomerTenantBackfillDAO.assign_tenant(
                session,
                entity=Customer,
                ids=candidate_ids["customer"],
                tenant_id=tenant_scope.tenant_id,
            ),
            "recognition": await CustomerTenantBackfillDAO.assign_tenant(
                session,
                entity=CustomerRequisitesRecognition,
                ids=candidate_ids["recognition"],
                tenant_id=tenant_scope.tenant_id,
            ),
        }
        cls._assert_exact_updates(candidate_ids, updated)
        after = await cls._inspect(session, tenant_scope=tenant_scope)
        after_blockers = cls._blocking_reasons(after)
        if after_blockers:
            raise CustomerTenantBackfillBlockedError(
                "Backfill post-check found ownership anomalies: "
                + "; ".join(after_blockers)
            )
        return {
            **result,
            "updated": {
                entity: len(ids) for entity, ids in updated.items()
            },
            "updated_ids": updated,
            "after": cls._reports_to_dict(after),
            "contract_ready": cls._contract_ready(after, after_blockers),
        }

    @staticmethod
    async def _inspect(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> dict[str, TenantOwnedEntityCounts]:
        return {
            "customer": await CustomerTenantBackfillDAO.inspect(
                session,
                entity=Customer,
                tenant_id=tenant_scope.tenant_id,
            ),
            "recognition": await CustomerTenantBackfillDAO.inspect(
                session,
                entity=CustomerRequisitesRecognition,
                tenant_id=tenant_scope.tenant_id,
            ),
        }

    @staticmethod
    async def _candidate_ids(
        session: AsyncSession,
        *,
        limit: int,
        lock_rows: bool,
    ) -> dict[str, list[int]]:
        return {
            "customer": await CustomerTenantBackfillDAO.list_legacy_ids(
                session,
                entity=Customer,
                limit=limit,
                lock_rows=lock_rows,
            ),
            "recognition": await CustomerTenantBackfillDAO.list_legacy_ids(
                session,
                entity=CustomerRequisitesRecognition,
                limit=limit,
                lock_rows=lock_rows,
            ),
        }

    @staticmethod
    def _reports_to_dict(
        reports: dict[str, TenantOwnedEntityCounts],
    ) -> dict[str, dict[str, int | str]]:
        return {
            entity: report.to_dict()
            for entity, report in reports.items()
        }

    @staticmethod
    def _blocking_reasons(
        reports: dict[str, TenantOwnedEntityCounts],
    ) -> list[str]:
        blockers: list[str] = []
        for entity, report in reports.items():
            classified = (
                report.legacy_null
                + report.target_scoped
                + report.unexpected_scoped
            )
            if classified != report.total:
                blockers.append(
                    f"{entity}: classification mismatch "
                    f"({classified} classified, {report.total} total)"
                )
            if report.unexpected_scoped:
                blockers.append(
                    f"{entity}: unexpected_scoped={report.unexpected_scoped}"
                )
            if report.unknown_tenant:
                blockers.append(
                    f"{entity}: unknown_tenant={report.unknown_tenant}"
                )
        return blockers

    @staticmethod
    def _contract_ready(
        reports: dict[str, TenantOwnedEntityCounts],
        blockers: list[str],
    ) -> bool:
        return not blockers and all(
            report.legacy_null == 0 for report in reports.values()
        )

    @staticmethod
    def _plan_token(
        *,
        tenant_scope: TenantScope,
        limit: int,
        reports: dict[str, TenantOwnedEntityCounts],
        candidate_ids: dict[str, list[int]],
    ) -> str:
        payload = {
            "version": 1,
            "tenant_id": tenant_scope.tenant_id,
            "storefront_id": tenant_scope.storefront_id,
            "limit_per_table": limit,
            "legacy_null": {
                entity: report.legacy_null
                for entity, report in reports.items()
            },
            "anomalies": {
                entity: {
                    "unexpected_scoped": report.unexpected_scoped,
                    "unknown_tenant": report.unknown_tenant,
                }
                for entity, report in reports.items()
            },
            "candidate_ids": candidate_ids,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _validate_limit(cls, value: int) -> int:
        limit = int(value)
        if limit < cls.MIN_LIMIT or limit > cls.MAX_LIMIT:
            raise ValueError(
                f"limit_per_table must be between {cls.MIN_LIMIT} and {cls.MAX_LIMIT}"
            )
        return limit

    @staticmethod
    def _validate_confirmation(
        *,
        expected_tenant_id: int | None,
        expected_storefront_id: int | None,
        plan_token: str | None,
    ) -> None:
        if not expected_tenant_id or not expected_storefront_id:
            raise CustomerTenantBackfillBlockedError(
                "Execute requires positive expected tenant and storefront IDs"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", str(plan_token or "")):
            raise CustomerTenantBackfillBlockedError(
                "Execute requires the plan token from dry-run"
            )

    @staticmethod
    def _assert_expected_scope(
        tenant_scope: TenantScope,
        *,
        expected_tenant_id: int | None,
        expected_storefront_id: int | None,
    ) -> None:
        if (
            tenant_scope.tenant_id != expected_tenant_id
            or tenant_scope.storefront_id != expected_storefront_id
        ):
            raise CustomerTenantBackfillBlockedError(
                "Resolved scope does not match the reviewed scope"
            )

    @staticmethod
    def _assert_exact_updates(
        planned: dict[str, list[int]],
        updated: dict[str, list[int]],
    ) -> None:
        for entity in ("customer", "recognition"):
            if sorted(planned[entity]) != sorted(updated[entity]):
                raise CustomerTenantBackfillBlockedError(
                    f"{entity}: updated IDs differ from the reviewed plan"
                )
