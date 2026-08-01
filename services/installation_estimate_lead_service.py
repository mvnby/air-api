"""Atomic public intake for preliminary installation estimates from photos."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import secrets
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.public_upload_limits import PUBLIC_ATTACHMENT_PAYLOAD_MAX_BYTES
from models import Customer, LeadSource, Order, OrderStatus
from schemas_installation_estimate import (
    InstallationEstimateLeadPayload,
    InstallationEstimateLeadResponse,
)
from services.communications.contracts import (
    InstallationEstimateLeadCreatedPayloadV1,
)
from services.communications.outbox_service import IntegrationOutboxService
from services.communications.installation_activation_fence import (
    InstallationEventEnqueueFenceBusy,
)
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
)
from services.tenant_entity_access_service import TenantEntityAccessService
from services.order_service import OrderService
from services.tenant_scope_service import TenantScope, storefront_scope_clause
from services.private_attachment_storage_service import (
    PrivateAttachmentStorage,
    VariantScopedPrivateAttachmentStorage,
    get_private_attachment_storage,
)
from services.public_write_fingerprint_service import (
    PublicWriteAttachmentFingerprint,
    PublicWriteFingerprintService,
)
from services.public_write_idempotency_service import (
    PublicWriteCommandResponse,
    PublicWriteIdempotencyConflict,
    PublicWriteIdempotencyService,
)
from services.service_attachment_service import ServiceAttachmentService


logger = logging.getLogger(__name__)


InstallationEstimateIdempotencyConflict = PublicWriteIdempotencyConflict


class InstallationEstimateTemporarilyUnavailable(RuntimeError):
    pass


PHOTO_CATEGORIES = {
    "indoor_unit": ("installation_indoor", "Место внутреннего блока"),
    "outdoor_unit": ("installation_outdoor", "Место наружного блока"),
    "route": ("installation_route", "Трасса"),
    "facade": ("installation_facade", "Фасад"),
    "power_supply": ("installation_power", "Электропитание"),
}
ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
MAX_FILES_PER_CATEGORY = 5
MAX_FILES_TOTAL = 15
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PAYLOAD_BYTES = PUBLIC_ATTACHMENT_PAYLOAD_MAX_BYTES


@dataclass(frozen=True)
class InstallationEstimateIncomingFile:
    category: str
    filename: str
    content_type: str
    content: bytes
    content_hash: str


class InstallationEstimateLeadService:
    @staticmethod
    def source_fingerprint(idempotency_key: str) -> str:
        normalized = str(idempotency_key or "").strip()
        if not normalized:
            raise ValueError("Idempotency-Key is required")
        return hashlib.sha256(
            f"installation-estimate:v1:{normalized}".encode("utf-8")
        ).hexdigest()

    @staticmethod
    async def collect_uploads(
        raw_groups: dict[str, Any],
    ) -> list[InstallationEstimateIncomingFile]:
        collected: list[InstallationEstimateIncomingFile] = []
        total_bytes = 0
        for category in PHOTO_CATEGORIES:
            raw_files = raw_groups.get(category) or []
            files = [upload for upload in raw_files if upload is not None]
            if len(files) > MAX_FILES_PER_CATEGORY:
                label = PHOTO_CATEGORIES[category][1]
                raise ValueError(
                    f"{label}: можно загрузить не больше {MAX_FILES_PER_CATEGORY} файлов"
                )
            for upload in files:
                content = await upload.read(MAX_FILE_BYTES + 1)
                content_type = str(getattr(upload, "content_type", "") or "").split(
                    ";", 1
                )[0].strip().lower()
                filename = InstallationEstimateLeadService._clean_filename(
                    getattr(upload, "filename", None)
                )
                total_bytes += len(content)
                if total_bytes > MAX_PAYLOAD_BYTES:
                    raise ValueError(
                        f"Общий размер фотографий не должен превышать "
                        f"{MAX_PAYLOAD_BYTES // (1024 * 1024)} МБ"
                    )
                await InstallationEstimateLeadService._validate_image(
                    filename=filename,
                    content_type=content_type,
                    content=content,
                )
                collected.append(
                    InstallationEstimateIncomingFile(
                        category=category,
                        filename=filename,
                        content_type=content_type,
                        content=content,
                        content_hash=hashlib.sha256(content).hexdigest(),
                    )
                )
                if len(collected) > MAX_FILES_TOTAL:
                    raise ValueError(
                        f"В одной заявке можно загрузить не больше {MAX_FILES_TOTAL} фотографий"
                    )
        if not collected:
            raise ValueError("Добавьте хотя бы одну фотографию объекта")
        return collected

    @staticmethod
    def request_hash(
        *,
        payload: InstallationEstimateLeadPayload,
        uploads: list[InstallationEstimateIncomingFile],
    ) -> str:
        positions: dict[str, int] = {}
        attachments: list[PublicWriteAttachmentFingerprint] = []
        for upload in uploads:
            position = positions.get(upload.category, 0)
            positions[upload.category] = position + 1
            attachments.append(
                PublicWriteAttachmentFingerprint(
                    field=upload.category,
                    position=position,
                    content_hash=upload.content_hash,
                    content_type=upload.content_type,
                    size_bytes=len(upload.content),
                )
            )
        return PublicWriteFingerprintService.for_multipart(
            payload=payload,
            attachments=attachments,
        )

    @classmethod
    async def create_lead(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        payload: InstallationEstimateLeadPayload,
        uploads: list[InstallationEstimateIncomingFile],
        idempotency_key: str,
        storage: PrivateAttachmentStorage | None = None,
    ) -> InstallationEstimateLeadResponse:
        fingerprint = cls.source_fingerprint(idempotency_key)
        storage_variant_scope = (
            "public-installation-"
            f"{PublicWriteIdempotencyService.key_hash(idempotency_key)}-"
            f"{secrets.token_hex(8)}"
        )
        payload_hash = cls.request_hash(payload=payload, uploads=uploads)
        selected_storage = storage or get_private_attachment_storage()
        attempt_storage = VariantScopedPrivateAttachmentStorage(
            selected_storage,
            variant_scope=storage_variant_scope,
        )
        created_storage_keys: set[str] = set()
        received_at = datetime.now(timezone.utc)
        category_counts = {
            category: sum(1 for upload in uploads if upload.category == category)
            for category in PHOTO_CATEGORIES
            if any(upload.category == category for upload in uploads)
        }
        comment = cls._build_comment(payload=payload, category_counts=category_counts)

        async def create() -> PublicWriteCommandResponse[InstallationEstimateLeadResponse]:
            existing = await cls._find_existing(
                session,
                tenant_scope=tenant_scope,
                fingerprint=fingerprint,
            )
            if existing is not None:
                replay = cls._replay_response(existing, payload_hash=payload_hash)
                return PublicWriteCommandResponse(
                    value=replay,
                    resource_type="order",
                    resource_id=replay.order_id,
                )

            order = await OrderService.create_from_website(
                session=session,
                customer_name=payload.name,
                customer_phone=payload.phone,
                customer_email=payload.email,
                customer_address=payload.address,
                items=[],
                lead_source=LeadSource.SITE,
                initial_status=OrderStatus.NEW_LEAD,
                comment=comment,
                order_technical_meta={
                    "service_type": "pre_install",
                    "object_type": payload.object_type,
                    "marketing_source": "site",
                    "installation_estimate": {
                        "status": "pending_review",
                        "request_payload_hash": payload_hash,
                        "received_at": received_at.isoformat(),
                        "attachment_count": len(uploads),
                        "category_counts": category_counts,
                        "privacy_consent": True,
                        "privacy_consent_at": received_at.isoformat(),
                        "attachment_policy": "private_access_only",
                    },
                },
                commit=False,
                tenant_scope=tenant_scope,
            )
            order.title = "Предварительная оценка монтажа по фото"
            order.workflow_type = "sales_installation"
            order.source_fingerprint = fingerprint
            session.add(order)
            await session.flush()

            for upload in uploads:
                attachment_category, label = PHOTO_CATEGORIES[upload.category]
                await ServiceAttachmentService.create_and_link_order_attachment(
                    session,
                    order_id=int(order.id or 0),
                    content=upload.content,
                    filename=upload.filename,
                    mime_type=upload.content_type,
                    category=attachment_category,
                    caption=label,
                    source="website_installation_estimate",
                    created_by="public_website",
                    source_meta={
                        "intake": "installation_estimate",
                        "photo_category": upload.category,
                        "request_fingerprint": fingerprint,
                        "received_at": received_at.isoformat(),
                    },
                    storage=attempt_storage,
                    created_storage_keys=created_storage_keys,
                    commit=False,
                    tenant_scope=tenant_scope,
                )

            await IntegrationOutboxService.enqueue(
                session,
                event_type=INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
                aggregate_type="order",
                aggregate_id=int(order.id or 0),
                payload=InstallationEstimateLeadCreatedPayloadV1(
                    order_id=int(order.id or 0),
                    status="new_lead",
                    name=payload.name,
                    phone=payload.phone,
                    email=payload.email,
                    address=payload.address,
                    description=payload.description,
                    attachment_count=len(uploads),
                    photo_categories=tuple(
                        PHOTO_CATEGORIES[category][1] for category in category_counts
                    ),
                ),
                idempotency_key=f"installation-estimate-v1:{fingerprint}",
                priority=20,
                max_attempts=8,
            )
            response = InstallationEstimateLeadResponse(
                lead_id=int(order.id or 0),
                order_id=int(order.id or 0),
                status="new_lead",
                created_at=order.created_at,
                attachment_count=len(uploads),
                replayed=False,
            )
            return PublicWriteCommandResponse(
                value=response,
                resource_type="order",
                resource_id=response.order_id,
            )

        async def execute_once():
            return await PublicWriteIdempotencyService.execute(
                session,
                tenant_scope=tenant_scope,
                command_name="public_installation_estimate_lead_v1",
                idempotency_key=idempotency_key,
                request_fingerprint=payload_hash,
                response_model=InstallationEstimateLeadResponse,
                operation=create,
            )

        try:
            for attempt in range(2):
                try:
                    outcome = await execute_once()
                    break
                except IntegrityError:
                    if attempt > 0:
                        raise
                    await cls._cleanup_failed_uploads(
                        session,
                        storage=selected_storage,
                        storage_keys=created_storage_keys,
                    )
                    created_storage_keys.clear()
            else:  # pragma: no cover - loop always returns or raises
                raise RuntimeError("Installation estimate retry was exhausted")
        except Exception as exc:
            await cls._cleanup_failed_uploads(
                session,
                storage=selected_storage,
                storage_keys=created_storage_keys,
            )
            if isinstance(exc, InstallationEventEnqueueFenceBusy):
                raise InstallationEstimateTemporarilyUnavailable(
                    "installation_estimate_temporarily_unavailable"
                ) from exc
            raise
        return outcome.value

    @staticmethod
    async def _find_existing(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        fingerprint: str,
    ) -> Order | None:
        return await session.scalar(
            select(Order)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                Order.source_fingerprint == fingerprint,
                storefront_scope_clause(Order, tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope),
            )
            .limit(1)
        )

    @staticmethod
    def _replay_response(
        order: Order,
        *,
        payload_hash: str,
    ) -> InstallationEstimateLeadResponse:
        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        estimate_meta = meta.get("installation_estimate")
        if not isinstance(estimate_meta, dict) or estimate_meta.get(
            "request_payload_hash"
        ) != payload_hash:
            raise InstallationEstimateIdempotencyConflict(
                "Idempotency-Key уже использован для другой заявки"
            )
        return InstallationEstimateLeadResponse(
            lead_id=int(order.id or 0),
            order_id=int(order.id or 0),
            status=(
                order.status.value
                if hasattr(order.status, "value")
                else str(order.status)
            ),
            created_at=order.created_at,
            attachment_count=int(estimate_meta.get("attachment_count") or 0),
            replayed=True,
        )

    @staticmethod
    async def _cleanup_failed_uploads(
        session: AsyncSession,
        *,
        storage: PrivateAttachmentStorage,
        storage_keys: set[str],
    ) -> None:
        if not storage_keys:
            return
        try:
            await ServiceAttachmentService.delete_unreferenced_storage_keys(
                session,
                storage=storage,
                storage_keys=storage_keys,
            )
        except Exception:
            logger.exception(
                "INSTALLATION_ESTIMATE_STORAGE_COMPENSATION_FAILED keys=%s",
                len(storage_keys),
            )

    @staticmethod
    def _build_comment(
        *,
        payload: InstallationEstimateLeadPayload,
        category_counts: dict[str, int],
    ) -> str:
        lines = [
            "Заявка на предварительную оценку монтажа по фотографиям.",
            "Стоимость и техническое решение требуют проверки специалистом.",
        ]
        if payload.address:
            lines.append(f"Адрес/район: {payload.address}")
        if payload.object_type:
            lines.append(f"Тип объекта: {payload.object_type}")
        if payload.description:
            lines.append(f"Комментарий клиента: {payload.description}")
        photo_summary = ", ".join(
            f"{PHOTO_CATEGORIES[category][1]}: {count}"
            for category, count in category_counts.items()
        )
        lines.append(f"Фото: {photo_summary}")
        return "\n".join(lines)

    @staticmethod
    def _clean_filename(value: Any) -> str:
        filename = Path(str(value or "photo")).name.replace("\x00", "").strip()
        return filename[:255] or "photo"

    @staticmethod
    async def _validate_image(
        *,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> None:
        if content_type not in ALLOWED_IMAGE_MIME_TYPES:
            raise ValueError(
                f"{filename}: поддерживаются только JPEG, PNG и WebP"
            )
        if not content:
            raise ValueError(f"{filename}: файл пуст")
        if len(content) > MAX_FILE_BYTES:
            raise ValueError(
                f"{filename}: размер не должен превышать "
                f"{MAX_FILE_BYTES // (1024 * 1024)} МБ"
            )

        def verify() -> str:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as image:
                    image.verify()
                    return str(image.format or "").upper()

        try:
            detected_format = await asyncio.to_thread(verify)
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise ValueError(f"{filename}: файл не является корректным изображением") from exc
        if detected_format != ALLOWED_IMAGE_MIME_TYPES[content_type]:
            raise ValueError(
                f"{filename}: содержимое файла не соответствует типу {content_type}"
            )
