"""Continue a consumer document from its saved facts, never today's CRM defaults."""

from copy import deepcopy
from dataclasses import asdict, replace

from .consumer_context import build_consumer_document_context
from .draft_parameters import json_terms, read_draft_parameters, saved_total
from .errors import ManagedDocumentConflictError
from .installation_context import staged_template_is_supported
from modules.documents.domain import ConsumerDocumentTerms


async def consumer_replacement_snapshot(session, *, tenant_scope, source, selection, version):
    if source.legal_entity_id != selection.legal_entity_id:
        raise ManagedDocumentConflictError("Для другой стороны договора создайте отдельный документ")
    if selection.proposal_id is not None and selection.proposal_id != source.proposal_id:
        raise ManagedDocumentConflictError("Новая редакция наследует состав исходного документа; для другого предложения создайте отдельный документ")
    snapshot = deepcopy(source.render_snapshot)
    saved = read_draft_parameters(source)
    data = saved["consumer_terms"] or {}
    changed_terms = False
    if selection.consumer_terms is not None:
        incoming = asdict(selection.consumer_terms)
        if selection.consumer_terms_fields is not None:
            incoming = {key: value for key, value in incoming.items() if key in selection.consumer_terms_fields}
        else:
            defaults = asdict(ConsumerDocumentTerms())
            incoming = {key: value for key, value in incoming.items() if value != defaults[key]}
        changed_terms = any(data.get(key) != value for key, value in incoming.items())
        data = {**data, **incoming}
    terms = ConsumerDocumentTerms(**data)
    # A new explicit physical selection refreshes identity. The same saved ID never does.
    if terms.equipment_id is not None and terms.equipment_id != (saved["consumer_terms"] or {}).get("equipment_id"):
        from .consumer_equipment import resolve_linked_equipment
        from services.tenant_entity_access_service import TenantEntityAccessService
        order = await TenantEntityAccessService.get_order(session, source.order_id, tenant_scope=tenant_scope)
        resolved = await resolve_linked_equipment(session, tenant_scope=tenant_scope, order=order, terms=terms)
        terms = replace(resolved, **{name: data[name] for name in
            ("equipment_brand", "equipment_model", "equipment_serial") if name in incoming})
    if terms.installation_two_stages and not staged_template_is_supported(version.placeholder_schema or {}):
        raise ManagedDocumentConflictError("Выбранная версия шаблона не поддерживает монтаж в два этапа")
    values = snapshot["values"]
    if changed_terms:
        context = build_consumer_document_context(document_type=source.doc_type, terms=terms,
            seller_requisites={"offer_url": values.get("offer.url"), "offer_version": values.get("offer.version"),
                "offer_published_on": values.get("offer.published_on")}, total_amount=saved_total(snapshot))
        values.update(context.values)
        snapshot["conditions"].update(context.conditions)
    for key in ("internal_reference", "official_series", "official_number", "official_full_number", "act_sequence_number"):
        values[f"document.{key}"] = ""
    values["document.issued_on"] = selection.issue_date.strftime("%d.%m.%Y")
    if selection.issue_city is not None:
        values["document.issue_city"] = selection.issue_city
    snapshot["meta"]["issue_city"] = values.get("document.issue_city", "")
    snapshot["meta"].setdefault("draft_parameters", {})["consumer_terms"] = json_terms(terms)
    return snapshot
