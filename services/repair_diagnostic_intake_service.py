from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from models import LeadSource, Order, OrderStatus
from services.private_attachment_storage_service import (
    PrivateAttachmentStorage,
    VariantScopedPrivateAttachmentStorage,
    get_private_attachment_storage,
)
from services.order_service import OrderService
from services.public_write_fingerprint_service import (
    PublicWriteAttachmentFingerprint,
    PublicWriteFingerprintService,
)
from services.public_write_idempotency_service import (
    PublicWriteCommandResponse,
    PublicWriteIdempotencyService,
)
from services.repair_diagnostic_ai_job_service import (
    RepairDiagnosticAiJobService,
)
from services.repair_diagnostic_service import (
    PHOTO_FIELD_ORDER,
    PHOTO_LABELS,
    SYMPTOM_LABELS,
    RepairDiagnosticIncomingFile,
    RepairDiagnosticLeadPayload,
    RepairDiagnosticLeadResponse,
    RepairDiagnosticService,
)
from services.service_attachment_service import ServiceAttachmentService
from services.tenant_scope_service import TenantScope


_PRIVATE_ATTACHMENT_CATEGORIES = {
    "nameplate": "nameplate",
    "indoor_unit": "defect",
    "outdoor_unit": "defect",
    "error_display": "defect",
    "leak_place": "defect",
}


