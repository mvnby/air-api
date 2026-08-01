from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from core.database import async_session_maker
from models import IntegrationOutboxEvent, Order
from schemas import ManagerRepairActAiDraftPayload
from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.defect_act_ai_service import DefectActAIService
from services.general_media_storage_service import get_general_media_storage
from services.order_service import OrderService
from services.repair_diagnostic_service import (
    PHOTO_FIELDS,
    SYMPTOM_FAULT_TYPE,
    SYMPTOM_LABELS,
    RepairDiagnosticIncomingFile,
    RepairDiagnosticLeadPayload,
    RepairDiagnosticService,
)


_TERMINAL_STATUSES = frozenset({"completed", "failed", "skipped"})
_PROVIDER_STATUS_PATTERN = re.compile(r"(?:error|ошибку)\s+(\d{3})", re.I)
_OCR_BUSINESS_FAILURES = (
    "Файл пустой",
    "Файл слишком большой",
    "Не удалось распознать текст",
    "Поддерживаются только",
)


class RepairDiagnosticAiRetryableError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)[:100]
        super().__init__(str(message)[:300])


class RepairDiagnosticAiLeaseLost(RepairDiagnosticAiRetryableError):
    def __init__(self) -> None:
        super().__init__(
            "repair_ai_lease_lost",
            "Repair diagnostic AI job lease was lost",
        )


