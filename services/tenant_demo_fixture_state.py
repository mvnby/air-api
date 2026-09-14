"""Read and validate the persisted synthetic tenant demo identity."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Customer,
    Order,
    OrderProductLink,
    OrderProposal,
    Storefront,
    Tenant,
    TenantDemoFixtureState,
)
from services.tenant_demo_fixture import DEMO_CUSTOMERS, DEMO_ORDERS, FIXTURE_VERSION


def _datetime_value(value) -> str | None:
    return value.isoformat() if value is not None else None


def serialize_fixture(
    fixture: TenantDemoFixtureState | None,
) -> dict[str, Any] | None:
    if fixture is None:
        return None
    return {
        "tenant_id": fixture.tenant_id,
        "storefront_id": fixture.storefront_id,
        "fixture_version": fixture.fixture_version,
        "customer_ids": list(fixture.customer_ids),
        "order_ids": list(fixture.order_ids),
        "proposal_ids": list(fixture.proposal_ids),
        "product_line_ids": list(fixture.product_line_ids),
        "offer_ids": list(fixture.offer_ids),
        "created_at": _datetime_value(fixture.created_at),
        "updated_at": _datetime_value(fixture.updated_at),
    }


async def load_fixture_snapshot(
    session: AsyncSession,
    *,
    fixture: TenantDemoFixtureState | None,
) -> dict[str, Any] | None:
    if fixture is None:
        return None
    customers = list(
        (
            await session.execute(
                select(Customer)
                .where(
                    Customer.id.in_(fixture.customer_ids),
                    Customer.tenant_id == fixture.tenant_id,
                )
                .order_by(Customer.id.asc())
            )
        ).scalars().all()
    )
    orders = list(
        (
            await session.execute(
                select(Order)
                .where(
                    Order.id.in_(fixture.order_ids),
                    Order.tenant_id == fixture.tenant_id,
                    Order.storefront_id == fixture.storefront_id,
                )
                .order_by(Order.id.asc())
            )
        ).scalars().all()
    )
    proposals = list(
        (
            await session.execute(
                select(OrderProposal)
                .where(
                    OrderProposal.id.in_(fixture.proposal_ids),
                    OrderProposal.order_id.in_(fixture.order_ids),
                )
                .order_by(OrderProposal.id.asc())
            )
        ).scalars().all()
    )
    lines = list(
        (
            await session.execute(
                select(OrderProductLink)
                .where(
                    OrderProductLink.id.in_(fixture.product_line_ids),
                    OrderProductLink.order_id.in_(fixture.order_ids),
                )
                .order_by(OrderProductLink.id.asc())
            )
        ).scalars().all()
    )
    return {
        "customers": [
            {
                "id": int(value.id),
                "tenant_id": value.tenant_id,
                "name": value.name,
                "phone": value.phone,
                "email": value.email,
                "type": str(value.type),
                "inn": value.inn,
                "city": value.city,
                "actual_address": value.actual_address,
            }
            for value in customers
        ],
        "orders": [
            {
                "id": int(value.id),
                "tenant_id": value.tenant_id,
                "storefront_id": value.storefront_id,
                "customer_id": value.customer_id,
                "status": str(value.status),
                "source_fingerprint": value.source_fingerprint,
                "technical_meta": value.technical_meta,
                "total_amount": value.total_amount,
                "total_cost": value.total_cost,
                "margin": value.margin,
            }
            for value in orders
        ],
        "proposals": [
            {
                "id": int(value.id),
                "order_id": value.order_id,
                "is_selected": value.is_selected,
                "is_archived": value.is_archived,
            }
            for value in proposals
        ],
        "product_lines": [
            {
                "id": int(value.id),
                "order_id": value.order_id,
                "proposal_id": value.proposal_id,
                "product_id": value.product_id,
                "quantity": value.quantity,
                "price": value.price,
                "cost": value.cost,
                "installation_price": value.installation_price,
            }
            for value in lines
        ],
    }


def fixture_blockers(
    *,
    tenant: Tenant,
    storefront: Storefront,
    fixture: TenantDemoFixtureState,
    inventory: dict[str, list[int]],
    snapshot: dict[str, Any] | None,
    chosen_offers: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if fixture.storefront_id != storefront.id:
        blockers.append("fixture identity belongs to another storefront")
    if fixture.fixture_version != FIXTURE_VERSION:
        blockers.append("fixture version is unsupported")
    if not tenant.demo_read_only:
        blockers.append("fixture exists but demo read-only policy is disabled")
    if inventory["customer_ids"] != sorted(fixture.customer_ids):
        blockers.append("tenant customers differ from the recorded demo fixture")
    if inventory["order_ids"] != sorted(fixture.order_ids):
        blockers.append("storefront orders differ from the recorded demo fixture")
    if inventory["lead_ids"]:
        blockers.append("demo storefront contains unrecorded leads")
    if [value["offer_id"] for value in chosen_offers] != fixture.offer_ids:
        blockers.append("recorded demo offers are no longer active and allowed")
    if snapshot is None:
        blockers.append("fixture snapshot is missing")
        return blockers
    if len(snapshot["customers"]) != len(DEMO_CUSTOMERS):
        blockers.append("recorded demo customers are missing")
    if len(snapshot["orders"]) != len(DEMO_ORDERS):
        blockers.append("recorded demo orders are missing")
    if len(snapshot["proposals"]) != len(DEMO_ORDERS):
        blockers.append("recorded demo proposals are missing")
    if len(snapshot["product_lines"]) != len(DEMO_ORDERS):
        blockers.append("recorded demo product lines are missing")
    if any(value["inn"] is not None for value in snapshot["customers"]):
        blockers.append("demo customer contains an unexpected tax identifier")
    if any(
        not value["name"].startswith("[ДЕМО]")
        or not value["phone"].startswith("Не указан (демо ")
        or not str(value["email"] or "").endswith("@example.invalid")
        for value in snapshot["customers"]
    ):
        blockers.append("demo customer identity marker changed")
    if any(
        float(value["total_cost"]) != 0.0
        or value["technical_meta"].get("tenant_demo_fixture", {}).get("version")
        != FIXTURE_VERSION
        for value in snapshot["orders"]
    ):
        blockers.append("demo order marker or purchase cost changed")
    if any(
        not value["is_selected"] or value["is_archived"]
        for value in snapshot["proposals"]
    ):
        blockers.append("demo proposal selection changed")
    if any(
        value["cost"] != 0 or value["installation_price"] != 0
        for value in snapshot["product_lines"]
    ):
        blockers.append("demo product line contains a purchase or installation cost")
    if [value["order_id"] for value in snapshot["proposals"]] != fixture.order_ids:
        blockers.append("demo proposals no longer match the recorded orders")
    if [value["order_id"] for value in snapshot["product_lines"]] != fixture.order_ids:
        blockers.append("demo product lines no longer match the recorded orders")
    if [value["product_id"] for value in snapshot["product_lines"]] != [
        value["product_id"] for value in chosen_offers
    ]:
        blockers.append("demo product lines no longer match the recorded offers")
    return blockers


__all__ = ["fixture_blockers", "load_fixture_snapshot", "serialize_fixture"]
