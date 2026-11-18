"""Scoped, read-only view of imported tender inbox cards."""

from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import func, not_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload
from sqlmodel import select

from core.command_actor import CommandActor
from core.config import settings
from models import Customer, LeadSource, Order, OrderStatus
from models.leads_inbox import InboxReadState, InboxTriageState
from schemas_connector_tender_inbox import TenderInboxInput, TenderInboxItem, TenderInboxResult, TenderSourceReference
from services.belzakupki_canonical_identity import canonical_procurement_url, canonical_tender_url, original_native_identities
from services.belzakupki_import_service import BelzakupkiImportService
from services.leads_inbox_projection import LeadsInboxProjection
from services.leads_inbox_service import LeadsInboxService


def _object(value):
    return value if isinstance(value, dict) else {}


def _text(value, size):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    return " ".join(str(value).split())[:size] or None


def _date(value):
    return LeadsInboxService.deadline_fields(value)


def _verified_canonical(provider_url, tender):
    return canonical_procurement_url(provider_url) or canonical_tender_url(tender)


def _matches_procedure(canonical, procedure):
    if canonical is None:
        return False
    if procedure.startswith("https://"):
        return canonical == procedure
    parsed = urlsplit(canonical)
    return parsed.hostname == "goszakupki.by" and parsed.path.rsplit("/", 1)[-1] == procedure[3:]


