"""Evidence-only links between repeats of the same procurement URL."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit
from sqlalchemy import String, and_, cast, or_
from sqlmodel import select
from models import Customer, Order
from models.leads_inbox import InboxTriageState
from schemas_leads_inbox import InboxRelatedRequest
from services.tenant_entity_access_service import TenantEntityAccessService


def procurement_urls(order):
    meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
    provider = meta.get('belzakupki')
    provider = provider if isinstance(provider, dict) else {}
    tender = provider.get('tender')
    tender = tender if isinstance(tender, dict) else {}
    candidates = [tender.get('url') or '']
    confirmed = meta.get('inbox_tender')
    if isinstance(confirmed, dict) and confirmed.get('confirmed') is True and confirmed.get('is_tender') is True:
        candidates.append(confirmed.get('source_url') or '')
    for text in (meta.get('email_source_text') or '', order.comment or ''):
        if isinstance(text, str):
            candidates.extend(re.findall(r'https?://[^\s<>"\]\)]+', text))
    result = set()
    for raw in candidates:
        if not isinstance(raw, str):
            continue
        try:
            value = urlsplit(raw.rstrip('.,;'))
            host = (value.hostname or '').lower().removeprefix('www.')
            if host not in {'goszakupki.by', 'icetrade.by'}:
                continue
            if not re.search(r'\d', value.path + value.query):
                continue
            query = urlencode(sorted((k, v) for k, v in parse_qsl(value.query) if not k.lower().startswith('utm_')))
            result.add(host + value.path.rstrip('/') + ('?' + query if query else ''))
        except ValueError:
            continue
    return result


async def add_source_relations(session, *, rows, items, tenant_scope):
    identities = {order.id: procurement_urls(order) for order, *_ in rows}
    all_urls = set().union(*identities.values()) if identities else set()
    if not all_urls:
        return
    # Narrow candidates by the URL's factual procedure identifier. Compare full
    # canonical URLs afterwards; equal organization names are never duplicates.
    tokens = set(token for url in all_urls for token in re.findall(r'\d{4,}', url))
    if not tokens:
        return
    conditions = [or_(Order.comment.contains(token), cast(Order.technical_meta, String).contains(token)) for token in tokens]
    stmt = (select(Order, InboxTriageState).outerjoin(Customer, Customer.id == Order.customer_id)
        .outerjoin(InboxTriageState, and_(InboxTriageState.entity_kind == 'order', InboxTriageState.entity_id == Order.id,
            InboxTriageState.tenant_id == Order.tenant_id, InboxTriageState.storefront_id == Order.storefront_id))
        .where(TenantEntityAccessService.order_clause(tenant_scope), TenantEntityAccessService.order_customer_clause(tenant_scope), or_(*conditions))
        .order_by(Order.created_at.desc()).limit(200))
    candidates = (await session.execute(stmt)).all()
    for item in items:
        refs = identities.get(item.id, set())
        if not refs:
            continue
        related = []
        for other, state in candidates:
            shared = refs & procurement_urls(other)
            if other.id == item.id or not shared:
                continue
            archive = bool(state and state.archived_at)
            related.append(InboxRelatedRequest(order_id=other.id, title=other.title,
                outcome=state.outcome if archive else ('legacy_lost' if other.status == 'closed' and other.closing_result == 'lost' else None),
                reason=state.reason if archive else None,
                note=state.note if archive else other.reject_reason,
                url='https://' + sorted(shared)[0]))
            if len(related) == 3:
                break
        item.related_requests = related
