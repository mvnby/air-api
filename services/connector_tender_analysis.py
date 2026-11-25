"""Explicit, read-only analysis of a scoped order's selected originals."""

import asyncio
import re
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from core.config import settings
from models import StaffUser
from schemas_connector_tender_review import AnalyzedTenderFile, AnalyzeTenderResult
from schemas_tender_qualification import TenderDocumentFragment, TenderQualificationSourceMetadata
from services.belzakupki_source_analysis import MAX_TENDER_TEXT_CHARS
from services.connector_tender_preview import _public_url, procedure_type, source_inventory, display
from services.belzakupki_import_service import BelzakupkiImportService
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.tender_document_reader import load_tender_document
from services.tender_qualification import MAX_FRAGMENTS, load_mvn_tender_profile, qualify_tender_documents


async def require_analysis_access(session, actor):
    # Manager source-analyze requires the durable platform owner in the system company.
    if actor.tenant_scope.is_system and not actor.tenant_scope.demo_read_only:
        state = await LegacyOwnerAuthGuard.state(session)
        user = await session.get(StaffUser, actor.staff_user_id, populate_existing=True)
        if user is not None and await LegacyOwnerManagedIdentityService.exact_bound_staff_identity_allowed(
            session, state=state, user=user
        ):
            return
    raise PermissionError("Platform owner in the system company required")


def _source_metadata(tender, data, card):
    raw_budget = data.get("estimated_value")
    if raw_budget is None:
        raw_budget = tender.get("estimated_value")
    raw_amount = display(raw_budget, 80) or ""
    budget = currency = None
    match = re.fullmatch(r"([0-9]+(?:[\s\u00a0][0-9]{3})*(?:[,.][0-9]{1,2})?)\s*([A-Za-z]{3})?", raw_amount)
    if match:
        currency = match[2] or display(data.get("currency") or tender.get("currency"), 12)
        if currency and not re.fullmatch(r"[A-Za-z]{3}", currency):
            currency = None
        try:
            candidate = Decimal("".join(match[1].split()).replace(",", "."))
            if candidate < 10**15:
                budget = candidate
        except InvalidOperation:
            pass
    kind = data.get("deadline_kind") or tender.get("deadline_kind")
    deadline = BelzakupkiImportService._parse_datetime(data.get("deadline_at") or tender.get("deadline_at"))
    # Reviewed/structured work sites differ from the customer's registered office.
    addresses = list(dict.fromkeys(obj.address for obj in card.objects if 2 <= len(obj.address) <= 700))
    return TenderQualificationSourceMetadata(
        procedure_type=procedure_type(_public_url(data, tender)), estimated_budget=budget, budget_currency=currency,
        submission_deadline=deadline.astimezone(ZoneInfo("Europe/Minsk")) if deadline and kind == "submission" else None,
        submission_method=card.submission.method if card.submission.method in {"email", "platform"} else None,
        execution_addresses=addresses if len(addresses) <= 20 else [])


async def analyze_tender_documents(session, actor, inputs):
    clock = asyncio.get_running_loop().time
    started = clock()
    await require_analysis_access(session, actor)
    order, tender, data, card, inventory, complete, warnings = await source_inventory(
        session, actor.tenant_scope, inputs.order_id, inputs.source_reference)
    if any(key not in inventory for key in inputs.document_ids):
        raise HTTPException(400, "Выбранный оригинал отсутствует в текущем перечне. Обновите карточку источника.")
    profile = inputs.profile
    if inputs.profile_name == "mvn_vitebsk":
        profile = await asyncio.to_thread(load_mvn_tender_profile)
    documents = []
    fragments = []
    used_chars = 0
    unselected = len(inventory) - len(inputs.document_ids)
    covered = complete and unselected == 0
    # The synchronous MCP response must arrive before the 60-second ingress timeout.
    extraction_deadline = started + 30
    for key in inputs.document_ids:
        try:
            async with asyncio.timeout_at(extraction_deadline):
                original = await load_tender_document(
                    session, actor.tenant_scope, order_id=order.id, document_id=key, source_reference=inputs.source_reference)
        except TimeoutError:
            documents.append(AnalyzedTenderFile(
                document_id=key, filename=inventory[key].filename, status="timeout",
                diagnostics=["Истекло время чтения выбранных оригиналов. Проверьте этот файл отдельно."]))
            covered = False
            continue
        file = AnalyzedTenderFile(
            document_id=key, filename=original.filename or inventory[key].filename, status=original.status,
            sha256=original.sha256, diagnostics=original.diagnostics, origin=original.origin)
        documents.append(file)
        if original.status != "complete":
            covered = False
        if (used_chars + original.total_chars > MAX_TENDER_TEXT_CHARS
                or len(fragments) + len(original.fragments) > MAX_FRAGMENTS):
            file.status = "over_analysis_limit"
            file.diagnostics.append("Файл не вошёл в лимит анализа. Выберите его отдельно или прочитайте постранично.")
            covered = False
            continue
        used_chars += original.total_chars
        for part in original.fragments:
            location = f"стр. {part.page}, фрагмент {part.fragment}" if part.page else f"фрагмент {part.fragment}"
            fragments.append(TenderDocumentFragment(
                document_id=key, filename=file.filename, text=part.text, location=location,
                document_sha256=original.sha256, partial=original.status != "complete"))
    qualification = await qualify_tender_documents(
        fragments, profile=profile, complete=covered, provider=inputs.provider, source_metadata=_source_metadata(tender, data, card),
        provider_timeout_seconds=max(0, started + 51 - clock()))
    return AnalyzeTenderResult(
        source=card.source, external_id=card.external_id, order_id=order.id, manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{order.id}",
        documents=documents, unselected_count=unselected, inventory_complete=complete,
        warnings=warnings, qualification=qualification)
