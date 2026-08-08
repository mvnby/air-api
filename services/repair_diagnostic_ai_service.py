from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, NoReturn

import httpx
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from core.database import async_session_maker
from models import IntegrationOutboxEvent, Order
from schemas import ManagerRepairActAiDraftPayload
from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.defect_act_ai_service import (
    DefectActAIProviderError,
    DefectActAIService,
)
from services.google_vision_error_policy import OcrProviderError
from services.order_service import OrderService
from services.repair_diagnostic_attachment_service import (
    PrivateOrderAttachmentSource,
    RepairDiagnosticAttachmentService,
)
from services.repair_diagnostic_contracts import (
    CLIENT_CHECK_LABELS,
    SYMPTOM_DETAIL_LABELS,
    SYMPTOM_DETAIL_VALUE_LABELS,
    SYMPTOM_FAULT_TYPE,
    SYMPTOM_LABELS,
    TIMING_LABELS,
    RepairDiagnosticIncomingFile,
    RepairDiagnosticLeadPayload,
)
from services.repair_diagnostic_service import RepairDiagnosticService
from services.tenant_scope_service import TenantScope


_TERMINAL_STATUSES = frozenset({"completed", "failed", "skipped"})
_RECOGNIZED_EQUIPMENT_KEYS = frozenset(BotRepairNameplateService.REPAIR_FIELDS)
_PROVIDER_CONTEXT_EQUIPMENT_KEYS = frozenset(
    {
        "equipment_name",
        "equipment_brand",
        "equipment_model",
        "equipment_power",
        "refrigerant_type",
        "refrigerant_amount",
    }
)
_AI_OWNED_KEYS = frozenset(
    set(DefectActAIService.STRUCTURED_RESPONSE_KEYS)
    | set(DefectActAIService.PRIMARY_RESPONSE_KEYS)
    | set(_RECOGNIZED_EQUIPMENT_KEYS)
    | {
        "nameplate_recognition",
        "nameplate_recognition_status",
        "nameplate_recognition_error_code",
        "ai_pre_diagnosis_status",
        "ai_pre_diagnosis_error_code",
        "ai_pre_diagnosis_error",
        "ai_pre_diagnosis_updated_at",
    }
)
_MISSING = object()


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


@dataclass(frozen=True)
class _RepairDiagnosticAiSnapshot:
    order_id: int
    tenant_id: int
    storefront_id: int
    base_repair_meta: dict[str, Any]
    payload: RepairDiagnosticLeadPayload
    nameplate_source: PrivateOrderAttachmentSource | None


@dataclass(frozen=True)
class _RepairDiagnosticAiSnapshotFailure:
    order_id: int
    tenant_id: int
    base_repair_meta: dict[str, Any]
    outcome: _RepairDiagnosticAiTerminalError


