"""Explicit, read-only analysis of a scoped order's selected originals."""

import asyncio
import re
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from core.config import settings
from models import StaffUser
from schemas_connector_tender_review import AnalyzeTenderResult
from schemas_tender_qualification import TenderQualificationSourceMetadata
from services.connector_tender_preview import _public_url, procedure_type, source_inventory, display
from services.belzakupki_import_service import BelzakupkiImportService
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.tender_document_reader import load_tender_document
from services.tender_original_evidence import TenderOriginalEvidence
from services.tender_qualification import load_mvn_tender_profile, qualify_tender_documents


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
    evidence = TenderOriginalEvidence()
    unselected = len(inventory) - len(inputs.document_ids)
    # The synchronous MCP response must arrive before the 60-second ingress timeout.
    extraction_deadline = started + 30
    for key in inputs.document_ids:
        try:
            async with asyncio.timeout_at(extraction_deadline):
                original = await load_tender_document(
                    session, actor.tenant_scope, order_id=order.id, document_id=key, source_reference=inputs.source_reference)
        except TimeoutError:
            evidence.add_timeout(key, inventory[key].filename)
            continue
        evidence.add(original, inventory[key].filename)
    qualification = await qualify_tender_documents(
        evidence.fragments, profile=profile, complete=complete and unselected == 0 and evidence.all_documents_complete,
        provider=inputs.provider, source_metadata=_source_metadata(tender, data, card),
        provider_timeout_seconds=max(0, started + 51 - clock()))
    return AnalyzeTenderResult(
        source=card.source, external_id=card.external_id, order_id=order.id, manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{order.id}",
        documents=evidence.documents, unselected_count=unselected, inventory_complete=complete,
        warnings=warnings, qualification=qualification)
