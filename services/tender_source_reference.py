"""Resolve native source references recorded by intake on an already scoped order."""

from dataclasses import dataclass
from typing import Any

import httpx

from models import Order
from services.belzakupki_canonical_identity import canonical_procurement_url, original_native_identities
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService, _source_identity
from services.belzakupki_import_service import BelzakupkiImportService


@dataclass(frozen=True)
class TenderReviewSource:
    detail: dict[str, Any]
    document_identity: tuple[str, str]
    documents_source_url: str | None = None
    warning: str | None = None
    document_reference: str | None = None


def resolve_source_reference(order, reference):
    primary = _source_identity(order)
    if reference is None or reference == BelzakupkiImportService._order_fingerprint(
        source=primary[0], external_id=primary[1]
    ):
        return primary
    refs = ((order.technical_meta or {}).get("belzakupki") or {}).get("source_references")
    entry = refs.get(reference) if isinstance(refs, dict) else None
    if isinstance(entry, dict) and not entry.get("claimed_canonical_url"):
        source, external_id = entry.get("source"), entry.get("external_id")
        if (isinstance(source, str) and isinstance(external_id, str)
                and source and external_id and reference == BelzakupkiImportService._order_fingerprint(
                    source=source, external_id=external_id)):
            return source, external_id
    raise LookupError("Source reference not found on this order")


async def detail_for_reference(order, reference):
    source, external_id = resolve_source_reference(order, reference)
    if (source, external_id) == _source_identity(order):
        return await BelzakupkiEnrichmentService._detail(order)
    data = (await BelzakupkiEnrichmentService._fetch(source, external_id)).json()
    if not isinstance(data, dict) or data.get("source") != source or str(data.get("external_id")) != external_id:
        raise ValueError("Belzakupki detail identity mismatch")
    return data


def goszakupki_document_reference(order: Order) -> tuple[str, str] | None:
    """Find the recorded native Goszakupki publication for a GIAS order."""
    if _source_identity(order)[0] not in {"gias_by", "gias"}:
        return None
    provider = (order.technical_meta or {}).get("belzakupki") or {}
    tender = provider.get("tender") or {}
    url = canonical_procurement_url(provider.get("canonical_url"))
    if not url or not url.startswith("https://goszakupki.by/") or tender.get("claimed_canonical_url"):
        return None
    refs = provider.get("source_references")
    if not isinstance(refs, dict):
        return None
    for source, external_id in original_native_identities(url):
        reference = BelzakupkiImportService._order_fingerprint(source=source, external_id=external_id)
        entry = refs.get(reference)
        if not isinstance(entry, dict) or canonical_procurement_url(entry.get("url")) != url:
            continue
        try:
            if resolve_source_reference(order, reference) == (source, external_id):
                return reference, url
        except LookupError:
            continue
    return None


async def source_for_manager_review(order: Order) -> TenderReviewSource:
    primary = await BelzakupkiEnrichmentService._detail(order)
    identity = _source_identity(order)
    mirror = None if BelzakupkiEnrichmentService._documents(primary) else goszakupki_document_reference(order)
    if mirror is None:
        return TenderReviewSource(primary, identity)
    reference, url = mirror
    try:
        detail = await detail_for_reference(order, reference)
    except (httpx.HTTPError, RuntimeError, ValueError):
        return TenderReviewSource(primary, identity, warning="Не удалось получить вложения с Госзакупок.")
    if canonical_procurement_url(detail.get("source_url")) != url:
        return TenderReviewSource(primary, identity, warning="Не удалось сверить публикацию Госзакупок.")
    documents = BelzakupkiEnrichmentService._documents(detail)
    if not documents:
        return TenderReviewSource(primary, identity)
    return TenderReviewSource(
        {**primary, "documents": documents}, resolve_source_reference(order, reference), documents_source_url=url,
        document_reference=reference,
    )


def tender_snapshot_for_reference(order, identity):
    meta = (order.technical_meta or {}).get("belzakupki") or {}
    if identity == _source_identity(order):
        return meta.get("tender") or {}
    matches = [item for item in (meta.get("matches") or {}).values() if isinstance(item, dict)
               and isinstance(item.get("tender"), dict)
               and (item["tender"].get("source"), item["tender"].get("external_id")) == identity]
    latest = max(matches, key=lambda item: str(item.get("updated_at") or ""), default={})
    return latest.get("tender") or {}
