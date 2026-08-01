from __future__ import annotations

import logging
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from models import LeadSource, Order, OrderStatus
from services.general_media_storage_service import (
    GeneralMediaStorage,
    get_general_media_storage,
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
    PHOTO_FIELDS,
    SYMPTOM_LABELS,
    RepairDiagnosticIncomingFile,
    RepairDiagnosticLeadPayload,
    RepairDiagnosticLeadResponse,
    RepairDiagnosticService,
)
from services.repair_diagnostic_storage_service import (
    RepairDiagnosticStorageService,
)
from services.tenant_scope_service import TenantScope


logger = logging.getLogger(__name__)


class RepairDiagnosticIntakeService:
    @staticmethod
    async def create_lead(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        payload: RepairDiagnosticLeadPayload,
        uploads: Dict[str, List[RepairDiagnosticIncomingFile]],
        idempotency_key: str,
    ) -> tuple[
        RepairDiagnosticLeadResponse,
        list[RepairDiagnosticIncomingFile],
        bool,
    ]:
        storage = get_general_media_storage()
        created_paths: set[str] = set()
        created_order: Order | None = None
        key_hash = PublicWriteIdempotencyService.key_hash(idempotency_key)
        storage_namespace = RepairDiagnosticStorageService.new_attempt_namespace(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            key_hash=key_hash,
        )

        async def create() -> PublicWriteCommandResponse[RepairDiagnosticLeadResponse]:
            nonlocal created_order
            created_order = await RepairDiagnosticIntakeService._create_mutation(
                session,
                payload=payload,
                uploads=uploads,
                tenant_scope=tenant_scope,
                storage=storage,
                created_paths=created_paths,
                storage_namespace=storage_namespace,
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

        try:
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
        except Exception:
            await RepairDiagnosticIntakeService._cleanup_failed_uploads(
                storage=storage,
                paths=created_paths,
            )
            raise

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
            for field in sorted(PHOTO_FIELDS)
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
        storage: GeneralMediaStorage,
        created_paths: set[str],
        storage_namespace: str,
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

        photos = await RepairDiagnosticService._store_uploads(
            uploads=uploads,
            storage=storage,
            created_paths=created_paths,
            storage_namespace=storage_namespace,
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
    async def _cleanup_failed_uploads(
        *,
        storage: GeneralMediaStorage,
        paths: set[str],
    ) -> None:
        for path in sorted(paths):
            try:
                await storage.delete_media(path)
            except Exception:
                logger.exception("REPAIR_DIAGNOSTIC_STORAGE_COMPENSATION_FAILED")
