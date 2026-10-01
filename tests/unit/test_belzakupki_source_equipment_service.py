from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from models import LeadSource, Order, OrderAttachmentLink, OrderProductLink, OrderProposal, Product, ServiceAttachment
from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import ManagerOrderSourceEquipmentAdd, SourceEquipmentDraft, SourceObjectDraft
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.belzakupki_equipment_prefill import BelzakupkiEquipmentPrefillService, ExactCatalogCandidate
from services.belzakupki_installation_facts import installation_facts
from services.belzakupki_source_equipment_service import BelzakupkiSourceEquipmentService, SourceEquipmentPreviewChangedError


def _setup(monkeypatch):
    objects = [SourceObjectDraft(address="", equipment=[
        SourceEquipmentDraft(brand="MDV", model="AB-12/CD-12", quantity=9),
        SourceEquipmentDraft(brand="MDV", model="AB-09/CD-09", quantity=5),
    ])]
    order = Order(id=461, tenant_id=1, storefront_id=1, lead_source=LeadSource.BELZAKUPKI, technical_meta={
        "belzakupki": {"source": "goszakupki_by", "external_tender_id": "T-1", "tender": {"title": "Поставка + монтаж", "source_url": "https://source.test/T-1"},
            "enrichment": {"source": "goszakupki_by", "external_id": "T-1", "objects": [obj.model_dump() for obj in objects]}},
    })
    proposal = OrderProposal(id=465, order_id=461, is_selected=True, status="draft")
    manual = OrderProductLink(id=551, order_id=461, proposal_id=465, product_id=107, quantity=5, price=1234, cost=1000)
    lines = [manual]
    candidates = [ExactCatalogCandidate(
        product=Product(id=pid, title=f"MDV AB-{size}/CD-{size}", slug=f"mdv-{size}", price=9999),
        brand="MDV", available_quantity=20, price=price, cost=cost,
    ) for pid, size, price, cost in ((108, "12", 2990, 1691), (107, "09", 2690, 1494))]
    session = AsyncMock()
    async def execute(statement):
        entity = statement.column_descriptions[0]["entity"]
        result = MagicMock()
        result.scalars.return_value.all.return_value = [proposal] if entity is OrderProposal else list(lines)
        return result
    session.execute.side_effect = execute
    session.scalar.return_value = proposal
    def add(item):
        if isinstance(item, OrderProductLink):
            item.id = 1000 + len(lines)
            lines.append(item)
    session.add = MagicMock(side_effect=add)
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEquipmentPrefillService, "candidates", AsyncMock(return_value=candidates))
    monkeypatch.setattr("services.belzakupki_equipment_prefill.OrderService._refresh_order_financials", AsyncMock())
    return session, order, proposal, lines, candidates


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.mark.asyncio
async def test_visible_preview_add_preserves_manual_line_and_restore_requires_new_intent(monkeypatch):
    session, order, _, lines, _ = _setup(monkeypatch)
    preview = await BelzakupkiSourceEquipmentService.preview(session, order_id=461, scope=SCOPE, proposal_id=465)
    session.commit.assert_not_awaited()
    assert [(item.product_id, item.quantity, item.reason, item.existing_quantity) for item in preview.items] == [
        (108, 9, "ready", 0), (107, 5, "existing_line", 5),
    ]
    payload = ManagerOrderSourceEquipmentAdd(proposal_id=465, command_id="add-1", preview_fingerprint=preview.preview_fingerprint, product_ids=[108])
    report = await BelzakupkiSourceEquipmentService.add(session, order_id=461, scope=SCOPE, payload=payload)
    assert report.added[0].product_id == 108
    assert [(line.product_id, line.quantity, line.price) for line in lines] == [(107, 5, 1234), (108, 9, 2990)]
    assert BelzakupkiEnrichmentService._order.await_args.kwargs["lock"] is True
    assert order.technical_meta["belzakupki"]["equipment_prefill_commands"]
    # A retry of the same command succeeds without adding a duplicate.
    await BelzakupkiSourceEquipmentService.add(session, order_id=461, scope=SCOPE, payload=payload)
    assert len(lines) == 2
    lines.pop()
    await BelzakupkiSourceEquipmentService.add(session, order_id=461, scope=SCOPE, payload=payload)
    assert len(lines) == 1
    removed = await BelzakupkiSourceEquipmentService.preview(session, order_id=461, scope=SCOPE, proposal_id=465)
    assert removed.items[0].reason == "previously_removed"
    assert removed.items[0].can_restore and not removed.items[0].can_add
    restore = ManagerOrderSourceEquipmentAdd(proposal_id=465, command_id="restore-1", preview_fingerprint=removed.preview_fingerprint,
                                             product_ids=[108], restore_removed_product_ids=[108])
    await BelzakupkiSourceEquipmentService.add(session, order_id=461, scope=SCOPE, payload=restore)
    assert len(lines) == 2
    assert next(iter(order.technical_meta["belzakupki"]["equipment_prefill_history"].values()))["action"] == "restored"
    lines.pop()
    await BelzakupkiSourceEquipmentService.add(session, order_id=461, scope=SCOPE, payload=restore)
    assert len(lines) == 1


