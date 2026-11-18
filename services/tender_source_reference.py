"""Resolve native source references recorded by intake on an already scoped order."""

from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService, _source_identity
from services.belzakupki_import_service import BelzakupkiImportService


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


def tender_snapshot_for_reference(order, identity):
    meta = (order.technical_meta or {}).get("belzakupki") or {}
    if identity == _source_identity(order):
        return meta.get("tender") or {}
    matches = [item for item in (meta.get("matches") or {}).values() if isinstance(item, dict)
               and isinstance(item.get("tender"), dict)
               and (item["tender"].get("source"), item["tender"].get("external_id")) == identity]
    latest = max(matches, key=lambda item: str(item.get("updated_at") or ""), default={})
    return latest.get("tender") or {}
