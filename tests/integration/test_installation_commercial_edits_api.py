from decimal import Decimal

import pytest
from sqlmodel import select

from core.config import settings
from models import InstallationEstimate, InstallationEstimateRevision, InstallationPriceBook, Order, OrderProposal, OrderServiceLink, OrderStatus
from services.installation_estimate_confirmation_service import InstallationEstimateConfirmationService as Confirm


@pytest.mark.asyncio
async def test_manager_can_edit_and_remove_draft_installation_without_rewriting_revision(async_client, db):
    book = InstallationPriceBook(tenant_id=1, revision=1, fingerprint="commercial-api", entries=[])
    order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION)
    db.add_all([book, order])
    await db.flush()
    proposal = OrderProposal(order_id=order.id, is_selected=True)
    db.add(proposal)
    await db.flush()
    estimate = InstallationEstimate(tenant_id=1, storefront_id=1, order_id=order.id, proposal_id=proposal.id,
        confirmation_key_hash="commercial-api-key", confirmation_request_hash="commercial-api-request", preview_token_hash="commercial-api-preview")
    db.add(estimate)
    await db.flush()
    result = {"status": "fixed", "scope_ref": "scope", "subtotal": "3000.00", "discount": "0.00", "total": "3000.00",
              "customer_text": "Монтаж", "installations": [], "components": []}
    installations = []
    for index in range(5):
        key = f"unit-{index}"
        installations.append({"key": key, "typed_profile": {"product_kind": "complete_split_system", "indoor_type": "wall", "confirmed": True},
                              "route_length_m": "3", "holes_by_type": {}})
        result["installations"].append({"installation_key": key, "tariff_code": "wall", "work_label": "Монтаж", "short_title": "Монтаж",
                                         "included_scope": ["Трасса 3 м"], "measured": [], "selected_extras": []})
        result["components"].append({"code": "installation.base", "installation_key": key, "unit": "шт", "quantity": "1",
                                     "unit_price": "600.00", "gross": "600.00", "discount": "0.00", "net": "600.00", "description": "Монтаж"})
    snapshot = {"input": {"installations": installations}, "result": result, "commercial_projection_version": 2}
    revision = InstallationEstimateRevision(estimate_id=estimate.id, revision=1, price_book_id=book.id,
                                            price_book_revision=1, total=Decimal("3000"), snapshot=snapshot)
    db.add(revision)
    await db.flush()
    links = Confirm.new_revision_lines(order_id=order.id, proposal_id=proposal.id, saved=revision, mode="collapsed")
    db.add_all(links)
    await db.commit()
    order_id, proposal_id, link_id, revision_id = int(order.id), int(proposal.id), int(links[0].id), int(revision.id)
    login = await async_client.post("/login/access-token", data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    row = {"link_id": link_id, "title": "Монтаж по договорённости", "quantity": 5, "price": 550, "description": "Трасса 5 м"}
    response = await async_client.patch(f"/api/manager/orders/{order_id}", headers=headers,
        json={"line_proposal_id": proposal_id, "services": [row]})
    assert response.status_code == 200, response.text
    saved = response.json()["service_lines"][0]
    assert (saved["price"], saved["quantity"], saved["description"]) == (550, 5, "Трасса 5 м")
    assert saved["installation_estimate_revision_id"] is None
    row.pop("description")
    response = await async_client.patch(f"/api/manager/orders/{order_id}", headers=headers,
        json={"line_proposal_id": proposal_id, "services": [row]})
    assert response.status_code == 200 and response.json()["service_lines"][0]["description"] == "Трасса 5 м"
    response = await async_client.patch(f"/api/manager/orders/{order_id}", headers=headers,
        json={"line_proposal_id": proposal_id, "services": []})
    assert response.status_code == 200 and response.json()["service_lines"] == []
    db.expire_all()
    retained = await db.get(InstallationEstimateRevision, revision_id)
    assert retained.snapshot == snapshot and retained.total == Decimal("3000")
    assert not (await db.execute(select(OrderServiceLink).where(OrderServiceLink.order_id == order_id))).scalars().all()