@pytest.mark.asyncio
async def test_removed_product_cannot_be_added_without_restore_opt_in(monkeypatch):
    session, order, _, lines, _ = _setup(monkeypatch)
    fingerprint = BelzakupkiEquipmentPrefillService._fingerprint("goszakupki_by", "T-1", 108)
    order.technical_meta["belzakupki"]["equipment_prefill_history"] = {fingerprint: {"line_id": 1}}
    preview = await BelzakupkiSourceEquipmentService.preview(session, order_id=461, scope=SCOPE, proposal_id=465)
    payload = ManagerOrderSourceEquipmentAdd(proposal_id=465, command_id="not-restore", preview_fingerprint=preview.preview_fingerprint, product_ids=[108])
    with pytest.raises(ValueError, match="недоступны"):
        await BelzakupkiSourceEquipmentService.add(session, order_id=461, scope=SCOPE, payload=payload)
    assert len(lines) == 1


@pytest.mark.asyncio
async def test_new_draft_labels_prior_addition_separately_and_requires_explicit_opt_in(monkeypatch):
    session, order, proposal, lines, _ = _setup(monkeypatch)
    fingerprint = BelzakupkiEquipmentPrefillService._fingerprint("goszakupki_by", "T-1", 108)
    order.technical_meta["belzakupki"]["equipment_prefill_history"] = {fingerprint: {"proposal_id": 465, "line_id": 600}}
    proposal.id = 466
    # The existing manager row stays in the other proposal, outside this query.
    old_lines = lines.copy()
    lines.clear()
    preview = await BelzakupkiSourceEquipmentService.preview(session, order_id=461, scope=SCOPE, proposal_id=466)
    assert preview.items[0].reason == "previously_added_elsewhere"
    assert preview.items[0].can_restore and not preview.items[0].can_add
    payload = ManagerOrderSourceEquipmentAdd(proposal_id=466, command_id="new-draft", preview_fingerprint=preview.preview_fingerprint,
                                             product_ids=[108], restore_removed_product_ids=[108])
    await BelzakupkiSourceEquipmentService.add(session, order_id=461, scope=SCOPE, payload=payload)
    assert [(line.proposal_id, line.product_id, line.quantity) for line in lines] == [(466, 108, 9)]
    assert (old_lines[0].proposal_id, old_lines[0].quantity, old_lines[0].price) == (465, 5, 1234)


