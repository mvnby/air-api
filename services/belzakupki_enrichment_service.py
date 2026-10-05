"""Read source evidence and apply only manager-reviewed order enrichment."""

from __future__ import annotations

import re
import mimetypes
from io import BytesIO
from typing import Any
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

import httpx
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import Customer, CustomerBranch, LeadSource, Order, OrderAttachmentLink, OrderStatus, ServiceAttachment
from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import (
    ManagerOrderSourceApply,
    ManagerOrderSourceApplyResult,
    ManagerOrderSourceAnalyze,
    ManagerOrderSourcePreview,
    SourceCustomerDraft,
    SourceDocumentPreview,
    SourceEquipmentDraft,
    SourceObjectDraft,
    SourceScenarioDraft,
)
from services.belzakupki_customer_evidence import extract_customer_evidence
from services.belzakupki_customer_service import enrich_registry, apply_reviewed_customer
from services.commercial_terms_extraction import extract_commercial_terms
from services.order_commercial_terms_service import commercial_terms_response, store_source_terms
from services.belzakupki_source_analysis import analyze_tender_text, extract_missing_document_text
from services.belzakupki_equipment_prefill import BelzakupkiEquipmentPrefillService
from services.order_scenarios import SCENARIOS, infer_scenario_from_task, resolve_scenario
from services.service_attachment_service import ServiceAttachmentService
from services.tenant_entity_access_service import TenantEntityAccessService


