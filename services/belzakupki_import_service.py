"""Bounded, tenant-scoped import of Belzakupki opportunity matches."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import String, cast, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from core.config import settings
from core.database import async_session_maker
from models import BelzakupkiImportCheckpoint, LeadSource, Order, OrderStatus
from models.tenancy import TenantScope
from services.tenant_scope_service import SystemTenantScopeResolver

from services.belzakupki_canonical_identity import (
    canonical_procurement_url, canonical_tender_url, original_native_identities,
)

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
    order_id: int | None = None


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
    def _snapshot_datetime(cls, value: Any) -> str | None:
        parsed = cls._parse_datetime(value)
        return parsed.isoformat() if parsed is not None else cls._clean_text(value, maximum=80)

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
        # Only a submission deadline establishes that a tender is no longer
        # actionable. Delivery/contract dates and unknown kinds do not.
        if (tender.get("deadline_kind") or "submission") != "submission":
            return True
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
            "updated_at": cls._snapshot_datetime(item.get("updated_at")),
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
                "canonical_url": canonical_tender_url(tender),
                "deadline_at": cls._snapshot_datetime(tender.get("deadline_at")),
                "deadline_kind": cls._clean_text(tender.get("deadline_kind"), maximum=40) or "submission",
                "published_at": cls._snapshot_datetime(tender.get("published_at")),
                "estimated_value": tender.get("estimated_value"),
                "currency": cls._clean_text(tender.get("currency"), maximum=12),
                "location": cls._clean_text(tender.get("location"), maximum=1000),
                "quantity": tender.get("quantity"),
                "summary": cls._clean_text(tender.get("summary"), maximum=4000),
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
            "tender": snapshot["tender"],
        }
        incoming_time = cls._parse_datetime(snapshot.get("updated_at"))
        tender_time = cls._parse_datetime(existing.get("tender_updated_at"))
        if tender_time is None:
            prior_times = [cls._parse_datetime(match.get("updated_at"))
                           for match in existing_matches.values() if isinstance(match, dict)]
            tender_time = max((time for time in prior_times if time is not None), default=None)
        replace_tender = tender_time is None or (incoming_time is not None and incoming_time >= tender_time)
        selected_tender = snapshot["tender"] if replace_tender else existing.get("tender", snapshot["tender"])
        next_metadata = {
            "source": selected_tender["source"],
            "external_tender_id": selected_tender["external_id"],
            "tender": selected_tender,
            "tender_updated_at": snapshot.get("updated_at") if replace_tender else tender_time.isoformat(),
            "matches": matches,
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        }
        if isinstance(existing.get("enrichment"), dict):
            next_metadata["enrichment"] = existing["enrichment"]
        if isinstance(existing.get("equipment_prefill_history"), dict):
            next_metadata["equipment_prefill_history"] = existing["equipment_prefill_history"]
        if isinstance(existing.get("equipment_prefill_commands"), dict):
            next_metadata["equipment_prefill_commands"] = existing["equipment_prefill_commands"]
        references = dict(existing.get("source_references") or {})
        native = snapshot["tender"]
        native_key = cls._order_fingerprint(source=native["source"], external_id=native["external_id"])
        references[native_key] = {key: native.get(key) for key in ("source", "external_id", "url", "canonical_url", "claimed_canonical_url")}
        prior_native = existing.get("tender")
        if isinstance(prior_native, dict) and prior_native.get("source") and prior_native.get("external_id"):
            prior_key = cls._order_fingerprint(source=prior_native["source"], external_id=prior_native["external_id"])
            references.setdefault(prior_key, {key: prior_native.get(key) for key in ("source", "external_id", "url", "canonical_url", "claimed_canonical_url")})
        next_metadata["source_references"] = references
        canonical = canonical_tender_url(native) or existing.get("canonical_url")
        if canonical:
            next_metadata["canonical_url"] = canonical
        for conflict_key in ("identity_conflicts", "canonical_conflicts"):
            if existing.get(conflict_key):
                next_metadata[conflict_key] = existing[conflict_key]
        return next_metadata

    @classmethod
    def _canonical_fingerprint(cls, url: str) -> str:
        return hashlib.sha256(f"{cls.SOURCE_NAMESPACE}|canonical-url|{url}".encode()).hexdigest()

    @classmethod
    async def _identity_order(cls, session: AsyncSession, *, tenant_scope: TenantScope,
                              tender: dict[str, Any]) -> tuple[Order | None, str, list[int]]:
        tender = {**tender, "source": cls._clean_text(tender["source"], maximum=100),
                  "external_id": cls._clean_text(tender["external_id"], maximum=300)}
        native = cls._order_fingerprint(source=tender["source"], external_id=tender["external_id"])
        canonical = canonical_tender_url(tender)
        native_url = canonical_tender_url({**tender, "canonical_url": None})
        is_mirror = canonical is not None and native_url != canonical
        fingerprint = cls._canonical_fingerprint(canonical) if canonical else native
        original_keys = {cls._order_fingerprint(source=source, external_id=identity)
                         for source, identity in original_native_identities(canonical)} if canonical else set()
        metadata_text = cast(Order.technical_meta, String)
        predicates = [Order.source_fingerprint.in_({native, fingerprint} | original_keys),
                      metadata_text.contains(native)]
        if canonical:
            predicates.append(metadata_text.contains(canonical))
        scope = (Order.tenant_id == tenant_scope.tenant_id, Order.storefront_id == tenant_scope.storefront_id,
                 Order.lead_source == LeadSource.BELZAKUPKI)
        async def query(condition):
            return (await session.execute(select(Order).options(lazyload("*")).where(*scope, condition)
                    .order_by(Order.id).with_for_update())).scalars().all()

        def matching(rows):
            candidates = []
            for order in rows:
                meta = (order.technical_meta or {}).get(cls.META_KEY) or {}
                refs = meta.get("source_references") or {}
                stored = meta.get("tender") or {}
                reference = refs.get(native)
                native_alias = (isinstance(reference, dict) and reference.get("source")
                                and reference.get("external_id")
                                and cls._order_fingerprint(source=reference["source"],
                                    external_id=reference["external_id"]) == native)
                same_canonical = canonical and (canonical_procurement_url(meta.get("canonical_url")) == canonical
                                               or canonical_tender_url(stored) == canonical)
                native_match = order.source_fingerprint == native
                # A legacy original's numeric ID may collide across procedure
                # routes. Its actual URL must agree before canonical adoption.
                stored_canonical = canonical_tender_url(stored)
                if canonical and stored_canonical and stored_canonical != canonical and not is_mirror:
                    native_match = False
                    # Same native numeric ID does not collapse separate routes
                    # on the original platform. Cross-platform aliases still
                    # allow replays omitting their previously verified original.
                    if urlsplit(stored_canonical).hostname == urlsplit(canonical).hostname:
                        native_alias = False
                if order.source_fingerprint == fingerprint or native_match or native_alias or same_canonical:
                    candidates.append(order)
            return candidates

        def owns_native(order):
            meta = (order.technical_meta or {}).get(cls.META_KEY) or {}
            reference = (meta.get("source_references") or {}).get(native)
            return order.source_fingerprint == native or (
                isinstance(reference, dict) and reference.get("source") and reference.get("external_id")
                and cls._order_fingerprint(source=reference["source"], external_id=reference["external_id"]) == native)

        candidates = matching(await query(predicates[0]))
        if not candidates:
            candidates = matching(await query(or_(*predicates[1:])))
        elif is_mirror and not any(owns_native(row) for row in candidates):
            # A new claimed original must not steal an already linked mirror
            # simply because that other original already has its own order.
            alias_candidates = matching(await query(metadata_text.contains(native)))
            candidates = sorted({row.id: row for row in candidates + alias_candidates}.values(), key=lambda row: row.id)
        if not candidates:
            return None, fingerprint, []
        linked_mirror = None
        if is_mirror:
            for row in candidates:
                metadata = (row.technical_meta or {}).get(cls.META_KEY) or {}
                established = canonical_procurement_url(metadata.get("canonical_url"))
                if established and established != canonical and owns_native(row):
                    linked_mirror = row
                    break
        chosen = linked_mirror or next((row for row in candidates if row.source_fingerprint == fingerprint), candidates[0])
        # An older producer/replay may omit a previously verified original. Keep
        # its adopted key when the native identity has already been linked.
        existing_meta = (chosen.technical_meta or {}).get(cls.META_KEY) or {}
        previous_canonical = canonical_procurement_url(existing_meta.get("canonical_url"))
        if previous_canonical and (not tender.get("canonical_url") or linked_mirror is not None):
            fingerprint = cls._canonical_fingerprint(previous_canonical)
        return chosen, fingerprint, [row.id for row in candidates if row.id != chosen.id]

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
        order, fingerprint, conflicts = await cls._identity_order(
            session, tenant_scope=tenant_scope, tender=item["tender"],
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
                from services.communications.incoming_events import IncomingEventService
                await IncomingEventService.enqueue_order(session, order)
                result.created += 1
                result.order_id = order.id
                return

        result.order_id = order.id
        prior_meta = (order.technical_meta or {}).get(cls.META_KEY) or {}
        claimed_canonical = canonical_tender_url(snapshot["tender"])
        canonical_conflict = bool(item["tender"].get("canonical_url") and claimed_canonical and prior_meta.get("canonical_url")
                                  and fingerprint != cls._canonical_fingerprint(claimed_canonical))
        if prior_meta.get("canonical_url") and (not item["tender"].get("canonical_url") or canonical_conflict):
            snapshot["tender"]["canonical_url"] = prior_meta["canonical_url"]
            if canonical_conflict:
                snapshot["tender"]["claimed_canonical_url"] = claimed_canonical
            snapshot_fingerprint = cls._snapshot_fingerprint(snapshot)
        if not item["tender"].get("canonical_url"):
            previous_match = (prior_meta.get("matches") or {}).get(str(snapshot["match_id"])) or {}
            previous_claim = (previous_match.get("tender") or {}).get("claimed_canonical_url")
            if previous_claim:
                snapshot["tender"]["claimed_canonical_url"] = previous_claim
                snapshot_fingerprint = cls._snapshot_fingerprint(snapshot)
        technical_meta = dict(order.technical_meta or {})
        provider_meta = technical_meta.get(cls.META_KEY)
        provider_meta = dict(provider_meta) if isinstance(provider_meta, dict) else {}
        new_canonical_conflict = canonical_conflict and claimed_canonical not in provider_meta.get("canonical_conflicts", [])
        if canonical_conflict:
            provider_meta["canonical_conflicts"] = sorted(set(provider_meta.get("canonical_conflicts", []))
                | {prior_meta["canonical_url"], claimed_canonical})
        identity_changed = bool(canonical_tender_url(snapshot["tender"])) and order.source_fingerprint != fingerprint
        # Without current canonical evidence, retain a previously adopted key.
        if canonical_tender_url(snapshot["tender"]):
            order.source_fingerprint = fingerprint
        if conflicts:
            provider_meta["identity_conflicts"] = sorted(set(provider_meta.get("identity_conflicts", [])) | set(conflicts))
        existing_matches = provider_meta.get("matches") if isinstance(provider_meta.get("matches"), dict) else {}
        current_match = existing_matches.get(str(snapshot["match_id"]))
        if not conflicts and not new_canonical_conflict and not identity_changed and isinstance(current_match, dict) and current_match.get("fingerprint") == snapshot_fingerprint:
            result.unchanged += 1
            return

        stale_match = False
        if isinstance(current_match, dict):
            incoming_time = cls._parse_datetime(snapshot.get("updated_at"))
            current_time = cls._parse_datetime(current_match.get("updated_at"))
            stale_match = current_time is not None and (incoming_time is None or incoming_time < current_time)
            if stale_match and not identity_changed and not conflicts and not new_canonical_conflict:
                result.unchanged += 1
                return

        # Deliberately mutate only source-owned technical metadata.  A manager's
        # title, comment, workflow and status remain untouched after first intake.
        technical_meta[cls.META_KEY] = cls._next_metadata(
            existing=provider_meta,
            snapshot=snapshot,
            snapshot_fingerprint=snapshot_fingerprint,
        )
        if stale_match:
            technical_meta[cls.META_KEY]["matches"] = existing_matches
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
        # Observe the committed page, including rejected rows with durable IDs.
        from services.jev_shadow_service import JevShadowService
        await JevShadowService.enqueue_tenders(tenant_scope=tenant_scope, items=items)
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
