"""PostgreSQL contract for Manager confirmation and exact proposal attachment."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import func, select

from core.config import settings
from crud.public_write_idempotency import PublicWriteIdempotencyDAO
from models import (
    InstallationEstimate, InstallationEstimateRevision, InstallationPriceBook,
    InstallationPreviewSnapshot, Order, OrderProposal, OrderServiceLink, OrderStatus,
    ServiceTariff, ServiceTariffRule,
)
from models.tenancy import TenantScope
from schemas_installation_confirmation import ManagerInstallationAttachPayload, ManagerInstallationConfirmPayload
from schemas_installation_price_book import InstallationPreviewPayload
from services.installation_estimate_confirmation_service import InstallationEstimateConfirmationService as Confirm
from services.installation_price_book_service import InstallationPriceBookService as Book
from services.tariffs_service import TariffsService


def _entry(*, base_price="500.00", mode="fixed"):
    return {
        "tariff_id": 1, "code": "installation.wall.2_4", "mode": mode,
        "match": {"product_kind": "complete_split_system", "indoor_type": "wall",
                  "capacity_min_kw": "2", "capacity_max_kw": "4",
                  "pipe_liquid": '1/4"', "pipe_gas": '3/8"'},
        "base_price": base_price, "short_name": "Монтаж", "description": "Черновое описание",
        "included_route_m": "3", "included_holes": {"diamond": "1"},
        "rules": [
            {"id": 1, "code": "route.extra_m", "rule_type": "per_meter_over_included",
             "name": "Трасса", "line_template": "{name}", "unit": "м",
             "unit_price": "10.25", "is_optional": False, "sort_order": 1},
            {"id": 2, "code": "hole.diamond.extra", "rule_type": "per_hole_manual",
             "name": "Алмазное отверстие", "line_template": "{name}", "unit": "шт",
             "unit_price": "50.00", "is_optional": False, "sort_order": 2},
        ],
    }


def _preview_body(revision=1):
    return {"installations": [{"key": "one", "typed_profile": {
        "product_kind": "complete_split_system", "indoor_type": "wall",
        "capacity_cooling_kw": "2.5", "pipe_liquid": '1/4"', "pipe_gas": '3/8"',
        "confirmed": True}, "route_length_m": "6", "holes_by_type": {"diamond": 2}}],
        "expected_revision": revision}


async def _headers(client):
    login = await client.post("/login/access-token", data={
        "username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD,
    })
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_manager_confirm_stale_reprices_then_attach_exact_revision(async_client, db):
    first_book = InstallationPriceBook(tenant_id=1, revision=1, fingerprint="confirm-book-one",
                                       entries=[_entry()])
    order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION)
    db.add_all([first_book, order])
    await db.flush()
    selected = OrderProposal(order_id=order.id, name="Selected", is_selected=True, sort_order=0)
    alternative = OrderProposal(order_id=order.id, name="Alternative", is_selected=False, sort_order=10)
    db.add_all([selected, alternative])
    await db.commit()
    headers = await _headers(async_client)
    prefix = "/api/manager/installation-estimates"

    first_preview = await async_client.post(f"{prefix}/preview", json=_preview_body(),
        headers={**headers, "Idempotency-Key": "manager-preview-first"})
    assert first_preview.status_code == 200, first_preview.text
    assert first_preview.json()["total"] == "580.75"

    second_book = InstallationPriceBook(tenant_id=1, revision=2, fingerprint="confirm-book-two",
                                        entries=[_entry(base_price="550.00")])
    db.add(second_book)
    await db.commit()
    confirmation = {"preview_ref": first_preview.json()["preview_ref"],
                    "order_id": order.id, "proposal_id": selected.id,
                    "verified_service_only_keys": ["one"]}
    stale = await async_client.post(f"{prefix}/confirm", json=confirmation,
        headers={**headers, "Idempotency-Key": "manager-confirm-stale"})
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "price_changed"
    assert stale.json()["detail"]["new_consent_required"] is True
    fresh = stale.json()["detail"]["fresh_preview"]
    assert fresh["total"] == "630.75" and fresh["preview_ref"]

    confirmation["preview_ref"] = fresh["preview_ref"]
    confirmed = await async_client.post(f"{prefix}/confirm", json=confirmation,
        headers={**headers, "Idempotency-Key": "manager-confirm-accepted"})
    assert confirmed.status_code == 201, confirmed.text
    estimate_id = confirmed.json()["estimate_id"]
    assert confirmed.json()["total"] == "630.75"
    repeated = await async_client.post(f"{prefix}/confirm", json=confirmation,
        headers={**headers, "Idempotency-Key": "manager-confirm-accepted"})
    assert repeated.status_code == 201 and repeated.json() == confirmed.json()
    assert await db.scalar(select(func.count(InstallationEstimate.id))) == 1

    attach_url = f"{prefix}/{estimate_id}/orders/{order.id}/proposals/{selected.id}/attach"
    wrong_proposal_url = f"{prefix}/{estimate_id}/orders/{order.id}/proposals/{alternative.id}/attach"
    wrong_proposal = await async_client.post(wrong_proposal_url, json={"revision": 1},
        headers={**headers, "Idempotency-Key": "manager-attach-wrong-proposal"})
    assert wrong_proposal.status_code == 404
    wrong_revision = await async_client.post(attach_url, json={"revision": 2},
        headers={**headers, "Idempotency-Key": "manager-attach-wrong-revision"})
    assert wrong_revision.status_code == 404
    attached = await async_client.post(attach_url, json={"revision": 1},
        headers={**headers, "Idempotency-Key": "manager-attach-selected"})
    assert attached.status_code == 200, attached.text
    assert attached.json()["total"] == "630.75"
    assert len(attached.json()["lines"]) == 1
    assert "трасса 6" in attached.json()["lines"][0]["title"].lower()
    repeated_attach = await async_client.post(attach_url, json={"revision": 1},
        headers={**headers, "Idempotency-Key": "manager-attach-selected-again"})
    assert repeated_attach.status_code == 200 and repeated_attach.json() == attached.json()
    assert await db.scalar(select(func.count(OrderServiceLink.id))) == 1
    await db.refresh(order)
    assert Decimal(str(order.total_amount)) == Decimal("630.75")

    saved_preview = (await db.execute(select(InstallationPreviewSnapshot).where(
        InstallationPreviewSnapshot.token_hash.is_not(None),
        InstallationPreviewSnapshot.price_book_id == second_book.id,
    ))).scalars().first()
    saved_preview.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.add(saved_preview)
    await db.commit()
    retained = await async_client.get(f"{prefix}/{estimate_id}/revisions/1", headers=headers)
    assert retained.status_code == 200, retained.text
    assert retained.json()["snapshot"]["result"]["total"] == "630.75"
    assert retained.json()["snapshot"]["confirmation"]["actor"]
    assert await db.scalar(select(func.count(InstallationEstimateRevision.id))) == 1

    alternative_preview = await async_client.post(f"{prefix}/preview", json=_preview_body(2),
        headers={**headers, "Idempotency-Key": "manager-preview-alternative"})
    assert alternative_preview.status_code == 200, alternative_preview.text
    alt_confirm = await async_client.post(f"{prefix}/confirm", json={
        "preview_ref": alternative_preview.json()["preview_ref"],
        "order_id": order.id, "proposal_id": alternative.id,
        "verified_service_only_keys": ["one"],
    }, headers={**headers, "Idempotency-Key": "manager-confirm-alternative"})
    assert alt_confirm.status_code == 201, alt_confirm.text
    alt_url = f"{prefix}/{alt_confirm.json()['estimate_id']}/orders/{order.id}/proposals/{alternative.id}/attach"
    alt_attached = await async_client.post(alt_url, json={"revision": 1, "mode": "detailed"},
        headers={**headers, "Idempotency-Key": "manager-attach-alternative"})
    assert alt_attached.status_code == 200, alt_attached.text
    assert len(alt_attached.json()["lines"]) == 3
    assert sum((Decimal(line["price"]) for line in alt_attached.json()["lines"]), Decimal("0")) == Decimal("630.75")
    await db.refresh(order)
    assert Decimal(str(order.total_amount)) == Decimal("630.75")
    assert selected.is_selected and not alternative.is_selected


@pytest.mark.asyncio
async def test_manager_quote_preview_has_no_confirmable_reference(async_client, db):
    book = InstallationPriceBook(tenant_id=1, revision=1, fingerprint="confirm-quote-book",
                                 entries=[_entry(mode="quote")])
    db.add(book)
    await db.commit()
    headers = await _headers(async_client)
    preview = await async_client.post("/api/manager/installation-estimates/preview",
        json=_preview_body(), headers={**headers, "Idempotency-Key": "manager-preview-quote-mode"})
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "quote"
    assert preview.json()["preview_ref"] is None
    assert await db.scalar(select(func.count(InstallationPreviewSnapshot.id))) == 0


@pytest.mark.asyncio
async def test_manager_confirm_rejects_expired_and_from_preview(async_client, db):
    book = InstallationPriceBook(tenant_id=1, revision=1, fingerprint="confirm-from-book",
                                 entries=[_entry(mode="from")])
    order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION)
    db.add_all([book, order])
    await db.flush()
    proposal = OrderProposal(order_id=order.id, is_selected=True)
    db.add(proposal)
    await db.commit()
    headers = await _headers(async_client)
    prefix = "/api/manager/installation-estimates"
    preview = await async_client.post(f"{prefix}/preview", json=_preview_body(),
        headers={**headers, "Idempotency-Key": "manager-preview-from-mode"})
    assert preview.status_code == 200 and preview.json()["status"] == "from"
    body = {"preview_ref": preview.json()["preview_ref"], "order_id": order.id,
            "proposal_id": proposal.id, "verified_service_only_keys": ["one"]}
    refused = await async_client.post(f"{prefix}/confirm", json=body,
        headers={**headers, "Idempotency-Key": "manager-confirm-from-mode"})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "preview_not_fixed"
    saved = (await db.execute(select(InstallationPreviewSnapshot))).scalar_one()
    saved.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.add(saved)
    await db.commit()
    expired = await async_client.post(f"{prefix}/confirm", json=body,
        headers={**headers, "Idempotency-Key": "manager-confirm-expired-ref"})
    assert expired.status_code == 409 and expired.json()["detail"]["code"] == "preview_expired"
    assert await db.scalar(select(func.count(InstallationEstimate.id))) == 0


@pytest.mark.asyncio
async def test_concurrent_manager_confirm_and_attach_create_one_revision_and_line(db_engine):
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True, is_canonical_storefront=True)
    async with factory() as setup:
        book = InstallationPriceBook(tenant_id=1, revision=1, fingerprint="race-confirm-book",
                                     entries=[_entry()])
        order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION)
        setup.add_all([book, order])
        await setup.flush()
        proposal = OrderProposal(order_id=order.id, is_selected=True)
        setup.add(proposal)
        await setup.commit()
        payload = InstallationPreviewPayload.model_validate(_preview_body())
        preview = await Book.preview(setup, scope, payload, idempotency_key="race-preview-one-key")
        confirm_payload = ManagerInstallationConfirmPayload(
            preview_ref=preview.preview_ref, order_id=order.id, proposal_id=proposal.id,
            verified_service_only_keys=["one"],
        )
        order_id, proposal_id = order.id, proposal.id

    async def confirm_once():
        async with factory() as session:
            return await Confirm.confirm(session, scope, confirm_payload,
                                         idempotency_key="race-confirm-one-key", actor="manager")

    first, second = await asyncio.gather(confirm_once(), confirm_once())
    assert first.value == second.value
    estimate_id = first.value.estimate_id

    async def attach_once():
        async with factory() as session:
            return await Confirm.attach(session, scope, order_id=order_id, proposal_id=proposal_id,
                estimate_id=estimate_id, payload=ManagerInstallationAttachPayload(revision=1),
                idempotency_key="race-attach-one-key")

    first_attach, second_attach = await asyncio.gather(attach_once(), attach_once())
    assert first_attach.value == second_attach.value
    async with factory() as verify:
        assert await verify.scalar(select(func.count(InstallationEstimate.id))) == 1
        assert await verify.scalar(select(func.count(InstallationEstimateRevision.id))) == 1
        assert await verify.scalar(select(func.count(OrderServiceLink.id)).where(
            OrderServiceLink.proposal_id == proposal_id)) == 1


@pytest.mark.asyncio
async def test_distinct_confirm_keys_same_tenant_do_not_deadlock_after_receipt_claim(db_engine, monkeypatch):
    """Both receipt inserts hold FK KEY SHARE before the tenant serialization lock."""
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True, is_canonical_storefront=True)
    async with factory() as setup:
        setup.add(InstallationPriceBook(tenant_id=1, revision=1,
                                        fingerprint="distinct-confirm-book", entries=[_entry()]))
        orders = [Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION)
                  for _ in range(2)]
        setup.add_all(orders)
        await setup.flush()
        proposals = [OrderProposal(order_id=order.id, is_selected=True) for order in orders]
        setup.add_all(proposals)
        await setup.commit()
        targets = [(int(order.id), int(proposal.id)) for order, proposal in zip(orders, proposals)]
        previews = [await Book.preview(setup, scope,
                    InstallationPreviewPayload.model_validate(_preview_body()),
                    idempotency_key=f"distinct-confirm-preview-{index}")
                    for index in range(2)]

    barrier = asyncio.Barrier(2)
    original_claim = PublicWriteIdempotencyDAO.claim

    async def claim_then_barrier(session, **kwargs):
        receipt = await original_claim(session, **kwargs)
        if kwargs["command_name"] == "manager_installation_confirm_v1":
            assert receipt is not None
            await asyncio.wait_for(barrier.wait(), timeout=10)
        return receipt

    monkeypatch.setattr(PublicWriteIdempotencyDAO, "claim", staticmethod(claim_then_barrier))

    async def confirm_one(index):
        async with factory() as session:
            order_id, proposal_id = targets[index]
            return await Confirm.confirm(session, scope, ManagerInstallationConfirmPayload(
                preview_ref=previews[index].preview_ref, order_id=order_id,
                proposal_id=proposal_id, verified_service_only_keys=["one"],
            ), idempotency_key=f"distinct-confirm-command-{index}", actor="manager")

    results = await asyncio.wait_for(asyncio.gather(confirm_one(0), confirm_one(1)), timeout=15)
    assert results[0].value.estimate_id != results[1].value.estimate_id
    async with factory() as verify:
        assert await verify.scalar(select(func.count(InstallationEstimate.id))) == 2


@pytest.mark.asyncio
async def test_confirm_holds_publication_lock_until_accepted_revision_commits(db_engine, monkeypatch):
    """A price publication cannot commit between confirm's final reprice and commit."""
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True, is_canonical_storefront=True)
    async with factory() as setup:
        tariff = ServiceTariff(
            tenant_id=scope.tenant_id, service_kind="installation",
            selector_label="Монтаж", short_name="Монтаж",
            installation_code="installation.wall.2_4", installation_price_mode="fixed",
            installation_match={"indoor_type": "wall", "capacity_min_kw": "2", "capacity_max_kw": "4",
                                "pipe_liquid": '1/4"', "pipe_gas": '3/8"'},
            base_price=500, included_route_meters=3, included_holes_by_type={"diamond": 1},
        )
        order = Order(tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
                      status=OrderStatus.NEGOTIATION)
        setup.add_all([tariff, order])
        await setup.flush()
        proposal = OrderProposal(order_id=order.id, is_selected=True)
        setup.add_all([
            proposal,
            ServiceTariffRule(tariff_id=tariff.id, rule_type="per_meter_over_included",
                              component_code="route.extra_m", name="Трасса", unit="м", unit_price=10.25),
            ServiceTariffRule(tariff_id=tariff.id, rule_type="per_hole_manual",
                              component_code="hole.diamond.extra", name="Отверстие", unit_price=50),
        ])
        await setup.commit()
        first_book = await Book.publish(setup, scope, actor="publisher-one")
        preview = await Book.preview(
            setup, scope, InstallationPreviewPayload.model_validate(_preview_body()),
            idempotency_key="confirm-publication-race-preview",
        )
        tariff.base_price = 550
        setup.add(tariff)
        await setup.commit()
        confirm_payload = ManagerInstallationConfirmPayload(
            preview_ref=preview.preview_ref, order_id=order.id, proposal_id=proposal.id,
            verified_service_only_keys=["one"],
        )

    confirm_repriced = asyncio.Event()
    release_confirm = asyncio.Event()
    publisher_started = asyncio.Event()
    publisher_inside_tenant_lock = asyncio.Event()
    release_publisher = asyncio.Event()
    start_together = asyncio.Barrier(2)
    original_preview = Book.preview.__func__
    original_tariffs = TariffsService.get_all_tariffs

    async def pause_confirm_after_reprice(cls, session, current_scope, payload, *, idempotency_key=None, persist=True):
        response = await original_preview(
            cls, session, current_scope, payload,
            idempotency_key=idempotency_key, persist=persist,
        )
        if session.info.get("hold_confirm_after_reprice"):
            confirm_repriced.set()
            await release_confirm.wait()
        return response

    async def pause_publisher_after_tenant_lock(session, *args, **kwargs):
        tariffs = await original_tariffs(session, *args, **kwargs)
        if session.info.get("hold_publisher_after_tenant_lock"):
            publisher_inside_tenant_lock.set()
            await release_publisher.wait()
        return tariffs

    monkeypatch.setattr(Book, "preview", classmethod(pause_confirm_after_reprice))
    monkeypatch.setattr(TariffsService, "get_all_tariffs", staticmethod(pause_publisher_after_tenant_lock))

    async def confirm_once():
        async with factory() as session:
            session.info["hold_confirm_after_reprice"] = True
            await start_together.wait()
            return await Confirm.confirm(
                session, scope, confirm_payload,
                idempotency_key="confirm-publication-race-confirm", actor="manager",
            )

    async def publish_once():
        async with factory() as session:
            session.info["hold_publisher_after_tenant_lock"] = True
            await start_together.wait()
            await confirm_repriced.wait()
            publisher_started.set()
            published = await Book.publish(session, scope, actor="publisher-two")
            await session.commit()
            return published

    confirmation = asyncio.create_task(confirm_once())
    publication = asyncio.create_task(publish_once())
    await asyncio.wait_for(confirm_repriced.wait(), timeout=3)
    await asyncio.wait_for(publisher_started.wait(), timeout=3)
    publication_reached_after_confirm_reprice = False
    try:
        await asyncio.wait_for(publisher_inside_tenant_lock.wait(), timeout=1)
        publication_reached_after_confirm_reprice = True
    except TimeoutError:
        pass
    finally:
        release_confirm.set()

    confirmed = await asyncio.wait_for(confirmation, timeout=3)
    await asyncio.wait_for(publisher_inside_tenant_lock.wait(), timeout=3)
    release_publisher.set()
    published = await asyncio.wait_for(publication, timeout=3)

    assert not publication_reached_after_confirm_reprice
    assert confirmed.value.price_book_id == first_book.price_book_id
    assert confirmed.value.price_book_revision == first_book.revision
    assert published.revision == first_book.revision + 1
    async with factory() as verification:
        accepted = await verification.scalar(select(InstallationEstimateRevision).where(
            InstallationEstimateRevision.price_book_id == first_book.price_book_id,
        ))
        assert accepted is not None
