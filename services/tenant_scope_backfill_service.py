from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from crud.tenant_scope_backfill import (
    TenantScopeBackfillDAO,
    TenantScopeEntityCounts,
)
from models import Lead, Order
from models.tenancy import TenantScope
from services.tenant_scope_service import SystemTenantScopeResolver


class TenantScopeBackfillBlockedError(RuntimeError):
    """Raised when the reviewed backfill plan is stale or unsafe."""


class TenantScopeBackfillService:
    """Plan or stage one atomic batch; the command handler owns commit/rollback."""

    MIN_LIMIT = 1
    MAX_LIMIT = 1000

    @classmethod
    async def run(
        cls,
        session: AsyncSession,
        *,
        execute: bool,
        limit_per_table: int = 100,
        tenant_slug: str = "mvn",
        storefront_slug: str = "main",
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

        if execute and not await TenantScopeBackfillDAO.try_acquire_transaction_lock(
            session
        ):
            raise TenantScopeBackfillBlockedError(
                "Another tenant-scope backfill transaction is already running"
            )

        tenant_scope = await SystemTenantScopeResolver.resolve(
            session,
            tenant_slug=tenant_slug,
            storefront_slug=storefront_slug,
        )
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
            "tenant_slug": tenant_slug,
            "storefront_slug": storefront_slug,
            "tenant_id": tenant_scope.tenant_id,
            "storefront_id": tenant_scope.storefront_id,
            "limit_per_table": limit,
            "before": cls._reports_to_dict(before),
            "planned": candidate_ids,
            "planned_counts": {
                entity: len(ids) for entity, ids in candidate_ids.items()
            },
            "plan_token": computed_token,
            "ready_for_backfill": not blockers,
            "blockers": blockers,
            "updated": {"lead": 0, "order": 0},
            "after": None,
            "contract_ready": cls._contract_ready(before, blockers=blockers),
        }
        if not execute:
            return result

        if blockers:
            raise TenantScopeBackfillBlockedError(
                "Backfill preflight found blocking provenance anomalies: "
                + "; ".join(blockers)
            )
        if not hmac.compare_digest(str(plan_token), computed_token):
            raise TenantScopeBackfillBlockedError(
                "Backfill plan token is stale; run a fresh dry-run"
            )

        updated = {
            "lead": await TenantScopeBackfillDAO.assign_scope(
                session,
                entity=Lead,
                ids=candidate_ids["lead"],
                tenant_scope=tenant_scope,
            ),
            "order": await TenantScopeBackfillDAO.assign_scope(
                session,
                entity=Order,
                ids=candidate_ids["order"],
                tenant_scope=tenant_scope,
            ),
        }
        cls._assert_exact_updates(candidate_ids, updated)

        after = await cls._inspect(session, tenant_scope=tenant_scope)
        after_blockers = cls._blocking_reasons(after)
        if after_blockers:
            raise TenantScopeBackfillBlockedError(
                "Backfill post-check found blocking provenance anomalies: "
                + "; ".join(after_blockers)
            )

        return {
            **result,
            "updated": {
                entity: len(ids) for entity, ids in updated.items()
            },
            "updated_ids": updated,
            "after": cls._reports_to_dict(after),
            "contract_ready": cls._contract_ready(
                after,
                blockers=after_blockers,
            ),
        }

    @classmethod
    async def _inspect(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> dict[str, TenantScopeEntityCounts]:
        return {
            "lead": await TenantScopeBackfillDAO.inspect(
                session,
                entity=Lead,
                tenant_scope=tenant_scope,
            ),
            "order": await TenantScopeBackfillDAO.inspect(
                session,
                entity=Order,
                tenant_scope=tenant_scope,
            ),
        }

    @classmethod
    async def _candidate_ids(
        cls,
        session: AsyncSession,
        *,
        limit: int,
        lock_rows: bool,
    ) -> dict[str, list[int]]:
        return {
            "lead": await TenantScopeBackfillDAO.list_legacy_ids(
                session,
                entity=Lead,
                limit=limit,
                lock_rows=lock_rows,
            ),
            "order": await TenantScopeBackfillDAO.list_legacy_ids(
                session,
                entity=Order,
                limit=limit,
                lock_rows=lock_rows,
            ),
        }

    @staticmethod
    def _reports_to_dict(
        reports: dict[str, TenantScopeEntityCounts],
    ) -> dict[str, dict[str, int | str]]:
        return {
            entity: report.to_dict()
            for entity, report in reports.items()
        }

    @staticmethod
    def _blocking_reasons(
        reports: dict[str, TenantScopeEntityCounts],
    ) -> list[str]:
        blockers: list[str] = []
        for entity, report in reports.items():
            classified = (
                report.legacy_null
                + report.target_scoped
                + report.partial
                + report.unexpected_scoped
            )
            if classified != report.total:
                blockers.append(
                    f"{entity}: classification mismatch "
                    f"({classified} classified, {report.total} total)"
                )
            for field in (
                "partial",
                "unexpected_scoped",
                "unknown_tenant",
                "unknown_storefront",
                "cross_tenant",
            ):
                value = int(getattr(report, field))
                if value:
                    blockers.append(f"{entity}: {field}={value}")
        return blockers

    @staticmethod
    def _contract_ready(
        reports: dict[str, TenantScopeEntityCounts],
        *,
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
        reports: dict[str, TenantScopeEntityCounts],
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
                    "partial": report.partial,
                    "unexpected_scoped": report.unexpected_scoped,
                    "unknown_tenant": report.unknown_tenant,
                    "unknown_storefront": report.unknown_storefront,
                    "cross_tenant": report.cross_tenant,
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
            raise TenantScopeBackfillBlockedError(
                "Execute requires positive expected tenant and storefront IDs"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", str(plan_token or "")):
            raise TenantScopeBackfillBlockedError(
                "Execute requires the 64-character plan token from dry-run"
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
            raise TenantScopeBackfillBlockedError(
                "Resolved tenant/storefront IDs do not match the reviewed scope"
            )

    @staticmethod
    def _assert_exact_updates(
        planned: dict[str, list[int]],
        updated: dict[str, list[int]],
    ) -> None:
        for entity in ("lead", "order"):
            if sorted(planned[entity]) != sorted(updated[entity]):
                raise TenantScopeBackfillBlockedError(
                    f"{entity}: updated IDs differ from the reviewed plan"
                )
