"""Read verified public inventories through the collector's market scope."""

import httpx

from models import TenderMarketPublication
from services.belzakupki_canonical_identity import canonical_procurement_url, original_native_identities
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.tender_source_reference import TenderReviewSource


async def _detail(identity: tuple[str, str]) -> dict:
    data = (await BelzakupkiEnrichmentService._fetch(*identity, market=True)).json()
    if not isinstance(data, dict) or (data.get("source"), str(data.get("external_id"))) != identity:
        raise ValueError("Market publication identity mismatch")
    return data


async def market_original_inventory(publication: TenderMarketPublication) -> TenderReviewSource:
    identity = (publication.source, publication.external_id)
    primary = await _detail(identity)
    url = primary.get("source_url")
    native_url = canonical_procurement_url(publication.source_url)
    if url != publication.source_url and (native_url is None or canonical_procurement_url(url) != native_url):
        raise ValueError("Market publication URL changed")

    original = canonical_procurement_url(publication.canonical_url)
    documents_url = primary.get("documents_source_url")
    if documents_url and documents_url != url:
        if publication.source != "gias_by" or original is None or canonical_procurement_url(documents_url) != original:
            raise ValueError("Market document inventory reference mismatch")
        return TenderReviewSource(primary, identity, documents_source_url=original)
    if (BelzakupkiEnrichmentService._documents(primary) or publication.source != "gias_by"
            or original is None or not original.startswith("https://goszakupki.by/")):
        return TenderReviewSource(primary, identity, documents_source_url=publication.source_url)

    original_identity = original_native_identities(original)[0]
    try:
        mirror = await _detail(original_identity)
    except httpx.HTTPStatusError as error:
        if error.response.status_code != 404:
            raise
        return TenderReviewSource(primary, identity, warning="Перечень оригиналов Госзакупок пока недоступен.")
    if canonical_procurement_url(mirror.get("source_url")) != original:
        raise ValueError("Goszakupki mirror did not match the verified publication")
    return TenderReviewSource(mirror, original_identity, documents_source_url=original)
