#!/usr/bin/env python3
"""Backfill private service attachments and equipment links from legacy data.

The default mode is a read-only dry run. Use ``--execute`` only after reviewing
the report. Legacy JSON fields are deliberately left untouched so the migration
can be audited and repeated safely.
"""

from __future__ import annotations

import argparse
import asyncio
import mimetypes
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import settings  # noqa: E402
from core.database import async_session_maker  # noqa: E402
from models import (  # noqa: E402
    CustomerEquipment,
    EquipmentOrderLink,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
    Order,
    OrderAttachmentLink,
    OrderWorkStage,
    ServiceAttachment,
)
from services.service_attachment_service import ServiceAttachmentService  # noqa: E402


PHOTO_RE = re.compile(r"^-\s*Фото:\s*(?P<file_id>\S+)\s*$", re.MULTILINE)
DOCUMENT_RE = re.compile(
    r"^-\s*Документ:\s*(?P<filename>.+?)\s*\((?P<file_id>[^()\s]+)\)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class LegacyAttachmentCandidate:
    order_id: int
    file_id: str | None
    filename: str
    mime_type: str
    category: str
    source: str
    captured_at: datetime | None = None
    url: str | None = None
    transcript: str | None = None
    work_stage_id: int | None = None
    equipment_id: int | None = None
    component_id: int | None = None
    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None
    telegram_user_id: int | None = None

    @property
    def identity(self) -> tuple[int, str, str]:
        return (self.order_id, self.file_id or self.url or self.filename, self.category)


@dataclass
class MigrationStats:
    orders_scanned: int = 0
    attachments_found: int = 0
    attachments_existing: int = 0
    attachments_migrated: int = 0
    attachments_unavailable: int = 0
    attachment_duplicates: int = 0
    equipment_links_found: int = 0
    equipment_links_created: int = 0
    legacy_coverages_found: int = 0
    legacy_coverages_created: int = 0


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized or None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _role_from_event(value: Any) -> str:
    normalized = str(getattr(value, "value", value) or "").strip().lower()
    if normalized == "maintenance":
        return "maintenance"
    if normalized == "repair":
        return "repair"
    if normalized == "diagnostic":
        return "diagnostic"
    return "other"


def _candidate_from_entry(
    order_id: int,
    entry: dict[str, Any],
    *,
    default_category: str = "other",
    default_source: str = "telegram_bot",
) -> LegacyAttachmentCandidate | None:
    file_id = _text(entry.get("file_id"))
    url = _text(entry.get("url"))
    if not file_id and not url:
        return None
    filename = _text(entry.get("filename")) or "telegram-file"
    mime_type = _text(entry.get("mime_type")) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    purpose = _text(entry.get("purpose")) or default_category
    category = "nameplate" if "nameplate" in purpose else default_category
    if purpose in ServiceAttachmentService.CATEGORIES:
        category = purpose
    return LegacyAttachmentCandidate(
        order_id=order_id,
        file_id=file_id,
        filename=filename,
        mime_type=mime_type,
        category=category,
        source=_text(entry.get("source")) or default_source,
        captured_at=_datetime(entry.get("attached_at")),
        url=url,
        transcript=_text(entry.get("raw_text")),
        equipment_id=_int(entry.get("equipment_id")),
        component_id=_int(entry.get("component_id")),
        telegram_chat_id=_int(entry.get("telegram_chat_id")),
        telegram_message_id=_int(entry.get("telegram_message_id")),
        telegram_user_id=_int(entry.get("telegram_user_id")),
    )


def extract_order_candidates(order: Order) -> list[LegacyAttachmentCandidate]:
    meta = _as_dict(order.technical_meta)
    candidates: list[LegacyAttachmentCandidate] = []
    for raw in _as_list(meta.get("telegram_attachments")):
        if isinstance(raw, dict):
            candidate = _candidate_from_entry(int(order.id or 0), raw)
            if candidate:
                candidates.append(candidate)

    repair = _as_dict(meta.get("repair"))
    for raw in _as_list(repair.get("nameplate_recognitions")):
        if isinstance(raw, dict):
            candidate = _candidate_from_entry(int(order.id or 0), raw, default_category="nameplate")
            if candidate:
                candidates.append(candidate)

    for raw in _as_list(meta.get("warranty_nameplate_recognitions")):
        if isinstance(raw, dict):
            candidate = _candidate_from_entry(int(order.id or 0), raw, default_category="nameplate")
            if candidate:
                candidates.append(candidate)

    unique: dict[tuple[int, str, str], LegacyAttachmentCandidate] = {}
    for candidate in candidates:
        current = unique.get(candidate.identity)
        if current is None or (candidate.equipment_id and not current.equipment_id):
            unique[candidate.identity] = candidate
    return list(unique.values())


def extract_stage_candidates(stage: OrderWorkStage) -> list[LegacyAttachmentCandidate]:
    report = str(stage.installer_report or "")
    result: list[LegacyAttachmentCandidate] = []
    for match in PHOTO_RE.finditer(report):
        result.append(
            LegacyAttachmentCandidate(
                order_id=int(stage.order_id),
                file_id=match.group("file_id"),
                filename=f"stage-{stage.id}-photo.jpg",
                mime_type="image/jpeg",
                category="installation_result",
                source="telegram_bot_stage_report",
                work_stage_id=int(stage.id or 0),
            )
        )
    for match in DOCUMENT_RE.finditer(report):
        filename = _text(match.group("filename")) or f"stage-{stage.id}-document"
        result.append(
            LegacyAttachmentCandidate(
                order_id=int(stage.order_id),
                file_id=match.group("file_id"),
                filename=filename,
                mime_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
                category="document",
                source="telegram_bot_stage_report",
                work_stage_id=int(stage.id or 0),
            )
        )
    return result


async def _telegram_file_url(client: httpx.AsyncClient, file_id: str) -> str | None:
    token = str(settings.BOT_TOKEN or "").strip()
    if not token or token == "0:disabled-bot-token":
        return None
    response = await client.get(
        f"https://api.telegram.org/bot{token}/getFile",
        params={"file_id": file_id},
    )
    response.raise_for_status()
    payload = response.json()
    path = _text(_as_dict(payload.get("result")).get("file_path"))
    return f"https://api.telegram.org/file/bot{token}/{path}" if path else None


async def download_candidate(client: httpx.AsyncClient, candidate: LegacyAttachmentCandidate) -> bytes | None:
    url = candidate.url
    if not url and candidate.file_id:
        try:
            url = await _telegram_file_url(client, candidate.file_id)
        except (httpx.HTTPError, ValueError):
            return None
    if not url:
        return None
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.content or None
    except httpx.HTTPError:
        return None


async def _is_existing_attachment(
    session: AsyncSession,
    candidate: LegacyAttachmentCandidate,
) -> bool:
    if not candidate.file_id:
        return False
    result = await session.execute(
        select(ServiceAttachment.id)
        .join(OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id)
        .where(
            OrderAttachmentLink.order_id == candidate.order_id,
            OrderAttachmentLink.archived_at.is_(None),
            ServiceAttachment.telegram_file_id == candidate.file_id,
        )
        .limit(1)
    )
    return result.first() is not None


async def migrate_attachments(
    session: AsyncSession,
    *,
    execute: bool,
    order_id: int | None,
    stats: MigrationStats,
) -> None:
    order_stmt = select(Order).order_by(Order.id.asc())
    stage_stmt = select(OrderWorkStage).where(OrderWorkStage.installer_report.is_not(None)).order_by(OrderWorkStage.id.asc())
    if order_id is not None:
        order_stmt = order_stmt.where(Order.id == order_id)
        stage_stmt = stage_stmt.where(OrderWorkStage.order_id == order_id)

    orders = list((await session.execute(order_stmt)).scalars().all())
    stages = list((await session.execute(stage_stmt)).scalars().all())
    candidates: list[LegacyAttachmentCandidate] = []
    for order in orders:
        stats.orders_scanned += 1
        candidates.extend(extract_order_candidates(order))
    for stage in stages:
        candidates.extend(extract_stage_candidates(stage))

    unique: dict[tuple[int, str, str], LegacyAttachmentCandidate] = {}
    for candidate in candidates:
        if candidate.identity in unique:
            stats.attachment_duplicates += 1
        else:
            unique[candidate.identity] = candidate
    stats.attachments_found = len(unique)

    async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
        for candidate in unique.values():
            if await _is_existing_attachment(session, candidate):
                stats.attachments_existing += 1
                continue
            if not execute:
                continue
            content = await download_candidate(client, candidate)
            if not content:
                stats.attachments_unavailable += 1
                continue
            try:
                await ServiceAttachmentService.create_and_link_order_attachment(
                    session,
                    order_id=candidate.order_id,
                    content=content,
                    filename=candidate.filename,
                    mime_type=candidate.mime_type,
                    category=candidate.category,
                    source=candidate.source,
                    work_stage_id=candidate.work_stage_id,
                    equipment_id=candidate.equipment_id,
                    component_id=candidate.component_id,
                    transcript=candidate.transcript,
                    captured_at=candidate.captured_at,
                    telegram_meta={
                        "file_id": candidate.file_id,
                        "chat_id": candidate.telegram_chat_id,
                        "message_id": candidate.telegram_message_id,
                        "user_id": candidate.telegram_user_id,
                        "source_meta": {"migration": "legacy_service_attachment"},
                    },
                )
            except ValueError:
                stats.attachments_unavailable += 1
                continue
            stats.attachments_migrated += 1


async def migrate_equipment_links(
    session: AsyncSession,
    *,
    execute: bool,
    order_id: int | None,
    stats: MigrationStats,
) -> None:
    pairs: set[tuple[int, int, str]] = set()
    source_stmt = select(CustomerEquipment).where(CustomerEquipment.source_order_id.is_not(None))
    history_stmt = select(EquipmentServiceHistory).where(EquipmentServiceHistory.order_id.is_not(None))
    if order_id is not None:
        source_stmt = source_stmt.where(CustomerEquipment.source_order_id == order_id)
        history_stmt = history_stmt.where(EquipmentServiceHistory.order_id == order_id)
    for equipment in (await session.execute(source_stmt)).scalars().all():
        pairs.add((int(equipment.id or 0), int(equipment.source_order_id or 0), "sale"))
    for event in (await session.execute(history_stmt)).scalars().all():
        role = _role_from_event(event.event_type)
        pairs.add((int(event.equipment_id), int(event.order_id or 0), role))

    for equipment_id, linked_order_id, role in sorted(pairs):
        existing = await session.scalar(
            select(EquipmentOrderLink.id).where(
                EquipmentOrderLink.equipment_id == equipment_id,
                EquipmentOrderLink.order_id == linked_order_id,
                EquipmentOrderLink.role == role,
            )
        )
        if existing:
            continue
        stats.equipment_links_found += 1
        if execute:
            session.add(EquipmentOrderLink(equipment_id=equipment_id, order_id=linked_order_id, role=role))
            stats.equipment_links_created += 1


async def migrate_legacy_coverages(
    session: AsyncSession,
    *,
    execute: bool,
    order_id: int | None,
    stats: MigrationStats,
) -> None:
    stmt = select(CustomerEquipment).where(
        (CustomerEquipment.warranty_started_at.is_not(None))
        | (CustomerEquipment.warranty_expires_at.is_not(None))
    )
    if order_id is not None:
        stmt = stmt.where(CustomerEquipment.source_order_id == order_id)
    for equipment in (await session.execute(stmt)).scalars().all():
        existing = await session.scalar(
            select(EquipmentWarrantyCoverage.id).where(
                EquipmentWarrantyCoverage.equipment_id == int(equipment.id or 0),
                EquipmentWarrantyCoverage.coverage_type == "legacy",
                EquipmentWarrantyCoverage.component_id.is_(None),
            )
        )
        if existing:
            continue
        stats.legacy_coverages_found += 1
        if not execute:
            continue
        session.add(
            EquipmentWarrantyCoverage(
                equipment_id=int(equipment.id or 0),
                coverage_type="legacy",
                source="legacy",
                starts_at=equipment.warranty_started_at,
                expires_at=equipment.warranty_expires_at,
                terms_snapshot=equipment.warranty_terms,
                policy_snapshot={"migration": "customer_equipment_legacy_fields"},
            )
        )
        stats.legacy_coverages_created += 1


async def run(*, execute: bool, order_id: int | None) -> MigrationStats:
    stats = MigrationStats()
    async with async_session_maker() as session:
        await migrate_attachments(session, execute=execute, order_id=order_id, stats=stats)
        await migrate_equipment_links(session, execute=execute, order_id=order_id, stats=stats)
        await migrate_legacy_coverages(session, execute=execute, order_id=order_id, stats=stats)
        if execute:
            await session.commit()
        else:
            await session.rollback()
    return stats


def print_report(stats: MigrationStats, *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY RUN"
    print(f"Service attachment migration: {mode}")
    for key, value in stats.__dict__.items():
        print(f"  {key}: {value}")
    if not execute:
        planned = stats.attachments_found - stats.attachments_existing
        print(f"  attachments_planned: {max(0, planned)}")
        print("No data changed. Re-run with --execute after reviewing this report.")
    else:
        print("Legacy JSON and legacy warranty fields were preserved for audit.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Persist the migration. Default is dry-run.")
    parser.add_argument("--order-id", type=int, help="Limit the migration to one order.")
    args = parser.parse_args()
    stats = asyncio.run(run(execute=bool(args.execute), order_id=args.order_id))
    print_report(stats, execute=bool(args.execute))


if __name__ == "__main__":
    main()
