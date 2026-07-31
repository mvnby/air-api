"""Idempotently copy verified legacy attachments into private storage."""

from __future__ import annotations

import hashlib

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Order, OrderAttachmentLink, OrderWorkStage, ServiceAttachment
from models.tenancy import TenantScope
from services.private_attachment_storage_service import PrivateAttachmentStorage
from services.service_attachment_service import ServiceAttachmentService
from services.tenant_scope_service import tenant_scope_clause

from .legacy_sources import (
    AttachmentDownloadError,
    LegacyAttachmentCandidate,
    MigrationStats,
    _as_dict,
    _merge_candidates,
    download_candidate,
    extract_order_candidates,
    extract_stage_candidates,
)


async def _is_existing_attachment(
    session: AsyncSession,
    candidate: LegacyAttachmentCandidate,
) -> bool:
    source_meta_result = await session.execute(
        select(ServiceAttachment.source_meta)
        .join(OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id)
        .where(
            OrderAttachmentLink.order_id == candidate.order_id,
            OrderAttachmentLink.archived_at.is_(None),
            ServiceAttachment.archived_at.is_(None),
        )
    )
    for source_meta in source_meta_result.scalars().all():
        if _as_dict(source_meta).get("legacy_source_key") == candidate.legacy_source_key:
            return True

    if not candidate.file_id and not (
        candidate.telegram_chat_id is not None and candidate.telegram_message_id is not None
    ):
        return False
    filters = [
        OrderAttachmentLink.order_id == candidate.order_id,
        OrderAttachmentLink.archived_at.is_(None),
        ServiceAttachment.archived_at.is_(None),
    ]
    if candidate.telegram_chat_id is not None and candidate.telegram_message_id is not None:
        filters.extend(
            [
                ServiceAttachment.telegram_chat_id == candidate.telegram_chat_id,
                ServiceAttachment.telegram_message_id == candidate.telegram_message_id,
            ]
        )
    elif candidate.work_stage_id is not None:
        filters.extend(
            [
                OrderAttachmentLink.work_stage_id == candidate.work_stage_id,
                ServiceAttachment.telegram_file_id == candidate.file_id,
            ]
        )
    else:
        filters.append(ServiceAttachment.telegram_file_id == candidate.file_id)
    result = await session.execute(
        select(ServiceAttachment.id)
        .join(OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id)
        .where(*filters)
        .limit(1)
    )
    return result.first() is not None


async def migrate_attachments(
    session: AsyncSession,
    *,
    execute: bool,
    order_id: int | None,
    stats: MigrationStats,
    storage: PrivateAttachmentStorage | None = None,
    tenant_scope: TenantScope,
) -> None:
    order_stmt = (
        select(Order)
        .where(tenant_scope_clause(Order, tenant_scope))
        .order_by(Order.id.asc())
    )
    stage_stmt = (
        select(OrderWorkStage)
        .join(Order, Order.id == OrderWorkStage.order_id)
        .where(OrderWorkStage.installer_report.is_not(None))
        .where(tenant_scope_clause(Order, tenant_scope))
        .order_by(OrderWorkStage.id.asc())
    )
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
        current = unique.get(candidate.identity)
        if current is not None:
            stats.attachment_duplicates += 1
            unique[candidate.identity] = _merge_candidates(current, candidate)
        else:
            unique[candidate.identity] = candidate
    stats.attachments_found = len(unique)

    async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
        for candidate in unique.values():
            if await _is_existing_attachment(session, candidate):
                stats.attachments_existing += 1
                continue
            try:
                content = await download_candidate(client, candidate)
                ServiceAttachmentService._normalize_mime_type(candidate.mime_type, candidate.filename)
            except (AttachmentDownloadError, ValueError) as exc:
                stats.attachments_unavailable += 1
                if isinstance(exc, AttachmentDownloadError):
                    stats.transient_failures += int(exc.transient)
                    stats.configuration_failures += int(exc.configuration)
                stats.issues.append(
                    f"order={candidate.order_id} attachment={candidate.filename}: {exc}"
                )
                continue
            stats.attachments_verified += 1
            if not execute:
                continue
            try:
                async with session.begin_nested():
                    created = await ServiceAttachmentService.create_and_link_order_attachment(
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
                            "source_meta": {
                                "migration": "legacy_service_attachment",
                                "legacy_source_key": candidate.legacy_source_key,
                                "legacy_provenance": list(candidate.provenance),
                            },
                        },
                        storage=storage,
                        commit=False,
                        tenant_scope=tenant_scope,
                    )
                    attachment = await session.get(ServiceAttachment, int(created["id"]))
                    if not attachment or not attachment.storage_key or storage is None:
                        raise RuntimeError("Migrated attachment has no private storage object")
                    stored_content = await storage.read(attachment.storage_key)
                    if (
                        len(stored_content) != len(content)
                        or hashlib.sha256(stored_content).hexdigest()
                        != hashlib.sha256(content).hexdigest()
                    ):
                        raise RuntimeError("Private storage read-back integrity check failed")
                    stats.attachments_storage_verified += 1
            except (ValueError, RuntimeError) as exc:
                stats.attachments_unavailable += 1
                stats.issues.append(
                    f"order={candidate.order_id} attachment={candidate.filename}: {exc}"
                )
                continue
            stats.attachments_migrated += 1
