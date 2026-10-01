from decimal import Decimal
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from models import InstallationEstimateRevision
from schemas_installation_price_book import InstallationPreviewResponse
from services.installation_estimate_confirmation_service import InstallationEstimateConfirmationService as Confirm
from services.installation_estimate_projection import grouped_installation_lines


def preview(count=5):
    return InstallationPreviewResponse.model_validate({"status": "fixed", "scope_ref": "scope",
        "total": str(count * 600), "subtotal": str(count * 600), "discount": "0",
        "customer_text": "Historical full text.",
        "installations": [{"installation_key": str(index), "tariff_code": "wall.small",
            "short_title": "Монтаж настенного кондиционера до 4,2 кВт", "work_label": "Монтаж",
            "included_scope": ["Электропитание до 5 м", "Расходные материалы"],
            "measured": [{"code": "route.length_m", "label": "Трасса", "unit": "м",
                "actual": "3.00" if index % 2 else "3", "included": "3", "extra": "0"}],
            "selected_extras": []} for index in range(count)],
        "components": [{"code": "installation.base", "installation_key": str(index), "unit": "шт",
            "quantity": "1", "unit_price": "600", "gross": "600", "discount": "0", "net": "600",
            "description": "Монтаж"} for index in range(count)]})


def test_five_identical_installations_are_one_exact_quantity_line():
    result = preview()
    lines = grouped_installation_lines(result)
    assert len(lines) == 1
    assert lines[0].quantity == 5 and lines[0].price == Decimal("600")
    assert "Установка" not in lines[0].title
    assert "Электропитание до 5 м" in lines[0].description
    assert "Не включены: дренажный насос" in lines[0].description
    saved = InstallationEstimateRevision(id=1, estimate_id=1, revision=1, price_book_id=1,
        price_book_revision=1, total=result.total, snapshot={"result": result.model_dump(mode="json"),
                                                           "commercial_projection_version": 2})
    persisted = Confirm.new_revision_lines(order_id=1, proposal_id=2, saved=saved, mode="collapsed")
    assert len(persisted) == 1 and persisted[0].quantity == 5 and persisted[0].price == Decimal("600")
    assert persisted[0].quantity * persisted[0].price == Decimal("3000")


def test_different_tariffs_and_measured_work_are_separate_lines():
    result = preview(3)
    result.installations[1].tariff_code = "wall.medium"
    result.installations[2].measured[0].actual = Decimal("2")
    lines = grouped_installation_lines(result)
    assert len(lines) == 3
    assert sum(line.quantity * line.price for line in lines) == Decimal("1800")


def test_historical_snapshot_keeps_its_saved_collapsed_line():
    result = preview()
    saved = InstallationEstimateRevision(id=1, estimate_id=1, revision=1, price_book_id=1,
        price_book_revision=1, total=result.total, snapshot={"result": result.model_dump(mode="json")})
    lines = Confirm.new_revision_lines(order_id=1, proposal_id=2, saved=saved, mode="collapsed")
    assert [(line.title, line.quantity, line.price) for line in lines] == [
        ("Historical full text.", 1, Decimal("3000"))]


@pytest.mark.asyncio
async def test_frozen_description_checks_link_ownership_and_keeps_legacy_snapshot_unchanged():
    from services.installation_estimate_projection import frozen_installation_descriptions
    result = preview()
    revision = SimpleNamespace(id=10, total=result.total,
        snapshot={"result": result.model_dump(mode="json"), "commercial_projection_version": 2})
    estimate = SimpleNamespace(order_id=1, proposal_id=2)
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(revision, estimate)])))
    valid = SimpleNamespace(id=20, order_id=1, proposal_id=2, installation_estimate_revision_id=10,
        installation_line_index=0, installation_projection_mode="collapsed")
    wrong = SimpleNamespace(**{**vars(valid), "id": 21, "proposal_id": 3})
    descriptions = await frozen_installation_descriptions(session, [valid, wrong])
    assert set(descriptions) == {20}
    assert "Расходные материалы" in descriptions[20]
    revision.snapshot.pop("commercial_projection_version")
    for summary in revision.snapshot["result"]["installations"]:
        summary.pop("included_scope")
        summary.pop("short_title")
    valid.quantity = 1
    valid.price = result.total
    valid.title = result.customer_text
    assert await frozen_installation_descriptions(session, [valid]) == {}
    from services.installation_estimate_projection import frozen_installation_presentations
    displayed = (await frozen_installation_presentations(session, [valid]))[20]["installation_display_lines"]
    assert [(line["quantity"], line["price"]) for line in displayed] == [(5, Decimal("600"))]
    assert valid.quantity == 1 and valid.price == Decimal("3000") and valid.title == "Historical full text."
    assert "Расходные материалы" not in displayed[0]["description"]
    assert "Электропитание до 5 м" not in displayed[0]["description"]