class RepairDiagnosticAiService:
    """Run providers outside DB sessions, then merge behind the live lease."""

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

        loaded = await cls._load_snapshot(
            order_id=order_id,
            tenant_id=tenant_id,
            payload_data=payload_data,
            resolve_nameplate=nameplate_files is None,
        )
        if loaded is None:
            return
        if isinstance(loaded, _RepairDiagnosticAiSnapshotFailure):
            await cls._persist_outcome(
                order_id=loaded.order_id,
                tenant_id=loaded.tenant_id,
                base_repair_meta=loaded.base_repair_meta,
                computed_repair_meta=loaded.base_repair_meta,
                status=loaded.outcome.status,
                error_code=loaded.outcome.code,
                error_message=loaded.outcome.public_message,
                job_event_id=job_event_id,
                job_lease_token=job_lease_token,
            )
            return

        working_meta = copy.deepcopy(loaded.base_repair_meta)
        try:
            durable_nameplates = (
                nameplate_files
                if nameplate_files is not None
                else await cls._load_durable_nameplate_files(loaded)
            )
            await cls._apply_nameplate_recognition(
                working_meta,
                durable_nameplates,
            )
            ai_meta = await cls._build_ai_meta(loaded.payload, working_meta)
            if ai_meta:
                working_meta.update(ai_meta)
        except _RepairDiagnosticAiTerminalError as exc:
            await cls._persist_outcome(
                order_id=loaded.order_id,
                tenant_id=loaded.tenant_id,
                base_repair_meta=loaded.base_repair_meta,
                computed_repair_meta=working_meta,
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

        await cls._persist_outcome(
            order_id=loaded.order_id,
            tenant_id=loaded.tenant_id,
            base_repair_meta=loaded.base_repair_meta,
            computed_repair_meta=working_meta,
            status="completed",
            job_event_id=job_event_id,
            job_lease_token=job_lease_token,
        )

    @classmethod
    async def _load_snapshot(
        cls,
        *,
        order_id: int,
        tenant_id: int,
        payload_data: dict[str, Any] | None,
        resolve_nameplate: bool,
    ) -> _RepairDiagnosticAiSnapshot | _RepairDiagnosticAiSnapshotFailure | None:
        async with async_session_maker() as session:
            order = await session.scalar(
                select(Order)
                .where(
                    Order.id == order_id,
                    Order.tenant_id == tenant_id,
                )
                .limit(1)
            )
            if order is None:
                return None
            base_meta = copy.deepcopy(OrderService._get_repair_meta(order))
            if base_meta.get("ai_pre_diagnosis_status") in _TERMINAL_STATUSES:
                return None
            try:
                payload = RepairDiagnosticLeadPayload.model_validate(
                    payload_data
                    if payload_data is not None
                    else RepairDiagnosticService._payload_from_repair_meta(base_meta)
                )
            except ValidationError:
                return _RepairDiagnosticAiSnapshotFailure(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    base_repair_meta=base_meta,
                    outcome=_RepairDiagnosticAiTerminalError(
                        status="failed",
                        code="repair_ai_invalid_durable_payload",
                        message="Stored repair diagnostic data is invalid",
                    ),
                )

            storefront_id = int(order.storefront_id or 0)
            nameplate_source = None
            if resolve_nameplate:
                attachment_id = cls._nameplate_attachment_id(base_meta)
                if attachment_id is not None:
                    if storefront_id <= 0:
                        return cls._invalid_nameplate_failure(
                            order_id,
                            tenant_id,
                            base_meta,
                        )
                    nameplate_source = (
                        await RepairDiagnosticAttachmentService.resolve_source(
                            session,
                            order_id=order_id,
                            attachment_id=attachment_id,
                            tenant_scope=TenantScope(
                                tenant_id=tenant_id,
                                storefront_id=storefront_id,
                                is_system=True,
                            ),
                        )
                    )
                    if nameplate_source is None:
                        return cls._invalid_nameplate_failure(
                            order_id,
                            tenant_id,
                            base_meta,
                        )
            return _RepairDiagnosticAiSnapshot(
                order_id=order_id,
                tenant_id=tenant_id,
                storefront_id=storefront_id,
                base_repair_meta=base_meta,
                payload=payload,
                nameplate_source=nameplate_source,
            )

    @staticmethod
    def _invalid_nameplate_failure(
        order_id: int,
        tenant_id: int,
        base_meta: dict[str, Any],
    ) -> _RepairDiagnosticAiSnapshotFailure:
        return _RepairDiagnosticAiSnapshotFailure(
            order_id=order_id,
            tenant_id=tenant_id,
            base_repair_meta=base_meta,
            outcome=_RepairDiagnosticAiTerminalError(
                status="failed",
                code="repair_ai_nameplate_reference_invalid",
                message="Stored nameplate reference is invalid",
            ),
        )

    @staticmethod
    def _nameplate_attachment_id(repair_meta: dict[str, Any]) -> int | None:
        photos = repair_meta.get("photos")
        nameplates = photos.get("nameplate") if isinstance(photos, dict) else None
        if not isinstance(nameplates, list) or not nameplates:
            return None
        item = nameplates[0] if isinstance(nameplates[0], dict) else {}
        try:
            attachment_id = int(item.get("attachment_id") or 0)
        except (TypeError, ValueError):
            attachment_id = 0
        return attachment_id if attachment_id > 0 else -1

    @classmethod
    async def _load_durable_nameplate_files(
        cls,
        snapshot: _RepairDiagnosticAiSnapshot,
    ) -> list[RepairDiagnosticIncomingFile]:
        source = snapshot.nameplate_source
        if source is None:
            return []
        try:
            content = await RepairDiagnosticAttachmentService.read_source(source)
        except Exception as exc:
            raise cls._retryable_error(exc, stage="storage_read") from exc
        return [
            RepairDiagnosticIncomingFile(
                filename=source.filename,
                content_type=source.mime_type,
                content=content,
                content_hash=source.content_hash or "",
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
        except DefectActAIProviderError as exc:
            cls._raise_typed_provider_outcome(exc, stage="ocr")
        except OcrProviderError as exc:
            code = f"repair_ai_ocr_{exc.code}"[:100]
            if exc.retryable:
                raise RepairDiagnosticAiRetryableError(
                    code,
                    "Repair diagnostic OCR infrastructure failure",
                ) from exc
            raise _RepairDiagnosticAiTerminalError(
                status=(
                    "skipped"
                    if exc.code == "not_configured"
                    else "failed"
                ),
                code=code,
                message=(
                    "OCR provider is not configured"
                    if exc.code == "not_configured"
                    else "OCR provider rejected the request"
                ),
            ) from exc
        except ValueError as exc:
            repair_meta["nameplate_recognition_status"] = "failed"
            repair_meta["nameplate_recognition_error_code"] = (
                "repair_ai_nameplate_unreadable"
            )
            return
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
            "extracted": {
                key: extracted[key]
                for key in _RECOGNIZED_EQUIPMENT_KEYS
                if extracted.get(key)
            },
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
        safe_current_meta = {
            key: repair_meta[key]
            for key in _PROVIDER_CONTEXT_EQUIPMENT_KEYS
            if repair_meta.get(key)
        }
        symptom_label = SYMPTOM_LABELS[payload.symptom]
        try:
            return await DefectActAIService.generate_repair_meta(
                ManagerRepairActAiDraftPayload(
                    defect_type=SYMPTOM_FAULT_TYPE[payload.symptom],
                    defect_label=symptom_label,
                    allow_assumptions=False,
                    polish_existing=False,
                    equipment_name=safe_current_meta.get("equipment_name"),
                    equipment_brand=safe_current_meta.get("equipment_brand"),
                    equipment_model=safe_current_meta.get("equipment_model"),
                    equipment_power=safe_current_meta.get("equipment_power"),
                    customer_complaint=f"Симптом: {symptom_label}",
                    complaint_official=f"Заявленный симптом: {symptom_label}",
                    refrigerant_type=safe_current_meta.get("refrigerant_type"),
                    refrigerant_amount=safe_current_meta.get("refrigerant_amount"),
                    extra_context=cls._safe_diagnostic_context(payload),
                    current_meta=safe_current_meta,
                )
            )
        except DefectActAIProviderError as exc:
            cls._raise_typed_provider_outcome(exc, stage="provider")
        except Exception as exc:
            raise cls._retryable_error(exc, stage="provider") from exc
        raise AssertionError("unreachable")

    @staticmethod
    def _safe_diagnostic_context(payload: RepairDiagnosticLeadPayload) -> str:
        lines = [f"Симптом: {SYMPTOM_LABELS[payload.symptom]}"]
        if payload.problem_timing:
            lines.append(f"Время проявления: {TIMING_LABELS[payload.problem_timing]}")
        for key, value in payload.symptom_details.items():
            value_label = SYMPTOM_DETAIL_VALUE_LABELS.get(key, {}).get(
                value,
                value,
            )
            lines.append(f"{SYMPTOM_DETAIL_LABELS[key]}: {value_label}")
        if payload.client_checks:
            labels = [CLIENT_CHECK_LABELS[item] for item in payload.client_checks]
            lines.append(f"Проверки клиента: {', '.join(labels)}")
        return "\n".join(lines)

    @staticmethod
    def _raise_typed_provider_outcome(
        error: DefectActAIProviderError,
        *,
        stage: str,
    ) -> NoReturn:
        code = f"repair_ai_{stage}_{error.code}"[:100]
        if error.code == "not_configured":
            raise _RepairDiagnosticAiTerminalError(
                status="skipped",
                code=code,
                message="AI provider is not configured",
            ) from error
        if error.retryable:
            raise RepairDiagnosticAiRetryableError(
                code,
                f"Repair diagnostic {stage} infrastructure failure",
            ) from error
        raise _RepairDiagnosticAiTerminalError(
            status="failed",
            code=code,
            message="AI provider rejected the request",
        ) from error

    @classmethod
    async def _persist_outcome(
        cls,
        *,
        order_id: int,
        tenant_id: int,
        base_repair_meta: dict[str, Any],
        computed_repair_meta: dict[str, Any],
        status: str,
        job_event_id: str | None,
        job_lease_token: str | None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        computed = copy.deepcopy(computed_repair_meta)
        computed["ai_pre_diagnosis_status"] = status
        computed["ai_pre_diagnosis_updated_at"] = cls._now_iso()
        if error_code:
            computed["ai_pre_diagnosis_error_code"] = error_code[:100]
        else:
            computed.pop("ai_pre_diagnosis_error_code", None)
        if error_message:
            computed["ai_pre_diagnosis_error"] = error_message[:300]
        else:
            computed.pop("ai_pre_diagnosis_error", None)

        async with async_session_maker() as session:
            async with session.begin():
                if job_event_id and job_lease_token:
                    await cls._lock_live_job_lease(
                        session,
                        event_id=job_event_id,
                        lease_token=job_lease_token,
                        order_id=order_id,
                        tenant_id=tenant_id,
                    )
                order_statement = select(Order).where(
                    Order.id == order_id,
                    Order.tenant_id == tenant_id,
                )
                if session.get_bind().dialect.name == "postgresql":
                    order_statement = order_statement.with_for_update()
                order = await session.scalar(order_statement)
                if order is None:
                    return
                latest = OrderService._get_repair_meta(order)
                if latest.get("ai_pre_diagnosis_status") in _TERMINAL_STATUSES:
                    return
                merged = cls._three_way_merge(
                    base=base_repair_meta,
                    latest=latest,
                    computed=computed,
                )
                OrderService._set_repair_meta(
                    order,
                    merged,
                    default_status=OrderService.REPAIR_DEFAULT_STATUS,
                )
                flag_modified(order, "technical_meta")
                session.add(order)

    @staticmethod
    def _three_way_merge(
        *,
        base: dict[str, Any],
        latest: dict[str, Any],
        computed: dict[str, Any],
    ) -> dict[str, Any]:
        merged = copy.deepcopy(latest)
        for key in _AI_OWNED_KEYS:
            base_value = base.get(key, _MISSING)
            computed_value = computed.get(key, _MISSING)
            if computed_value == base_value:
                continue
            latest_value = latest.get(key, _MISSING)
            if latest_value != base_value:
                continue
            if computed_value is _MISSING:
                merged.pop(key, None)
            else:
                merged[key] = copy.deepcopy(computed_value)
        return merged

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

    @staticmethod
    async def _lock_live_job_lease(
        session,
        *,
        event_id: str,
        lease_token: str,
        order_id: int,
        tenant_id: int,
    ) -> None:
        database_clock = (
            func.clock_timestamp()
            if session.get_bind().dialect.name == "postgresql"
            else func.current_timestamp()
        )
        statement = select(IntegrationOutboxEvent).where(
            IntegrationOutboxEvent.event_id == event_id,
            IntegrationOutboxEvent.event_type
            == "repair.diagnostic_ai_requested.v1",
            IntegrationOutboxEvent.aggregate_type == "order",
            IntegrationOutboxEvent.aggregate_id == str(order_id),
            IntegrationOutboxEvent.status == "processing",
            IntegrationOutboxEvent.lease_token == lease_token,
            IntegrationOutboxEvent.lease_expires_at.is_not(None),
            IntegrationOutboxEvent.lease_expires_at > database_clock,
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        event = await session.scalar(statement)
        payload = event.payload if event is not None else None
        if (
            event is None
            or not isinstance(payload, dict)
            or str(payload.get("tenant_id") or "") != str(tenant_id)
            or str(payload.get("order_id") or "") != str(order_id)
        ):
            raise RepairDiagnosticAiLeaseLost()

    @staticmethod
    def _retryable_error(
        error: Exception,
        *,
        stage: str,
    ) -> RepairDiagnosticAiRetryableError:
        if isinstance(error, DefectActAIProviderError):
            suffix = error.code
        elif isinstance(error, (TimeoutError, httpx.TimeoutException)):
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