class _RepairDiagnosticAiTerminalError(RuntimeError):
    def __init__(self, *, status: str, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.public_message = message
        super().__init__(message)


class RepairDiagnosticAiService:
    """Run repair OCR/AI with explicit outcomes and a durable lease fence."""

    @classmethod
    async def run(
        cls,
        *,
        order_id: int,
        tenant_id: int,
        job_event_id: str | None = None,
        job_lease_token: str | None = None,
        payload_data: dict[str, Any] | None = None,
        nameplate_files: list[RepairDiagnosticIncomingFile] | None = None,
    ) -> None:
        if bool(job_event_id) != bool(job_lease_token):
            raise ValueError("Repair AI job fence requires event ID and lease token")

        async with async_session_maker() as session:
            order = await session.scalar(
                select(Order).where(
                    Order.id == order_id,
                    Order.tenant_id == tenant_id,
                ).limit(1)
            )
            if order is None:
                return
            repair_meta = OrderService._get_repair_meta(order)
            if repair_meta.get("ai_pre_diagnosis_status") in _TERMINAL_STATUSES:
                return

            try:
                payload = RepairDiagnosticLeadPayload.model_validate(
                    payload_data
                    if payload_data is not None
                    else RepairDiagnosticService._payload_from_repair_meta(
                        repair_meta
                    )
                )
            except ValidationError:
                await cls._persist_outcome(
                    session,
                    order=order,
                    repair_meta=repair_meta,
                    status="failed",
                    error_code="repair_ai_invalid_durable_payload",
                    error_message="Stored repair diagnostic data is invalid",
                    job_event_id=job_event_id,
                    job_lease_token=job_lease_token,
                )
                return

            try:
                durable_nameplates = (
                    nameplate_files
                    if nameplate_files is not None
                    else await cls._load_durable_nameplate_files(repair_meta)
                )
                await cls._apply_nameplate_recognition(
                    repair_meta,
                    durable_nameplates,
                )
                ai_meta = await cls._build_ai_meta(payload, repair_meta)
            except _RepairDiagnosticAiTerminalError as exc:
                await cls._persist_outcome(
                    session,
                    order=order,
                    repair_meta=repair_meta,
                    status=exc.status,
                    error_code=exc.code,
                    error_message=exc.public_message,
                    job_event_id=job_event_id,
                    job_lease_token=job_lease_token,
                )
                return
            except RepairDiagnosticAiRetryableError:
                raise
            except Exception as exc:
                raise cls._retryable_error(exc, stage="pipeline") from exc

            if ai_meta:
                repair_meta.update(ai_meta)
            await cls._persist_outcome(
                session,
                order=order,
                repair_meta=repair_meta,
                status="completed",
                job_event_id=job_event_id,
                job_lease_token=job_lease_token,
            )

    @classmethod
    async def mark_exhausted_failure(
        cls,
        session,
        *,
        order_id: int,
        tenant_id: int,
        error_code: str,
    ) -> None:
        statement = select(Order).where(
            Order.id == order_id,
            Order.tenant_id == tenant_id,
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        order = await session.scalar(statement)
        if order is None:
            return
        repair_meta = OrderService._get_repair_meta(order)
        if repair_meta.get("ai_pre_diagnosis_status") in _TERMINAL_STATUSES:
            return
        repair_meta["ai_pre_diagnosis_status"] = "failed"
        repair_meta["ai_pre_diagnosis_error_code"] = str(error_code)[:100]
        repair_meta["ai_pre_diagnosis_error"] = (
            "AI pre-diagnosis could not be completed after retries"
        )
        repair_meta["ai_pre_diagnosis_updated_at"] = cls._now_iso()
        OrderService._set_repair_meta(
            order,
            repair_meta,
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )
        flag_modified(order, "technical_meta")
        session.add(order)

    @classmethod
    async def _persist_outcome(
        cls,
        session,
        *,
        order: Order,
        repair_meta: dict[str, Any],
        status: str,
        job_event_id: str | None,
        job_lease_token: str | None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if job_event_id and job_lease_token:
            await cls._lock_live_job_lease(
                session,
                event_id=job_event_id,
                lease_token=job_lease_token,
            )
        repair_meta["ai_pre_diagnosis_status"] = status
        repair_meta["ai_pre_diagnosis_updated_at"] = cls._now_iso()
        if error_code:
            repair_meta["ai_pre_diagnosis_error_code"] = error_code[:100]
        else:
            repair_meta.pop("ai_pre_diagnosis_error_code", None)
        if error_message:
            repair_meta["ai_pre_diagnosis_error"] = error_message[:300]
        else:
            repair_meta.pop("ai_pre_diagnosis_error", None)
        OrderService._set_repair_meta(
            order,
            repair_meta,
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )
        flag_modified(order, "technical_meta")
        session.add(order)
        await session.commit()

    @staticmethod
    async def _lock_live_job_lease(
        session,
        *,
        event_id: str,
        lease_token: str,
    ) -> None:
        statement = select(IntegrationOutboxEvent).where(
            IntegrationOutboxEvent.event_id == event_id,
            IntegrationOutboxEvent.status == "processing",
            IntegrationOutboxEvent.lease_token == lease_token,
            IntegrationOutboxEvent.lease_expires_at.is_not(None),
            IntegrationOutboxEvent.lease_expires_at > datetime.now(timezone.utc),
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        if await session.scalar(statement) is None:
            raise RepairDiagnosticAiLeaseLost()

    @classmethod
    async def _load_durable_nameplate_files(
        cls,
        repair_meta: dict[str, Any],
    ) -> list[RepairDiagnosticIncomingFile]:
        photos = repair_meta.get("photos")
        nameplates = photos.get("nameplate") if isinstance(photos, dict) else None
        if not isinstance(nameplates, list) or not nameplates:
            return []
        item = nameplates[0] if isinstance(nameplates[0], dict) else {}
        path = str(item.get("storage_path") or "")
        if not path:
            raise _RepairDiagnosticAiTerminalError(
                status="failed",
                code="repair_ai_nameplate_reference_invalid",
                message="Stored nameplate reference is invalid",
            )
        try:
            content = await get_general_media_storage().read_media(path)
        except Exception as exc:
            raise cls._retryable_error(exc, stage="storage_read") from exc
        return [
            RepairDiagnosticIncomingFile(
                filename=str(item.get("filename") or "nameplate"),
                content_type=str(item.get("content_type") or "") or None,
                content=content,
                content_hash=str(item.get("content_hash") or ""),
            )
        ]

    @classmethod
    async def _apply_nameplate_recognition(
        cls,
        repair_meta: dict[str, Any],
        nameplate_files: list[RepairDiagnosticIncomingFile],
    ) -> None:
        if not nameplate_files:
            repair_meta["nameplate_recognition_status"] = "missing_photo"
            return
        file = nameplate_files[0]
        try:
            recognized = await BotRepairNameplateService.recognize_bytes(
                content=file.content,
                filename=file.filename,
                mime_type=file.content_type,
            )
        except ValueError as exc:
            terminal = cls._terminal_provider_error(exc, stage="ocr")
            if terminal is not None:
                raise terminal from exc
            if any(marker in str(exc) for marker in _OCR_BUSINESS_FAILURES):
                repair_meta["nameplate_recognition_status"] = "failed"
                repair_meta["nameplate_recognition_error_code"] = (
                    "repair_ai_nameplate_unreadable"
                )
                return
            raise cls._retryable_error(exc, stage="ocr") from exc
        except Exception as exc:
            raise cls._retryable_error(exc, stage="ocr") from exc

        extracted = recognized.get("extracted") if isinstance(recognized, dict) else {}
        if not isinstance(extracted, dict):
            extracted = {}
        merge = BotRepairNameplateService.preview_merge(repair_meta, extracted)
        if merge["applied"]:
            repair_meta.update(merge["applied"])
        repair_meta["nameplate_recognition_status"] = "recognized"
        repair_meta.pop("nameplate_recognition_error_code", None)
        repair_meta["nameplate_recognition"] = {
            "filename": file.filename,
            "extracted": extracted,
            "validation_flags": recognized.get("validation_flags") or {},
            "applied_fields": list(merge["applied"].keys()),
            "conflicts": merge["conflicts"],
        }

    @classmethod
    async def _build_ai_meta(
        cls,
        payload: RepairDiagnosticLeadPayload,
        repair_meta: dict[str, Any],
    ) -> dict[str, Any]:
        diagnostic_context = RepairDiagnosticService._build_order_comment(
            payload,
            {field: [] for field in PHOTO_FIELDS},
        )
        try:
            return await DefectActAIService.generate_repair_meta(
                ManagerRepairActAiDraftPayload(
                    defect_type=SYMPTOM_FAULT_TYPE[payload.symptom],
                    defect_label=SYMPTOM_LABELS[payload.symptom],
                    allow_assumptions=False,
                    polish_existing=False,
                    equipment_name=repair_meta.get("equipment_name"),
                    equipment_brand=repair_meta.get("equipment_brand"),
                    equipment_model=repair_meta.get("equipment_model"),
                    equipment_power=repair_meta.get("equipment_power"),
                    customer_complaint=repair_meta.get("customer_complaint"),
                    complaint_official=repair_meta.get("complaint_official"),
                    likely_diagnosis=repair_meta.get("likely_diagnosis"),
                    extra_context=diagnostic_context,
                    current_meta=repair_meta,
                )
            )
        except ValueError as exc:
            terminal = cls._terminal_provider_error(exc, stage="provider")
            if terminal is not None:
                raise terminal from exc
            raise cls._retryable_error(exc, stage="provider") from exc
        except Exception as exc:
            raise cls._retryable_error(exc, stage="provider") from exc

    @staticmethod
    def _terminal_provider_error(
        error: Exception,
        *,
        stage: str,
    ) -> _RepairDiagnosticAiTerminalError | None:
        message = str(error)
        if "is not configured" in message:
            return _RepairDiagnosticAiTerminalError(
                status="skipped",
                code=f"repair_ai_{stage}_not_configured",
                message="AI provider is not configured",
            )
        status_match = _PROVIDER_STATUS_PATTERN.search(message)
        status_code = int(status_match.group(1)) if status_match else None
        if status_code in {400, 401, 403, 404, 405, 422}:
            return _RepairDiagnosticAiTerminalError(
                status="failed",
                code=f"repair_ai_{stage}_request_rejected",
                message="AI provider rejected the request",
            )
        return None

    @staticmethod
    def _retryable_error(
        error: Exception,
        *,
        stage: str,
    ) -> RepairDiagnosticAiRetryableError:
        if isinstance(error, (TimeoutError, httpx.TimeoutException)):
            suffix = "timeout"
        elif isinstance(error, (OSError, httpx.TransportError)):
            suffix = "unavailable"
        else:
            suffix = "transient_failure"
        return RepairDiagnosticAiRetryableError(
            f"repair_ai_{stage}_{suffix}",
            f"Repair diagnostic {stage} infrastructure failure",
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