@pytest.mark.asyncio
async def test_five_manual_standard_installations_confirm_attach_replay_and_remain_frozen(tmp_path):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlmodel import SQLModel, select
    from models import Tenant, Storefront, Order, OrderProposal, OrderServiceLink, OrderStatus, InstallationPriceBook
    from models.tenancy import TenantScope
    from schemas import ManagerOrderUpdatePayload
    from schemas_installation_confirmation import ManagerInstallationPreviewPayload, ManagerInstallationConfirmPayload, ManagerInstallationAttachPayload
    from services.installation_price_book_service import InstallationPriceBookService as Book
    from services.order_update.command import OrderUpdateCommandService

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'grouped.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=601, storefront_id=602)
    entry = {"tariff_id": 1, "code": "wall.small.standard", "mode": "fixed", "base_price": "600",
        "short_name": "Монтаж", "description": "Стандарт",
        "match": {"product_kind": "complete_split_system", "indoor_type": "wall", "work_kind": "standard",
                  "match_strategy": "capacity_only", "capacity_max_kw": "4.2"},
        "included_route_m": "3", "included_holes": {"shared_pass_through": "1"}, "rules": []}
    entry["rules"] = [{"id": index, "code": code, "rule_type": rule_type, "name": code,
        "line_template": "{name}", "unit": unit, "unit_price": price, "is_optional": False, "sort_order": index}
        for index, (code, rule_type, unit, price) in enumerate([
            ("route.extra_m", "per_meter_over_included", "м", "50"),
            ("hole.through_thin.extra", "per_hole_manual", "шт", "30"),
            ("hole.through_thick.extra", "per_hole_manual", "шт", "70")], 1)]
    Book._validate_entries([entry])
    try:
        async with factory() as session:
            session.add(Tenant(id=601, slug="grouped", display_name="Grouped"))
            session.add(Storefront(id=602, tenant_id=601, slug="main", display_name="Main", status="active", is_default=True))
            session.add(InstallationPriceBook(tenant_id=601, revision=1, fingerprint="grouped-book", entries=[entry]))
            order = Order(tenant_id=601, storefront_id=602, status=OrderStatus.NEGOTIATION)
            session.add(order)
            await session.flush()
            proposal = OrderProposal(order_id=order.id, is_selected=True)
            session.add(proposal)
            await session.commit()
            order_id, proposal_id = int(order.id), int(proposal.id)
            keys = [f"manual-{index}" for index in range(5)]
            payload = ManagerInstallationPreviewPayload.model_validate({"installations": [{
                "key": key, "typed_profile": {"product_kind": "complete_split_system", "indoor_type": "wall", "confirmed": True},
                "route_length_m": "3", "holes_by_type": {"through_thick": 1}} for key in keys],
                "tariff_selections": {key: entry["code"] for key in keys}})
            quoted = await Book.preview(session, scope, payload, idempotency_key="grouped-preview-key",
                                        tariff_selections=payload.tariff_selections)
            accepted = await Confirm.confirm(session, scope, ManagerInstallationConfirmPayload(
                preview_ref=quoted.preview_ref, order_id=order_id, proposal_id=proposal_id,
                verified_service_only_keys=keys), idempotency_key="grouped-confirm-key", actor="manager")
            attached = await Confirm.attach(session, scope, order_id=order_id, proposal_id=proposal_id,
                estimate_id=accepted.value.estimate_id, payload=ManagerInstallationAttachPayload(revision=1),
                idempotency_key="grouped-attach-key")
            assert attached.value.total == Decimal("3000")
            assert [(line.quantity, line.price) for line in attached.value.lines] == [(5, Decimal("600"))]
            repeated = await Confirm.attach(session, scope, order_id=order_id, proposal_id=proposal_id,
                estimate_id=accepted.value.estimate_id, payload=ManagerInstallationAttachPayload(revision=1),
                idempotency_key="grouped-replay-key")
            assert repeated.value == attached.value
            line = (await session.execute(select(OrderServiceLink).where(OrderServiceLink.order_id == order_id))).scalars().one()
            with pytest.raises(ValueError):
                await OrderUpdateCommandService.update_order_for_manager(session, order_id,
                    ManagerOrderUpdatePayload(services=[{"link_id": line.id, "title": line.title,
                        "quantity": 4, "price": 600, "installation_estimate_revision_id": line.installation_estimate_revision_id,
                        "installation_projection_mode": "collapsed"}]), tenant_scope=scope)
            await session.refresh(line)
            assert line.quantity == 5 and line.price == Decimal("600")
    finally:
        await engine.dispose()