_OBJECT_START = re.compile(
    r"(?:расположенн\w*\s+по\s+адресу|адрес\s+объекта|место\s+оказания\s+услуг)\s*:\s*",
    re.IGNORECASE,
)
_EQUIPMENT = re.compile(
    r"(?P<brand>TCL|GENERAL\s+CLIMATE|GENERAL|HORIZONT|[A-Z][A-Z\s]{2,25})\s*"
    r"\((?P<description>.{0,220}?)\)?\s*[–—-]\s*(?P<quantity>\d{1,3})\s*шт\.?",
    re.IGNORECASE,
)
_EQUIPMENT_MODEL = re.compile(
    r"(?:модель\s*:?|внутренний\s+блок)\s*(?P<model>[A-Z0-9][A-Z0-9/._-]{2,})",
    re.IGNORECASE,
)
_UNP = re.compile(r"\b(?:УНП|унп)\s*[:№]?\s*(\d{9})\b")
_PHONE = re.compile(r"(?:\+375|8\s*0)\s*\(?\d{2}\)?[\s()-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def _text(value: Any, limit: int = 4000) -> str | None:
    cleaned = " ".join(str(value or "").split())
    return cleaned[:limit] or None


def _amount(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raw = str(value or "").strip()
    if not re.fullmatch(r"\d[\d\s]*(?:[,.]\d{1,2})?(?:\s*(?:BYN|руб\.?))?", raw, re.I):
        return None
    number = re.sub(r"\s*(?:BYN|руб\.?)$", "", raw, flags=re.I).replace(" ", "").replace(",", ".")
    return float(number)


def _unp(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw or not re.fullmatch(r"[\d\s-]+", raw):
        return None
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) == 9 else None


def _customer_unp_from_document(raw: str, customer_name: str | None) -> str | None:
    """Require customer context; a tender document may list supplier UNPs too."""
    contextual: set[str] = set()
    name_start = (customer_name or "").strip("«»\" ").casefold()[:24]
    for match in _UNP.finditer(raw):
        before = raw[max(0, match.start() - 250):match.start()].casefold()
        customer_label = re.search(r"(?:заказчик|организатор|покупатель)[^.;]{0,180}$", before)
        if customer_label or (name_start and name_start in before):
            contextual.add(match.group(1))
    return next(iter(contextual)) if len(contextual) == 1 else None


def _original_file_type(content: bytes, filename: str, supplied_type: str) -> tuple[str, str]:
    """Identify supported originals even when the provider uses a display title."""
    mime = supplied_type.split(";", 1)[0].strip().lower()
    guessed = mimetypes.guess_type(filename)[0]
    if mime == "application/octet-stream":
        mime = guessed or ""
    if content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return filename if filename.lower().endswith(".doc") else filename + ".doc", "application/msword"
    if content.startswith(b"%PDF-"):
        return filename if filename.lower().endswith(".pdf") else filename + ".pdf", "application/pdf"
    if content.startswith(b"PK\x03\x04"):
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist()[:200])
        except BadZipFile:
            names = set()
        if "word/document.xml" in names:
            return filename if filename.lower().endswith(".docx") else filename + ".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if "xl/workbook.xml" in names:
            return filename if filename.lower().endswith(".xlsx") else filename + ".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if mime in ServiceAttachmentService.SAFE_MIME_TYPES:
        return filename, mime
    return filename, "application/octet-stream"


def _source_identity(order: Order) -> tuple[str, str]:
    if order.lead_source != LeadSource.BELZAKUPKI:
        raise ValueError("Order has no Belzakupki source")
    meta = (order.technical_meta or {}).get("belzakupki") or {}
    tender = meta.get("tender") or {}
    source = _text(tender.get("source") or meta.get("source"), 100)
    external_id = _text(meta.get("external_tender_id") or tender.get("external_id"), 300)
    if not source or not external_id:
        raise ValueError("Belzakupki source identity is missing")
    return source, external_id


def _scenario_draft(workflow_type: str, service_type: str | None) -> SourceScenarioDraft | None:
    scenario = next(
        (item for item in SCENARIOS if item.workflow_type == workflow_type and item.service_type == service_type),
        None,
    )
    if scenario is None:
        return None
    return SourceScenarioDraft(
        workflow_type=scenario.workflow_type, service_type=scenario.service_type, label=scenario.label,
    )


def _objects_from_text(raw: str) -> list[SourceObjectDraft]:
    """Recognize explicit address sections; never invent an object from a city mention."""
    # Legacy Word table extraction inserts pipe separators into phrases and
    # model rows. Remove column boundaries before detecting address sections.
    raw = re.sub(r"\s*\|\s*", " ", raw)
    raw = " ".join(raw.split())
    raw = re.sub(r"(?<=/)\s+(?=[A-Z0-9])", "", raw)
    starts = list(_OBJECT_START.finditer(raw))
    objects: list[SourceObjectDraft] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(raw)
        segment = raw[match.end():end]
        # The first colon after an address generally starts the equipment list.
        address, separator, equipment_text = segment.partition(":")
        address = _text(address, 350)
        if not separator or not address or not re.search(r"\b(?:г\.|г\.п\.|ул\.|пр\.|д\.)", address, re.I):
            continue
        equipment = []
        for found in _EQUIPMENT.finditer(equipment_text):
            model_match = _EQUIPMENT_MODEL.search(found.group("description"))
            equipment.append(SourceEquipmentDraft(
                brand=_text(found.group("brand"), 80),
                model=_text(model_match.group("model"), 120) if model_match else None,
                quantity=int(found.group("quantity")),
            ))
        previous = next((obj for obj in objects if obj.address.casefold() == address.casefold()), None)
        if previous is None:
            objects.append(SourceObjectDraft(address=address, equipment=equipment))
        elif equipment and not previous.equipment:
            previous.equipment = equipment
    return objects


class BelzakupkiEnrichmentService:
    @staticmethod
    async def _order(session: AsyncSession, order_id: int, scope: TenantScope, *, lock: bool = False) -> Order:
        order = await TenantEntityAccessService.get_order(session, order_id, tenant_scope=scope, for_update=lock)
        if order is None:
            raise LookupError("Order not found")
        _source_identity(order)
        return order

    @staticmethod
    async def _fetch(source: str, external_id: str, document_id: str | None = None) -> httpx.Response:
        base = str(settings.BELZAKUPKI_API_BASE_URL or "").strip().rstrip("/")
        key = settings.BELZAKUPKI_INTEGRATION_KEY
        if not base or not key:
            raise RuntimeError("Belzakupki integration is not configured")
        path = f"/api/v1/tenders/{quote(source, safe='')}/{quote(external_id, safe='')}"
        if document_id is not None:
            path += f"/documents/{quote(document_id, safe='')}"
        async with httpx.AsyncClient(timeout=settings.BELZAKUPKI_IMPORT_TIMEOUT_SECONDS) as client:
            response = await client.get(base + path, headers={"Authorization": f"Bearer {key}"})
            response.raise_for_status()
            return response

    @classmethod
    async def _detail(cls, order: Order) -> dict[str, Any]:
        source, external_id = _source_identity(order)
        data = (await cls._fetch(source, external_id)).json()
        if not isinstance(data, dict) or str(data.get("source")) != source or str(data.get("external_id")) != external_id:
            raise ValueError("Belzakupki detail identity mismatch")
        return data

    @staticmethod
    def _documents(data: dict[str, Any]) -> list[dict[str, Any]]:
        documents = data.get("documents")
        if not isinstance(documents, list):
            return []
        return [item for item in documents if isinstance(item, dict) and item.get("id") is not None]

    @classmethod
    async def preview(cls, session: AsyncSession, *, order_id: int, scope: TenantScope) -> ManagerOrderSourcePreview:
        order = await cls._order(session, order_id, scope)
        data = await cls._detail(order)
        source, external_id = _source_identity(order)
        raw = "\n".join(filter(None, [_text(data.get("description"), 30000)] + [
            _text(doc.get("extracted_text"), 100000) for doc in cls._documents(data)
        ]))
        evidence = extract_customer_evidence(data)
        await enrich_registry(evidence)
        customer = evidence.customer
        inn = customer.inn
        matches = []
        if inn:
            matches = (await session.execute(select(Customer).where(
                Customer.tenant_id == scope.tenant_id, Customer.inn == inn,
            ))).scalars().all()
        existing_customer_id = int(matches[0].id) if len(matches) == 1 else None
        if order.customer_id and existing_customer_id is None:
            current_customer = await TenantEntityAccessService.get_customer(session, order.customer_id, tenant_scope=scope)
            if current_customer is not None:
                name_key = lambda value: "".join(char for char in str(value or "").casefold() if char.isalnum())
                if current_customer.inn == inn and inn or (
                    not current_customer.inn and name_key(current_customer.name) == name_key(customer.name)
                ):
                    existing_customer_id = int(current_customer.id)
        warnings: list[str] = list(evidence.warnings)
        if not inn:
            warnings.append("УНП заказчика не найден; выберите клиента вручную или проверьте данные перед созданием.")
        elif len(matches) > 1:
            warnings.append("Найдено несколько клиентов с тем же УНП; выберите нужного вручную.")
        objects = _objects_from_text(raw)
        if not objects:
            warnings.append("Объекты и оборудование не удалось надёжно извлечь; заполните их вручную.")
        elif any(not obj.equipment for obj in objects):
            warnings.append("Для некоторых объектов оборудование не распознано; проверьте документ.")
        if any(item.model is None for obj in objects for item in obj.equipment):
            warnings.append("Некоторые модели оборудования не распознаны; проверьте их по оригиналу.")
        documents = [SourceDocumentPreview(
            id=str(doc["id"]),
            name=_text(doc.get("name"), 255) or "Документ",
            source_url=_text(doc.get("source_url"), 2048),
            extracted_text=_text(doc.get("extracted_text"), 100000),
            extracted_text_truncated=bool(doc.get("extracted_text_truncated")),
            download_url=f"/api/manager/orders/{order_id}/source-documents/{quote(str(doc['id']), safe='')}",
        ) for doc in cls._documents(data)]
        if any(not doc.extracted_text for doc in documents):
            warnings.append("Не все документы имеют извлечённый текст. Запустите анализ выбранного документа или заполните данные вручную.")
        summary = _text(data.get("description"), 5000)
        if not summary and raw:
            summary = _text(raw, 5000)
        equipment_details = "; ".join(
            f"{obj.address}: " + ", ".join(
                f"{item.brand or ''} {item.model or ''} — {item.quantity or '?'} шт.".strip()
                for item in obj.equipment
            ) for obj in objects
        ) or None
        previous = ((order.technical_meta or {}).get("belzakupki") or {}).get("enrichment")
        reviewed = (
            isinstance(previous, dict)
            and previous.get("source") == source
            and previous.get("external_id") == external_id
        )
        if reviewed:
            summary = previous.get("work_summary")
            equipment_details = previous.get("equipment_details")
            objects = [SourceObjectDraft.model_validate(obj) for obj in previous.get("objects") or []]
            warnings.append("Показаны ранее подтверждённые данные; новый анализ можно запустить отдельно.")
        current_service = (order.technical_meta or {}).get("service_type")
        try:
            current_workflow, current_service = resolve_scenario(
                workflow_type=order.workflow_type, service_type=current_service,
            )
        except ValueError:
            current_workflow = None
        current_scenario = _scenario_draft(current_workflow, current_service) if current_workflow else None
        suggested = infer_scenario_from_task(_text(data.get("title"), 1000)) or infer_scenario_from_task(summary)
        suggested_scenario = _scenario_draft(suggested.workflow_type, suggested.service_type) if suggested else None
        field_sources = dict(evidence.field_sources)
        draft_source = "Ранее подтверждено менеджером" if reviewed else "Текст документа"
        if summary:
            field_sources["work_summary"] = draft_source if reviewed or not data.get("description") else "Описание закупки"
        if equipment_details:
            field_sources["equipment_details"] = draft_source
        for index, obj in enumerate(objects):
            field_sources[f"objects.{index}.address"] = draft_source
            for equipment_index, _ in enumerate(obj.equipment):
                field_sources[f"objects.{index}.equipment.{equipment_index}"] = draft_source
        commercial_source_terms = extract_commercial_terms(str(data.get("description") or ""), source="Описание закупки")
        for document in documents:
            if document.extracted_text:
                extracted_terms = extract_commercial_terms(document.extracted_text, source=document.name)
                if document.extracted_text_truncated:
                    for term in extracted_terms:
                        term.issues.append("Текст документа обрезан; проверьте оригинал")
                commercial_source_terms.extend(extracted_terms)
        return ManagerOrderSourcePreview(
            commercial_terms=commercial_terms_response(order, terms=commercial_source_terms),
            order_id=order_id, source_code=source, external_id=external_id,
            source_url=_text(data.get("source_url"), 2048), title=_text(data.get("title"), 1000),
            deadline_at=_text(data.get("deadline_at"), 80), estimated_value=_amount(data.get("estimated_value")),
            customer=customer, existing_customer_id=existing_customer_id,
            contacts=evidence.contacts, related_customers=evidence.related_customers,
            submission=evidence.submission,
            current_scenario=current_scenario, suggested_scenario=suggested_scenario,
            work_summary=summary, equipment_details=equipment_details, objects=objects,
            documents=documents, field_sources=field_sources, warnings=warnings,
            analysis_source="reviewed" if reviewed else "source",
            analyzed_document_ids=[str(value) for value in previous.get("analyzed_document_ids") or []] if reviewed else [],
            equipment_prefill=previous.get("equipment_prefill") if reviewed else None,
        )

    @classmethod
    async def analyze(
        cls, session: AsyncSession, *, order_id: int, scope: TenantScope,
        payload: ManagerOrderSourceAnalyze,
    ) -> ManagerOrderSourcePreview:
        preview = await cls.preview(session, order_id=order_id, scope=scope)
        selected = dict.fromkeys(payload.document_ids)
        documents = {doc.id: doc for doc in preview.documents}
        if any(document_id not in documents for document_id in selected):
            raise ValueError("Unknown source document")
        texts: list[str] = []
        for document_id in selected:
            doc = documents[document_id]
            extracted = doc.extracted_text
            if not extracted or doc.extracted_text_truncated:
                content, filename, mime_type = await cls.document(
                    session, order_id=order_id, document_id=document_id, scope=scope,
                )
                extracted, diagnostic = await extract_missing_document_text(
                    filename=filename, mime_type=mime_type, content=content,
                )
                if diagnostic:
                    preview.warnings.append(f"{doc.name}: {diagnostic}")
                if extracted:
                    doc.extracted_text = extracted
                    doc.extracted_text_truncated = len(extracted) >= 100000
            if extracted:
                if doc.extracted_text_truncated:
                    raise ValueError(f"Текст документа «{doc.name}» обрезан. Проверьте оригинал перед анализом.")
                texts.append(f"Документ {doc.name}:\n{extracted}")
        if not texts:
            preview.warnings.append("Выбранные документы не содержат доступного текста для анализа.")
            return preview
        refreshed = extract_customer_evidence({
            "customer": {
                "name": preview.customer.name, "unp": preview.customer.inn,
                "legal_address": preview.customer.legal_address,
                "contacts": {"phone": preview.customer.phone, "email": preview.customer.email},
            },
            "source_url": preview.source_url,
            "documents": [doc.model_dump() for doc in preview.documents],
        })
        if refreshed.customer.inn != preview.customer.inn or any(
            candidate.inn not in {item.inn for item in preview.related_customers}
            for candidate in refreshed.related_customers
        ):
            await enrich_registry(refreshed)
        else:
            for field in ("name", "type", "legal_address"):
                if getattr(preview.customer, field):
                    setattr(refreshed.customer, field, getattr(preview.customer, field))
        preview.customer = refreshed.customer
        preview.contacts = refreshed.contacts
        preview.related_customers = refreshed.related_customers
        preview.submission = refreshed.submission
        preview.field_sources.update(refreshed.field_sources)
        preview.warnings = list(dict.fromkeys([*preview.warnings, *refreshed.warnings]))
        if preview.customer.inn:
            preview.warnings = [warning for warning in preview.warnings if not warning.startswith("УНП заказчика не найден;")]
        if all(doc.extracted_text for doc in preview.documents):
            preview.warnings = [warning for warning in preview.warnings if not warning.startswith("Не все документы имеют извлечённый текст.")]
        work_summary, equipment_details, objects = await analyze_tender_text("\n\n".join(texts))
        if work_summary:
            preview.work_summary = work_summary
            preview.field_sources["work_summary"] = "ИИ по выбранным документам"
            suggested = infer_scenario_from_task(work_summary)
            preview.suggested_scenario = (
                _scenario_draft(suggested.workflow_type, suggested.service_type) if suggested else None
            )
        if equipment_details:
            preview.equipment_details = equipment_details
            preview.field_sources["equipment_details"] = "ИИ по выбранным документам"
        if objects:
            preview.objects = objects
            for key in tuple(preview.field_sources):
                if key.startswith("objects."):
                    del preview.field_sources[key]
            for index, obj in enumerate(objects):
                preview.field_sources[f"objects.{index}.address"] = "ИИ по выбранным документам"
                for equipment_index, _ in enumerate(obj.equipment):
                    preview.field_sources[f"objects.{index}.equipment.{equipment_index}"] = "ИИ по выбранным документам"
        else:
            preview.warnings.append("AI не смог надёжно разделить объекты; проверьте адреса по оригиналу.")
        order = await cls._order(session, order_id, scope)
        selected_terms = []
        for doc in preview.documents:
            if doc.id in selected and doc.extracted_text:
                extracted_terms = extract_commercial_terms(doc.extracted_text, source=doc.name)
                if doc.extracted_text_truncated:
                    for term in extracted_terms:
                        term.issues.append("Текст документа обрезан; проверьте оригинал")
                selected_terms.extend(extracted_terms)
        preview.commercial_terms = commercial_terms_response(order, terms=selected_terms)
        preview.analysis_source = "ai"
        preview.analyzed_document_ids = list(selected)
        preview.warnings.append("AI подготовил черновик; проверьте адреса, модели и количество по оригиналу.")
        return preview

    @classmethod
    async def document(cls, session: AsyncSession, *, order_id: int, document_id: str, scope: TenantScope) -> tuple[bytes, str, str]:
        order = await cls._order(session, order_id, scope)
        detail = await cls._detail(order)
        doc = next((item for item in cls._documents(detail) if str(item["id"]) == document_id), None)
        if doc is None:
            raise LookupError("Source document not found")
        source, external_id = _source_identity(order)
        response = await cls._fetch(source, external_id, document_id)
        content_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
        if len(response.content) > int(settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES):
            raise ValueError("Source document exceeds the configured size limit")
        filename, content_type = _original_file_type(
            response.content, _text(doc.get("name"), 230) or "document", content_type,
        )
        return response.content, filename, content_type

    @classmethod
    async def apply(
        cls, session: AsyncSession, *, order_id: int, scope: TenantScope,
        payload: ManagerOrderSourceApply, username: str,
    ) -> ManagerOrderSourceApplyResult:
        if scope.demo_read_only:
            raise ValueError("Demo workspace is read-only")
        order = await cls._order(session, order_id, scope, lock=True)
        from services.inbox_eligibility import require_unarchived_inbox
        await require_unarchived_inbox(session, "order", order_id)
        detail = await cls._detail(order)
        source, external_id = _source_identity(order)
        source_terms = extract_commercial_terms(str(detail.get("description") or ""), source="Описание закупки")
        for document in cls._documents(detail):
            if document.get("extracted_text"):
                extracted_terms = extract_commercial_terms(str(document["extracted_text"]), source=str(document.get("name") or "Документ закупки"))
                if document.get("extracted_text_truncated"):
                    for term in extracted_terms:
                        term.issues.append("Текст документа обрезан; проверьте оригинал")
                source_terms.extend(extracted_terms)
        if source_terms:
            store_source_terms(order, source_terms)
        fields_set = payload.model_fields_set
        if order.status == OrderStatus.NEW_LEAD and "workflow_type" not in fields_set:
            raise ValueError("Choose an order scenario before moving the lead to negotiations")
        selected_scenario = None
        if "workflow_type" in fields_set:
            if payload.workflow_type is None:
                raise ValueError("workflow_type is required")
            workflow_type, service_type = resolve_scenario(
                workflow_type=payload.workflow_type, service_type=payload.service_type,
            )
            selected_scenario = (workflow_type, service_type)
        applied: list[str] = []
        evidence = extract_customer_evidence(detail)
        customer = await apply_reviewed_customer(
            session, order=order, scope=scope, payload=payload,
            evidence=evidence, applied=applied,
        )
        if customer is not None:
            if order.customer_id and order.customer_id != customer.id:
                raise ValueError("Order already has another customer")
            order.customer_id = int(customer.id or 0)
            applied.append("customer_id")
            if order.status == OrderStatus.NEW_LEAD:
                order.status = OrderStatus.NEGOTIATION
                applied.append("status")
        source_meta = dict(order.technical_meta or {})
        if selected_scenario is not None:
            workflow_type, service_type = selected_scenario
            if order.workflow_type != workflow_type or source_meta.get("service_type") != service_type:
                applied.append("scenario")
            order.workflow_type = workflow_type
            if service_type is None:
                source_meta.pop("service_type", None)
            else:
                source_meta["service_type"] = service_type
        belzakupki_meta = dict(source_meta.get("belzakupki") or {})
        previous = belzakupki_meta.get("enrichment")
        if not isinstance(previous, dict) or previous.get("source") != source or previous.get("external_id") != external_id:
            previous = {}
        reviewed_objects = (
            payload.objects if "objects" in fields_set and payload.objects is not None
            else [SourceObjectDraft.model_validate(obj) for obj in previous.get("objects") or []]
        )
        prior_branch_ids = [int(value) for value in previous.get("customer_branch_ids") or []]
        if "objects" in fields_set and payload.objects == [] and prior_branch_ids:
            raise ValueError("Existing customer objects must be removed in the customer workspace")
        linked_customer_id = int(customer.id) if customer else order.customer_id
        branch_ids: list[int] = []
        for obj in reviewed_objects:
            address = _text(obj.address, 500)
            if not address or not linked_customer_id:
                continue
            branch = await session.scalar(select(CustomerBranch).where(
                CustomerBranch.customer_id == linked_customer_id,
                CustomerBranch.delivery_address == address,
            ).limit(1))
            if branch is None:
                branch = CustomerBranch(customer_id=linked_customer_id, delivery_address=address)
                session.add(branch)
                await session.flush()
                applied.append("customer_branch")
            branch_ids.append(int(branch.id or 0))
        if not linked_customer_id:
            branch_ids = prior_branch_ids
        if len(branch_ids) == 1 and order.customer_branch_id is None:
            order.customer_branch_id = branch_ids[0]
            applied.append("customer_branch_id")
        enrichment = {
            "source": source, "external_id": external_id,
            "submission": (
                evidence.submission.model_dump() if "submission" in fields_set
                else previous.get("submission") or evidence.submission.model_dump()
            ),
            "contacts": [item.model_dump() for item in evidence.contacts],
            "work_summary": (
                _text(payload.work_summary, 10000) if "work_summary" in fields_set
                else previous.get("work_summary")
            ),
            "equipment_details": (
                _text(payload.equipment_details, 10000) if "equipment_details" in fields_set
                else previous.get("equipment_details")
            ),
            "objects": [obj.model_dump() for obj in reviewed_objects],
            "customer_branch_ids": branch_ids,
            "analysis_source": payload.analysis_source if payload.analysis_source not in {None, "reviewed"} else previous.get("analysis_source"),
            "analyzed_document_ids": (
                payload.analyzed_document_ids if payload.analyzed_document_ids is not None
                else previous.get("analyzed_document_ids") or []
            ),
            "equipment_prefill": previous.get("equipment_prefill"),
        }
        belzakupki_meta["enrichment"] = enrichment
        source_meta["belzakupki"] = belzakupki_meta
        order.technical_meta = source_meta
        flag_modified(order, "technical_meta")
        applied.append("source_enrichment")
        equipment_prefill = None
        if order.workflow_type == "sales_installation" and reviewed_objects and not (
            "objects" in fields_set and payload.objects is None
        ):
            equipment_prefill = await BelzakupkiEquipmentPrefillService.apply(
                session, order=order, scope=scope, source=source,
                external_id=external_id, objects=reviewed_objects,
            )
            # The prefill service also stages provenance; preserve that ledger.
            source_meta = dict(order.technical_meta or {})
            belzakupki_meta = dict(source_meta.get("belzakupki") or {})
            enrichment["equipment_prefill"] = equipment_prefill.model_dump()
            belzakupki_meta["enrichment"] = enrichment
            source_meta["belzakupki"] = belzakupki_meta
            order.technical_meta = source_meta
            flag_modified(order, "technical_meta")
            if equipment_prefill.added:
                applied.append("proposal_equipment")
        available = {str(doc["id"]): doc for doc in cls._documents(detail)}
        attachment_ids: list[int] = []
        if any(document_id not in available for document_id in payload.document_ids):
            raise ValueError("Unknown source document")
        for document_id in dict.fromkeys(payload.document_ids):
            doc = available.get(document_id)
            assert doc is not None
            existing = (await session.execute(
                select(ServiceAttachment)
                .join(OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id)
                .where(OrderAttachmentLink.order_id == order_id, OrderAttachmentLink.archived_at.is_(None), ServiceAttachment.archived_at.is_(None))
            )).scalars().all()
            found = next((item for item in existing if (item.source_meta or {}).get("belzakupki_document_id") == document_id
                          and (item.source_meta or {}).get("external_id") == external_id), None)
            if found:
                attachment_ids.append(int(found.id or 0))
                continue
            content, filename, mime_type = await cls.document(session, order_id=order_id, document_id=document_id, scope=scope)
            if mime_type not in ServiceAttachmentService.SAFE_MIME_TYPES:
                raise ValueError("Unsupported source document type for private attachment")
            if not doc.get("extracted_text"):
                extracted, _ = await extract_missing_document_text(filename=filename, mime_type=mime_type, content=content)
                if extracted:
                    extracted_terms = extract_commercial_terms(extracted, source=filename)
                    if len(extracted) >= 24000:
                        for term in extracted_terms:
                            term.issues.append("Текст документа обрезан; проверьте оригинал")
                    source_terms.extend(extracted_terms)
            attachment = await ServiceAttachmentService.create_and_link_order_attachment(
                session, order_id=order_id, content=content, filename=filename,
                mime_type=mime_type,
                category="document", source="belzakupki",
                created_by=username, tenant_scope=scope, commit=False,
                source_meta={"purpose": "tender_original", "source": source,
                             "external_id": external_id, "belzakupki_document_id": document_id,
                             "source_url": _text(doc.get("source_url"), 2048)},
            )
            attachment_ids.append(int(attachment["id"]))
            applied.append("attachment")
        if source_terms:
            store_source_terms(order, source_terms)
        await session.commit()
        return ManagerOrderSourceApplyResult(
            order_id=order_id, customer_id=order.customer_id,
            attachment_ids=attachment_ids, applied_fields=applied,
            equipment_prefill=equipment_prefill,
        )