def _public_source_url(value):
    if (not isinstance(value, str) or len(value) > 2048 or "\\" in value
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme in {"http", "https"} and parts.hostname and parts.username is None and parts.password is None:
            _ = parts.port
            return canonical_procurement_url(value) or parts._replace(query="", fragment="").geturl()
    except ValueError:
        return None
    return None


def _source_references(provider, tender):
    entries = _object(provider.get("source_references"))
    aliases = {}
    for entry in (tender, *(entries[key] for key in sorted(entries))):
        reference = _object(entry)
        source_code = _text(reference.get("source"), 100)
        external_id = _text(reference.get("external_id"), 300)
        if source_code and external_id:
            identity = (source_code.casefold(), external_id)
            source_url = _public_source_url(reference.get("url"))
            claimed_canonical = canonical_procurement_url(reference.get("claimed_canonical_url"))
            conflict = bool(claimed_canonical and claimed_canonical != canonical_tender_url(reference))
            recorded = aliases.get(identity)
            if recorded:
                recorded.source_url = recorded.source_url or source_url
                recorded.canonical_conflict = recorded.canonical_conflict or conflict
            else:
                aliases[identity] = TenderSourceReference(
                    source_reference=BelzakupkiImportService._order_fingerprint(
                        source=source_code, external_id=external_id,
                    ),
                    source_code=source_code, external_id=external_id, source_url=source_url,
                    canonical_conflict=conflict,
                )
    return list(aliases.values())[:10], len(aliases) > 10


def _earlier_source_deadlines(provider, tender, current_deadline):
    current_seen = _date(provider.get("tender_updated_at"))
    native = (tender.get("source"), tender.get("external_id"))
    if current_seen is None or not all(native) or tender.get("claimed_canonical_url"):
        return None, None
    canonical = canonical_tender_url(tender)
    dates = set()

    def collect(snapshot, observed_at):
        observed = _date(observed_at)
        deadline = LeadsInboxService.deadline_fields(snapshot.get("deadline_at"), snapshot.get("deadline_kind"))
        if (observed is not None and observed < current_seen and deadline is not None
                and (snapshot.get("source"), snapshot.get("external_id")) == native
                and canonical_tender_url(snapshot) == canonical
                and not snapshot.get("claimed_canonical_url")):
            dates.add((observed, deadline))

    history = provider.get("source_deadline_history")
    if isinstance(history, list):
        for value in history:
            snapshot = _object(value)
            collect(snapshot, snapshot.get("observed_at"))
    for value in _object(provider.get("matches")).values():
        match = _object(value)
        collect(_object(match.get("tender")), match.get("updated_at"))
    ordered = sorted(dates)
    previous = [deadline for _, deadline in ordered if deadline != current_deadline]
    return (ordered[0][1] if ordered else None), (previous[-1] if previous else None)


def _is_archived(order, state):
    return bool((order.status == OrderStatus.NEW_LEAD and order.linked_order_id) or (state and state.archived_at)
                or (order.status == OrderStatus.CLOSED and order.closing_result == "lost"))


def _item(row):
    order, state, read, customer_name = row[:4]
    metadata = _object(order.technical_meta)
    provider = _object(metadata.get("belzakupki"))
    tender = _object(provider.get("tender"))
    canonical = _verified_canonical(provider.get("canonical_url"), tender)
    originals = original_native_identities(canonical) if canonical else []
    canonical_external_id = originals[0][1] if originals else None
    canonical_parts = urlsplit(canonical) if canonical else None
    procedure_kind = _text(tender.get("procedure_kind"), 80)
    if canonical_parts and canonical_parts.hostname == "goszakupki.by":
        procedure_kind = canonical_parts.path.split("/")[1]
    references, references_truncated = _source_references(provider, tender)
    source_deadline = _date(tender.get("deadline_at"))
    current_submission = LeadsInboxService.deadline_fields(tender.get("deadline_at"), tender.get("deadline_kind"))
    original_deadline, previous_deadline = _earlier_source_deadlines(provider, tender, current_submission)
    effective_deadline = LeadsInboxService.root_deadline(row)
    basis = None
    if effective_deadline is not None:
        if row.workflow_deadline_manual:
            basis = "workflow"
        elif row.manual_confirmed is True and row.manual_is_tender is True:
            basis = "confirmed_tender"
        else:
            basis = "submission"
    archived = _is_archived(order, state)
    archive_outcome = "linked" if order.linked_order_id else state.outcome if state and state.archived_at else None
    if archived and archive_outcome is None:
        archive_outcome = "legacy_lost" if order.status == OrderStatus.CLOSED and order.closing_result == "lost" else None
    return TenderInboxItem(
        order_id=order.id, manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{order.id}",
        title=_text(tender.get("title") or order.title, 400), status=order.status,
        customer_name=_text(customer_name or tender.get("customer_name"), 300), created_at=order.created_at,
        unread=not bool(read and read.is_read), archived=archived, archive_outcome=archive_outcome,
        region=_text(tender.get("region"), 150), location=_text(order.delivery_address or tender.get("location"), 300),
        estimated_budget=LeadsInboxProjection.number(tender.get("estimated_value")),
        quantity=LeadsInboxProjection.number(tender.get("quantity")),
        budget_currency=_text(tender.get("currency"), 12),
        source_code=_text(tender.get("source") or provider.get("source"), 100),
        external_id=_text(tender.get("external_id") or provider.get("external_tender_id"), 300),
        provider_tender_id=_text(tender.get("id"), 50), source_url=_public_source_url(tender.get("url")),
        canonical_url=canonical, canonical_external_id=canonical_external_id, source_references=references,
        source_references_truncated=references_truncated, canonical_conflict=bool(provider.get("canonical_conflicts")),
        procedure_kind=procedure_kind,
        participation_method=_text(tender.get("participation_method"), 150),
        published_at=_date(tender.get("published_at")), source_updated_at=_date(provider.get("tender_updated_at")),
        deadline_at=effective_deadline, deadline_basis=basis, source_deadline_at=source_deadline,
        source_deadline_kind=(_text(tender.get("deadline_kind"), 40) or "submission") if source_deadline else None,
        original_source_deadline_at=original_deadline, previous_source_deadline_at=previous_deadline,
    )


async def list_tender_inbox(session: AsyncSession, actor: CommandActor, inputs: TenderInboxInput) -> TenderInboxResult:
    as_of = datetime.now(timezone.utc)
    root = LeadsInboxService.base_statement(username=actor.username, tenant_scope=actor.tenant_scope).where(
        Order.lead_source == LeadSource.BELZAKUPKI,
    )
    if inputs.archived is True:
        root = root.where(LeadsInboxService.scope_clause("archive"))
    elif inputs.archived is False:
        if inputs.status is None or inputs.status == OrderStatus.NEW_LEAD:
            root = root.where(LeadsInboxService.scope_clause("active"))
        else:
            root = root.where(not_(func.coalesce(LeadsInboxService.scope_clause("archive"), False)))
    if inputs.status is not None:
        root = root.where(Order.status == inputs.status)
    if inputs.unread is not None:
        root = root.where(LeadsInboxService.unread_clause() if inputs.unread else InboxReadState.is_read.is_(True))
    provider = Order.technical_meta["belzakupki"]
    tender = provider["tender"]
    if inputs.region:
        region = inputs.region.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        pattern = f"%{region}%"
        root = root.where(or_(tender["region"].as_string().ilike(pattern, escape="!"),
                              tender["location"].as_string().ilike(pattern, escape="!"),
                              Order.delivery_address.ilike(pattern, escape="!")))

    statement = root.add_columns(Customer.name, *LeadsInboxService.deadline_columns()).options(noload("*"))
    newest = (Order.created_at.desc(), Order.id.desc())
    offset = (inputs.page - 1) * inputs.limit
    deadline_from = max(as_of, inputs.deadline_from or as_of) if inputs.current_only else inputs.deadline_from
    deadline_to = inputs.deadline_to
    needs_deadline = inputs.sort == "deadline" or deadline_from is not None or deadline_to is not None
    if needs_deadline or inputs.procedure:
        # Parse narrow roots before paging as Manager does. A legacy date with invalid JSON
        # text or no timezone cannot break filtering for the entire storefront.
        columns = [Order.id]
        if needs_deadline:
            columns.extend(LeadsInboxService.deadline_columns())
        if inputs.procedure:
            columns.extend([
                provider["canonical_url"].as_string().label("canonical_url"),
                tender["canonical_url"].as_string().label("tender_canonical_url"),
                tender["source"].as_string().label("source"),
                tender["url"].as_string().label("source_url"),
            ])
        filtered = []
        for row in (await session.execute(root.with_only_columns(*columns).order_by(*newest))).all():
            deadline = LeadsInboxService.root_deadline(row) if needs_deadline else None
            if deadline_from is not None and (deadline is None or deadline < deadline_from):
                continue
            if deadline_to is not None and (deadline is None or deadline > deadline_to):
                continue
            if inputs.procedure:
                canonical = _verified_canonical(row.canonical_url, {
                    "canonical_url": row.tender_canonical_url, "source": row.source, "url": row.source_url,
                })
                if not _matches_procedure(canonical, inputs.procedure):
                    continue
            filtered.append((row.id, deadline))
        if inputs.sort == "deadline":
            far_future = datetime.max.replace(tzinfo=timezone.utc)
            filtered.sort(key=lambda pair: pair[1] or far_future)
        total = len(filtered)
        ids = [order_id for order_id, _ in filtered[offset:offset + inputs.limit]]
        index = {row[0].id: row for row in (await session.execute(statement.where(Order.id.in_(ids)))).all()} if ids else {}
        rows = [index[order_id] for order_id in ids if order_id in index]
    else:
        total = await session.scalar(select(func.count()).select_from(root.with_only_columns(Order.id).subquery()))
        rows = (await session.execute(statement.order_by(*newest).offset(offset).limit(inputs.limit))).all()
    return TenderInboxResult(
        items=[_item(row) for row in rows], page=inputs.page, limit=inputs.limit,
        total=total, has_more=offset + inputs.limit < total, as_of=as_of,
    )