@pytest.mark.asyncio
async def test_price_or_stock_change_invalidates_preview_without_mutations(monkeypatch):
    session, _, _, lines, candidates = _setup(monkeypatch)
    preview = await BelzakupkiSourceEquipmentService.preview(session, order_id=461, scope=SCOPE, proposal_id=465)
    changed = [ExactCatalogCandidate(product=candidates[0].product, brand="MDV", available_quantity=3, price=3990, cost=1691), candidates[1]]
    monkeypatch.setattr(BelzakupkiEquipmentPrefillService, "candidates", AsyncMock(return_value=changed))
    payload = ManagerOrderSourceEquipmentAdd(proposal_id=465, command_id="changed", preview_fingerprint=preview.preview_fingerprint, product_ids=[108])
    with pytest.raises(SourceEquipmentPreviewChangedError):
        await BelzakupkiSourceEquipmentService.add(session, order_id=461, scope=SCOPE, payload=payload)
    assert len(lines) == 1
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["sent", "approved"])
async def test_non_draft_never_offers_mutation(monkeypatch, status):
    session, _, proposal, _, _ = _setup(monkeypatch)
    proposal.status = status
    preview = await BelzakupkiSourceEquipmentService.preview(session, order_id=461, scope=SCOPE, proposal_id=465)
    assert all(not item.can_add and not item.can_restore for item in preview.items)
    assert all(item.reason == "proposal_not_draft" for item in preview.items)


@pytest.mark.asyncio
async def test_local_card_lists_only_source_identity_matched_active_originals(monkeypatch):
    session, _, _, _, _ = _setup(monkeypatch)
    files = [SimpleNamespace(id=126, original_filename="ТЗ.pdf", mime_type="application/pdf", source_meta={"source": "goszakupki_by", "external_id": "T-1", "belzakupki_document_id": "doc1"}),
             SimpleNamespace(id=127, original_filename="other.pdf", mime_type="application/pdf", source_meta={"source": "goszakupki_by", "external_id": "OTHER"})]
    result = MagicMock(); result.scalars.return_value.all.return_value = files
    session.execute.side_effect = None; session.execute.return_value = result
    card = await BelzakupkiSourceEquipmentService.card(session, order_id=461, scope=SCOPE)
    assert [file.attachment_id for file in card.originals] == [126]
    assert card.originals[0].document_id == "doc1"
    assert sum(item.quantity for obj in card.objects for item in obj.equipment) == 14
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_card_query_excludes_foreign_order_and_archived_links(monkeypatch):
    _, order, _, _, _ = _setup(monkeypatch)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [ServiceAttachment.__table__, OrderAttachmentLink.__table__]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: SQLModel.metadata.create_all(sync, tables=tables))
        async with AsyncSession(engine, expire_on_commit=False) as session:
            from datetime import datetime
            for attachment_id, order_id, source, external_id, archived in (
                (126, 461, "belzakupki", "T-1", False),
                (127, 999, "belzakupki", "T-1", False),
                (128, 461, "manager", "T-1", False),
                (129, 461, "belzakupki", "OTHER", False),
                (130, 461, "belzakupki", "T-1", True),
            ):
                session.add(ServiceAttachment(id=attachment_id, original_filename=f"{attachment_id}.pdf", source=source,
                                              source_meta={"source": "goszakupki_by", "external_id": external_id}))
                session.add(OrderAttachmentLink(order_id=order_id, attachment_id=attachment_id,
                                                archived_at=datetime.now() if archived else None))
            await session.commit()
            card = await BelzakupkiSourceEquipmentService.card(session, order_id=461, scope=SCOPE)
            assert [file.attachment_id for file in card.originals] == [126]
    finally:
        await engine.dispose()


def test_explicit_installation_facts_keep_route_values_without_pricing_or_guessing():
    facts = installation_facts({"equipment_details": "Кабинет 1: трасса 5 м; Кабинет 2: трасса 8 м; Кабинет 3: трасса 10 м; MDV AB12 × 14"})
    assert [fact.text for fact in facts] == ["Кабинет 1: трасса 5 м", "Кабинет 2: трасса 8 м", "Кабинет 3: трасса 10 м"]
    assert all(fact.needs_review and fact.source == "reviewed_equipment_details" for fact in facts)


def test_long_source_retains_explicit_communications_lengths_as_labelled_quotes():
    source = "Условия поставки: " + "подтверждённое условие " * 45 + "Длина коммуникаций: кабинет 1 — 5 м, кабинет 2 — 8 м, кабинет 3 — 10 м. Питание предусмотрено заказчиком"
    facts = installation_facts({"equipment_details": source})
    assert facts
    quotes = " ".join(fact.text for fact in facts)
    assert all(value in quotes for value in ("5 м", "8 м", "10 м"))
    assert any(fact.is_excerpt for fact in facts)
