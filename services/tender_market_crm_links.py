"""Connect a visible market publication to a verified CRM record in the active storefront."""

from collections.abc import Sequence

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from crud.tender_market import TenderMarketDAO
from models import TenderMarketPublication
from models.tenancy import TenantScope
from schemas_tender_market import TenderMarketCrmLink
from services.belzakupki_canonical_identity import (
    canonical_procurement_url, canonical_tender_url, original_native_identities,
    procurement_canonical_fingerprint, procurement_native_fingerprint,
)
from services.leads_inbox_service import LeadsInboxService


async def market_crm_links(
    session: AsyncSession, scope: TenantScope, publications: Sequence[TenderMarketPublication],
) -> dict[int, TenderMarketCrmLink]:
    candidates = {}
    for publication in publications:
        canonical = canonical_tender_url({
            "source": publication.source, "url": publication.source_url, "canonical_url": publication.canonical_url,
        })
        native = procurement_native_fingerprint(source=publication.source, external_id=publication.external_id)
        keys = {native}
        if canonical:
            keys.add(procurement_canonical_fingerprint(canonical))
            keys.update(procurement_native_fingerprint(source=source, external_id=external_id)
                        for source, external_id in original_native_identities(canonical))
        candidates[publication.id] = (canonical, publication.source_url, keys)
    if not candidates:
        return {}
    inbox = or_(LeadsInboxService.scope_clause("active"), LeadsInboxService.scope_clause("archive"))
    rows = await TenderMarketDAO.crm_references(
        session, scope, set().union(*(keys for _, _, keys in candidates.values())), inbox,
    )
    by_key = {row.source_fingerprint: row for row in rows}
    links = {}
    for publication_id, (canonical, source_url, keys) in candidates.items():
        matches = []
        for key in keys:
            row = by_key.get(key)
            if row is None:
                continue
            if row.canonical_conflicts or row.identity_conflicts:
                # An operator must resolve the conflict before we select a CRM destination.
                matches = []
                break
            established = canonical_procurement_url(row.canonical_url) or canonical_tender_url({
                "source": row.native_source, "url": row.native_url, "canonical_url": row.native_canonical_url,
            })
            if canonical and established != canonical:
                continue
            if not canonical and row.native_url != source_url:
                continue
            matches.append(row)
        if len(matches) == 1:
            row = matches[0]
            links[publication_id] = TenderMarketCrmLink(kind="incoming" if row.in_inbox else "order", id=row.id)
    return links