class RepairDiagnosticIntakeService:
    @staticmethod
    async def create_lead(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        payload: RepairDiagnosticLeadPayload,
        uploads: Dict[str, List[RepairDiagnosticIncomingFile]],
        idempotency_key: str,
        storage: PrivateAttachmentStorage | None = None,
    ) -> tuple[
        RepairDiagnosticLeadResponse,
        list[RepairDiagnosticIncomingFile],
        bool,
    ]:
        created_order: Order | None = None
        key_hash = PublicWriteIdempotencyService.key_hash(idempotency_key)
        selected_storage = storage or get_private_attachment_storage()
        attempt_storage = VariantScopedPrivateAttachmentStorage(
            selected_storage,
            variant_scope=(
                f"public-repair-{tenant_scope.tenant_id}-"
                f"{tenant_scope.storefront_id}-{key_hash}-{secrets.token_hex(8)}"
            ),
        )

        async def create() -> PublicWriteCommandResponse[RepairDiagnosticLeadResponse]:
            nonlocal created_order
            created_order = await RepairDiagnosticIntakeService._create_mutation(
                session,
                payload=payload,
                uploads=uploads,
                tenant_scope=tenant_scope,
                storage=attempt_storage,
                key_hash=key_hash,
            )
            repair_meta = OrderService._get_repair_meta(created_order)
            response = RepairDiagnosticLeadResponse(
                order_id=int(created_order.id or 0),
                status=str(
                    created_order.status.value
                    if hasattr(created_order.status, "value")
                    else created_order.status
                ),
                created_at=created_order.created_at,
                ai_pre_diagnosis_status=repair_meta["ai_pre_diagnosis_status"],
            )
            return PublicWriteCommandResponse(
                value=response,
                resource_type="order",
                resource_id=response.order_id,
            )

        outcome = await PublicWriteIdempotencyService.execute(
            session,
            tenant_scope=tenant_scope,
            command_name="public_repair_diagnostic_lead_v1",
            idempotency_key=idempotency_key,
            request_fingerprint=RepairDiagnosticIntakeService.request_fingerprint(
                payload=payload,
                uploads=uploads,
            ),
            response_model=RepairDiagnosticLeadResponse,
            operation=create,
        )

        if not outcome.replayed and created_order is not None:
            photos = OrderService._get_repair_meta(created_order).get("photos", {})
            await RepairDiagnosticService._notify_admins(
                session,
                created_order,
                payload,
                photos,
                tenant_scope=tenant_scope,
            )
        nameplate_files = (uploads.get("nameplate") or [])[:1]
        return outcome.value, nameplate_files, outcome.replayed

    @staticmethod
    def request_fingerprint(
        *,
        payload: RepairDiagnosticLeadPayload,
        uploads: Dict[str, List[RepairDiagnosticIncomingFile]],
    ) -> str:
        attachments = [
            PublicWriteAttachmentFingerprint(
                field=field,
                position=position,
                content_hash=item.content_hash,
                content_type=item.content_type or "",
                size_bytes=len(item.content),
            )
            for field in PHOTO_FIELD_ORDER
            for position, item in enumerate(uploads.get(field) or [])
        ]
        return PublicWriteFingerprintService.for_multipart(
            payload=payload,
            attachments=attachments,
        )

    @staticmethod
    async def _create_mutation(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        payload: RepairDiagnosticLeadPayload,
        uploads: Dict[str, List[RepairDiagnosticIncomingFile]],
        storage: PrivateAttachmentStorage,
        key_hash: str,
    ) -> Order:
        order = await OrderService.create_from_website(
            session=session,
            customer_name=payload.contact.name,
            customer_phone=payload.contact.phone,
            customer_email=None,
            customer_address=payload.contact.address,
            items=[],
            lead_source=LeadSource.SITE,
            initial_status=OrderStatus.NEW_LEAD,
            comment=RepairDiagnosticService._build_order_comment(payload, uploads),
            tenant_scope=tenant_scope,
            commit=False,
        )
        order.workflow_type = "repair"
        order.title = f"Ремонт кондиционера: {SYMPTOM_LABELS[payload.symptom]}"
        order.delivery_address = payload.contact.address

        photos = await RepairDiagnosticIntakeService._store_private_uploads(
            session,
            order_id=int(order.id or 0),
            tenant_scope=tenant_scope,
            uploads=uploads,
            storage=storage,
            key_hash=key_hash,
        )
        repair_meta = RepairDiagnosticService._build_repair_meta(payload, photos)
        meta = dict(order.technical_meta or {})
        meta["service_type"] = "repair"
        order.technical_meta = meta
        OrderService._set_repair_meta(
            order,
            repair_meta,
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )
        await OrderService._maybe_add_default_repair_diagnostic(session, order)
        session.add(order)
        await session.flush()
        await RepairDiagnosticAiJobService.enqueue(
            session,
            order_id=int(order.id or 0),
            tenant_scope=tenant_scope,
            key_hash=key_hash,
        )
        return order

    @staticmethod
    async def _store_private_uploads(
        session: AsyncSession,
        *,
        order_id: int,
        tenant_scope: TenantScope,
        uploads: Dict[str, List[RepairDiagnosticIncomingFile]],
        storage: PrivateAttachmentStorage,
        key_hash: str,
    ) -> Dict[str, List[dict]]:
        stored: Dict[str, List[dict]] = {
            field: [] for field in PHOTO_FIELD_ORDER
        }
        uploaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for field in PHOTO_FIELD_ORDER:
            for position, file in enumerate(uploads.get(field) or []):
                item = await ServiceAttachmentService.create_and_link_order_attachment(
                    session,
                    order_id=order_id,
                    content=file.content,
                    filename=file.filename,
                    mime_type=file.content_type,
                    category=_PRIVATE_ATTACHMENT_CATEGORIES[field],
                    caption=PHOTO_LABELS[field],
                    source="website_repair_diagnostic",
                    created_by="public_website",
                    source_meta={
                        "intake": "repair_diagnostic",
                        "photo_category": field,
                        "purpose": f"repair_diagnostic_{field}",
                        "position": position,
                        "request_key_hash": key_hash,
                        "received_at": uploaded_at,
                    },
                    storage=storage,
                    commit=False,
                    tenant_scope=tenant_scope,
                )
                stored[field].append(
                    {
                        "attachment_id": int(item["id"]),
                        "filename": str(item["filename"]),
                        "content_type": str(item["mime_type"]),
                        "content_hash": file.content_hash,
                        "size_bytes": int(item["size_bytes"]),
                        "uploaded_at": uploaded_at,
                    }
                )
        return stored
