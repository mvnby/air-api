"""Bounded, tenant-scoped import of Belzakupki opportunity matches."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from core.config import settings
from core.database import async_session_maker
from models import BelzakupkiImportCheckpoint, LeadSource, Order, OrderStatus
from models.tenancy import TenantScope
from services.tenant_scope_service import SystemTenantScopeResolver

logger = logging.getLogger(__name__)


@dataclass
class BelzakupkiImportResult:
    cursor_before: str | None = None
    cursor_after: str | None = None
    processed: int = 0
    accepted: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    stale: bool = False


class BelzakupkiImportService:
    """Import one remote page at a time so each poll remains bounded.

    The remote cursor is opaque and tenant-bound.  It is moved in the same
    transaction as the orders from its page, so a failed page is replayed.
    """

    META_KEY = "belzakupki"
    SOURCE_NAMESPACE = "belzakupki"

    @classmethod
    def is_configured(cls) -> bool:
        return bool(
            settings.BELZAKUPKI_IMPORT_ENABLED
            and str(settings.BELZAKUPKI_API_BASE_URL or "").strip()
            and settings.BELZAKUPKI_INTEGRATION_KEY
            and str(settings.BELZAKUPKI_IMPORT_TENANT_SLUG or "").strip()
            and str(settings.BELZAKUPKI_IMPORT_STOREFRONT_SLUG or "").strip()
        )

    @staticmethod
    def _clean_text(value: Any, *, maximum: int = 4000) -> str | None:
        cleaned = " ".join(str(value or "").split())
        return cleaned[:maximum] or None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _is_accepted(cls, item: dict[str, Any], *, now: datetime) -> bool:
        if not bool(item.get("eligible")):
            return False
        relevance = str(item.get("relevance_status") or "").strip()
        allowed = {"confirmed"}
        if settings.BELZAKUPKI_IMPORT_INCLUDE_RULES_ONLY:
            allowed.add("rules_only")
        if relevance not in allowed:
            return False
        tender = item.get("tender")
        if not isinstance(tender, dict):
            return False
        deadline = cls._parse_datetime(tender.get("deadline_at"))
        return deadline is None or deadline >= now

    @classmethod
    def _external_identity(cls, item: dict[str, Any]) -> tuple[str, str]:
        tender = item.get("tender")
        if not isinstance(tender, dict):
            raise ValueError("Belzakupki opportunity tender is required")
        source = cls._clean_text(tender.get("source"), maximum=100)
        external_id = cls._clean_text(tender.get("external_id"), maximum=300)
        if not source or not external_id:
            raise ValueError("Belzakupki tender source and external_id are required")
        return source, external_id

    @classmethod
    def _order_fingerprint(cls, *, source: str, external_id: str) -> str:
        raw = f"{cls.SOURCE_NAMESPACE}|{source.casefold()}|{external_id}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def _match_snapshot(cls, item: dict[str, Any]) -> dict[str, Any]:
        tender = item.get("tender")
        if not isinstance(tender, dict):
            raise ValueError("Belzakupki opportunity tender is required")
        match_id = item.get("id")
        if not isinstance(match_id, int):
            raise ValueError("Belzakupki opportunity id must be an integer")
        profile = item.get("profile")
        if not isinstance(profile, dict):
            raise ValueError("Belzakupki opportunity profile is required")

        return {
            "match_id": match_id,
            "updated_at": cls._clean_text(item.get("updated_at"), maximum=80),
            "profile": {
                "id": profile.get("id"),
                "name": cls._clean_text(profile.get("name"), maximum=500),
            },
            "score": item.get("score"),
            "relevance_status": cls._clean_text(item.get("relevance_status"), maximum=40),
            "eligible": bool(item.get("eligible")),
            "reason": cls._clean_text(item.get("reason"), maximum=4000),
            "ai_analysis": item.get("ai_analysis"),
            "tender": {
                "id": tender.get("id"),
                "source": cls._clean_text(tender.get("source"), maximum=100),
                "external_id": cls._clean_text(tender.get("external_id"), maximum=300),
                "title": cls._clean_text(tender.get("title"), maximum=1000),
                "customer_name": cls._clean_text(tender.get("customer_name"), maximum=1000),
                "url": cls._clean_text(tender.get("url"), maximum=2048),
                "deadline_at": cls._clean_text(tender.get("deadline_at"), maximum=80),
                "published_at": cls._clean_text(tender.get("published_at"), maximum=80),
                "estimated_value": tender.get("estimated_value"),
                "contacts": tender.get("contacts"),
                "ai_analysis": tender.get("ai_analysis"),
            },
        }

    @staticmethod
    def _snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
        canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _initial_comment(cls, snapshot: dict[str, Any]) -> str:
        tender = snapshot["tender"]
        lines = ["Тендер Belzakupki"]
        if tender.get("title"):
            lines.append(str(tender["title"]))
        if tender.get("customer_name"):
            lines.append(f"Заказчик: {tender['customer_name']}")
        if tender.get("deadline_at"):
            lines.append(f"Срок: {tender['deadline_at']}")
        if tender.get("estimated_value") is not None:
            lines.append(f"Оценочная стоимость: {tender['estimated_value']}")
        if tender.get("url"):
            lines.append(f"Ссылка: {tender['url']}")
        reason = cls._clean_text(snapshot.get("reason"), maximum=1200)
        if not reason:
            analysis = snapshot.get("ai_analysis")
            if isinstance(analysis, dict):
                reason = cls._clean_text(
                    analysis.get("relevance_explanation") or analysis.get("explanation"),
                    maximum=1200,
                )
        if reason:
            lines.append(f"Причина соответствия: {reason}")
        return "\n".join(lines)

    @classmethod
    def _next_metadata(
        cls,
        *,
        existing: dict[str, Any],
        snapshot: dict[str, Any],
        snapshot_fingerprint: str,
    ) -> dict[str, Any]:
        existing_matches = existing.get("matches") if isinstance(existing.get("matches"), dict) else {}
        matches = dict(existing_matches)
        matches[str(snapshot["match_id"])] = {
            "fingerprint": snapshot_fingerprint,
            "updated_at": snapshot.get("updated_at"),
            "profile": snapshot.get("profile"),
            "score": snapshot.get("score"),
            "relevance_status": snapshot.get("relevance_status"),
            "eligible": snapshot.get("eligible"),
            "reason": snapshot.get("reason"),
            "ai_analysis": snapshot.get("ai_analysis"),
        }
        return {
            "source": snapshot["tender"]["source"],
            "external_tender_id": snapshot["tender"]["external_id"],
            "tender": snapshot["tender"],
            "matches": matches,
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    async def _find_order(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        fingerprint: str,
        for_update: bool = False,
    ) -> Order | None:
        statement = select(Order).where(
            Order.tenant_id == tenant_scope.tenant_id,
            Order.storefront_id == tenant_scope.storefront_id,
            Order.source_fingerprint == fingerprint,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    @classmethod
    async def _upsert_opportunity(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        item: dict[str, Any],
        result: BelzakupkiImportResult,
        allow_create: bool,
    ) -> None:
        source, external_id = cls._external_identity(item)
        snapshot = cls._match_snapshot(item)
        snapshot_fingerprint = cls._snapshot_fingerprint(snapshot)
        fingerprint = cls._order_fingerprint(source=source, external_id=external_id)
        order = await cls._find_order(
            session,
            tenant_scope=tenant_scope,
            fingerprint=fingerprint,
            for_update=True,
        )

        if order is None:
            if not allow_create:
                result.skipped += 1
                return
            metadata = cls._next_metadata(
                existing={},
                snapshot=snapshot,
                snapshot_fingerprint=snapshot_fingerprint,
            )
            order = Order(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
                status=OrderStatus.NEW_LEAD,
                lead_source=LeadSource.BELZAKUPKI,
                title=snapshot["tender"].get("title"),
                comment=cls._initial_comment(snapshot),
                source_fingerprint=fingerprint,
                technical_meta={cls.META_KEY: metadata},
            )
            try:
                async with session.begin_nested():
                    session.add(order)
                    await session.flush()
            except IntegrityError:
                # A concurrent page may have inserted the same tender through a
                # different matching profile.  The unique order key is decisive.
                order = await cls._find_order(
                    session,
                    tenant_scope=tenant_scope,
                    fingerprint=fingerprint,
                    for_update=True,
                )
                if order is None:
                    raise
            else:
                result.created += 1
                return

        technical_meta = dict(order.technical_meta or {})
        provider_meta = technical_meta.get(cls.META_KEY)
        provider_meta = dict(provider_meta) if isinstance(provider_meta, dict) else {}
        existing_matches = provider_meta.get("matches") if isinstance(provider_meta.get("matches"), dict) else {}
        current_match = existing_matches.get(str(snapshot["match_id"]))
        if isinstance(current_match, dict) and current_match.get("fingerprint") == snapshot_fingerprint:
            result.unchanged += 1
            return

        # Deliberately mutate only source-owned technical metadata.  A manager's
        # title, comment, workflow and status remain untouched after first intake.
        technical_meta[cls.META_KEY] = cls._next_metadata(
            existing=provider_meta,
            snapshot=snapshot,
            snapshot_fingerprint=snapshot_fingerprint,
        )
        order.technical_meta = technical_meta
        flag_modified(order, "technical_meta")
        session.add(order)
        result.updated += 1

    @classmethod
    async def _locked_checkpoint(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> BelzakupkiImportCheckpoint:
        checkpoint = (
            await session.execute(
                select(BelzakupkiImportCheckpoint)
                .where(
                    BelzakupkiImportCheckpoint.tenant_id == tenant_scope.tenant_id,
                    BelzakupkiImportCheckpoint.storefront_id == tenant_scope.storefront_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if checkpoint is None:
            checkpoint = BelzakupkiImportCheckpoint(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
            )
            try:
                async with session.begin_nested():
                    session.add(checkpoint)
                    await session.flush()
            except IntegrityError:
                checkpoint = (
                    await session.execute(
                        select(BelzakupkiImportCheckpoint)
                        .where(
                            BelzakupkiImportCheckpoint.tenant_id == tenant_scope.tenant_id,
                            BelzakupkiImportCheckpoint.storefront_id == tenant_scope.storefront_id,
                        )
                        .with_for_update()
                    )
                ).scalar_one()
        return checkpoint

    @classmethod
    def _validate_page(cls, payload: Any) -> tuple[list[dict[str, Any]], str | None]:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("Belzakupki opportunities response must contain items")
        items = payload["items"]
        if not all(isinstance(item, dict) for item in items):
            raise ValueError("Belzakupki opportunity items must be objects")
        for item in items:
            if not isinstance(item.get("id"), int):
                raise ValueError("Belzakupki opportunity id must be an integer")
            if not isinstance(item.get("profile"), dict):
                raise ValueError("Belzakupki opportunity profile is required")
            if not isinstance(item.get("relevance_status"), str):
                raise ValueError("Belzakupki opportunity relevance_status is required")
            if not isinstance(item.get("eligible"), bool):
                raise ValueError("Belzakupki opportunity eligible must be boolean")
            if not isinstance(item.get("tender"), dict):
                raise ValueError("Belzakupki opportunity tender is required")
            if cls._parse_datetime(item.get("updated_at")) is None:
                raise ValueError("Belzakupki opportunity updated_at must be ISO datetime")
            deadline_at = item["tender"].get("deadline_at")
            if deadline_at is not None and cls._parse_datetime(deadline_at) is None:
                raise ValueError("Belzakupki tender deadline_at must be ISO datetime or null")
            # The source may report non-actionable rows without a durable tender
            # identity. They cannot create or update an inbox order, but must not
            # poison the whole bounded scan. Eligible rows are never accepted
            # without that identity.
            if item["eligible"]:
                cls._external_identity(item)
        has_more = payload.get("has_more")
        next_cursor = payload.get("next_cursor")
        if not isinstance(has_more, bool):
            raise ValueError("Belzakupki opportunities has_more must be boolean")
        if has_more and (not isinstance(next_cursor, str) or not next_cursor):
            raise ValueError("Belzakupki opportunities next_cursor is required while has_more")
        if not has_more and next_cursor is not None:
            raise ValueError("Belzakupki terminal page must have null next_cursor")
        return items, next_cursor if has_more else None

    @classmethod
    async def import_page(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        page: dict[str, Any],
        cursor_before: str | None,
        now: datetime | None = None,
    ) -> BelzakupkiImportResult:
        items, next_cursor = cls._validate_page(page)
        result = BelzakupkiImportResult(cursor_before=cursor_before, cursor_after=next_cursor)
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("Belzakupki import clock must be timezone-aware")

        async with session.begin():
            checkpoint = await cls._locked_checkpoint(session, tenant_scope=tenant_scope)
            if checkpoint.cursor != cursor_before:
                result.stale = True
                result.cursor_after = checkpoint.cursor
                return result

            for item in items:
                result.processed += 1
                try:
                    cls._external_identity(item)
                except ValueError:
                    result.skipped += 1
                    continue
                accepted = cls._is_accepted(item, now=current_time)
                if accepted:
                    result.accepted += 1
                await cls._upsert_opportunity(
                    session,
                    tenant_scope=tenant_scope,
                    item=item,
                    result=result,
                    allow_create=accepted,
                )

            checkpoint.cursor = next_cursor
            checkpoint.updated_at = datetime.now(timezone.utc)
            session.add(checkpoint)
        return result

    @classmethod
    async def _cursor_for_scope(cls, *, tenant_scope: TenantScope) -> str | None:
        async with async_session_maker() as session:
            checkpoint = (
                await session.execute(
                    select(BelzakupkiImportCheckpoint.cursor).where(
                        BelzakupkiImportCheckpoint.tenant_id == tenant_scope.tenant_id,
                        BelzakupkiImportCheckpoint.storefront_id == tenant_scope.storefront_id,
                    )
                )
            ).scalar_one_or_none()
            return checkpoint

    @classmethod
    async def _fetch_page(cls, *, cursor: str | None) -> dict[str, Any]:
        base_url = str(settings.BELZAKUPKI_API_BASE_URL or "").strip().rstrip("/")
        params: dict[str, Any] = {"limit": settings.BELZAKUPKI_IMPORT_PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        async with httpx.AsyncClient(timeout=settings.BELZAKUPKI_IMPORT_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{base_url}/api/v1/opportunities",
                params=params,
                headers={"Authorization": f"Bearer {settings.BELZAKUPKI_INTEGRATION_KEY}"},
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Belzakupki opportunities response must be an object")
        return payload

    @classmethod
    async def run_scheduled_import(cls) -> BelzakupkiImportResult:
        if not cls.is_configured():
            raise RuntimeError("Belzakupki import is not fully configured")
        async with async_session_maker() as session:
            tenant_scope = await SystemTenantScopeResolver.resolve(
                session,
                tenant_slug=settings.BELZAKUPKI_IMPORT_TENANT_SLUG.strip(),
                storefront_slug=settings.BELZAKUPKI_IMPORT_STOREFRONT_SLUG.strip(),
            )
        cursor = await cls._cursor_for_scope(tenant_scope=tenant_scope)
        page = await cls._fetch_page(cursor=cursor)
        async with async_session_maker() as session:
            return await cls.import_page(
                session,
                tenant_scope=tenant_scope,
                page=page,
                cursor_before=cursor,
            )
