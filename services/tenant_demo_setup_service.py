"""Reviewed, idempotent synthetic CRM fixture for one existing tenant."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.request_context import current_request_id
from models import (
    Customer,
    Lead,
    Order,
    OrderProductLink,
    OrderProposal,
    Product,
    Storefront,
    Tenant,
    TenantAuditEvent,
    TenantCatalogGrant,
    TenantDemoFixtureState,
    TenantOffer,
)
from models.tenancy import TenantScope
from services.storefront_onboarding_plan_token import StorefrontOnboardingPlanToken
from services.tenant_demo_fixture import DEMO_CUSTOMERS, DEMO_ORDERS, FIXTURE_VERSION
from services.tenant_demo_fixture_state import (
    fixture_blockers,
    load_fixture_snapshot,
    serialize_fixture,
)


class TenantDemoSetupBlockedError(RuntimeError):
    """The exact target is unsafe or no longer matches the reviewed plan."""


class TenantDemoSetupPlanToken(StorefrontOnboardingPlanToken):
    @staticmethod
    def _key() -> bytes:
        return hashlib.sha256(
            b"mvn:tenant-demo-setup:plan-token:v1\0"
            + settings.SECRET_KEY.encode("utf-8")
        ).digest()


def _datetime_value(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _fixture_source_fingerprint(
    *, tenant_id: int, storefront_id: int, order_index: int,
) -> str:
    raw = f"tenant-demo:{FIXTURE_VERSION}:{tenant_id}:{storefront_id}:{order_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TenantDemoSetupService:
    MIN_VISIBLE_OFFERS = len(DEMO_ORDERS)

    @classmethod
    async def plan(
        cls,
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
        lock: bool = False,
    ) -> dict[str, Any]:
        if tenant_id <= 0 or storefront_id <= 0:
            raise TenantDemoSetupBlockedError("Tenant and storefront IDs must be positive")
        if lock:
            await cls._lock_operation(
                session,
                tenant_id=tenant_id,
                storefront_id=storefront_id,
            )

        pair_statement = (
            select(Tenant, Storefront)
            .join(Storefront, Storefront.tenant_id == Tenant.id)
            .where(Tenant.id == tenant_id, Storefront.id == storefront_id)
        )
        if lock:
            pair_statement = pair_statement.with_for_update()
        pair = (await session.execute(pair_statement)).first()
        if pair is None:
            raise TenantDemoSetupBlockedError("Exact tenant/storefront pair not found")
        tenant, storefront = pair
        scope = TenantScope(
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
            is_system=bool(tenant.is_system),
            demo_read_only=bool(tenant.demo_read_only),
            is_canonical_storefront=False,
        )

        fixture_statement = select(TenantDemoFixtureState).where(
            TenantDemoFixtureState.tenant_id == tenant_id
        )
        if lock:
            fixture_statement = fixture_statement.with_for_update()
        fixture = (
            await session.execute(fixture_statement)
        ).scalar_one_or_none()

        inventory = await cls._inventory(
            session,
            tenant_id=tenant_id,
            storefront_id=storefront_id,
        )
        chosen_offers, eligible_offer_count = await cls._chosen_offers(
            session,
            scope=scope,
            fixture=fixture,
            lock=lock,
        )
        fixture_snapshot = await load_fixture_snapshot(session, fixture=fixture)

        blockers: list[str] = []
        if tenant.is_system:
            blockers.append("system tenant is not a demo target")
        if tenant.kind != "independent_seller":
            blockers.append("tenant kind must be independent_seller")
        if tenant.status != "active":
            blockers.append("tenant must be active")
        if storefront.status != "active":
            blockers.append("storefront must be active")
        if not storefront.is_default:
            blockers.append("storefront must be the tenant default")
        if len(chosen_offers) < cls.MIN_VISIBLE_OFFERS:
            blockers.append(
                f"at least {cls.MIN_VISIBLE_OFFERS} active published allowed offers are required"
            )

        already_ready = fixture is not None
        if fixture is None:
            if tenant.demo_read_only:
                blockers.append("demo policy is enabled without a fixture identity record")
            if any(inventory[key] for key in ("customer_ids", "order_ids", "lead_ids")):
                blockers.append("target CRM is not empty; existing data will not be overwritten")
        else:
            blockers.extend(
                fixture_blockers(
                    tenant=tenant,
                    storefront=storefront,
                    fixture=fixture,
                    inventory=inventory,
                    snapshot=fixture_snapshot,
                    chosen_offers=chosen_offers,
                )
            )

        report: dict[str, Any] = {
            "operation": "tenant_demo_setup_v1",
            "status": (
                "blocked" if blockers else "already_ready" if already_ready else "planned"
            ),
            "target": {
                "tenant_id": int(tenant.id),
                "tenant_slug": tenant.slug,
                "tenant_kind": tenant.kind,
                "tenant_status": tenant.status,
                "tenant_is_system": bool(tenant.is_system),
                "tenant_demo_read_only": bool(tenant.demo_read_only),
                "tenant_updated_at": _datetime_value(tenant.updated_at),
                "storefront_id": int(storefront.id),
                "storefront_slug": storefront.slug,
                "storefront_status": storefront.status,
                "storefront_is_default": bool(storefront.is_default),
                "storefront_updated_at": _datetime_value(storefront.updated_at),
            },
            "fixture_version": FIXTURE_VERSION,
            "inventory": inventory,
            "fixture_state": serialize_fixture(fixture),
            "fixture_snapshot": fixture_snapshot,
            "eligible_offer_count": eligible_offer_count,
            "chosen_offers": chosen_offers,
            "planned_records": {
                "customers": len(DEMO_CUSTOMERS),
                "orders": len(DEMO_ORDERS),
                "selected_proposals": len(DEMO_ORDERS),
                "product_lines": len(DEMO_ORDERS),
                "leads": 0,
                "external_effects": [],
                "purchase_costs": 0,
            },
            "blockers": blockers,
        }
        encoded = json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        report["plan_digest"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return report

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
        plan_token: str,
    ) -> dict[str, Any]:
        verified = TenantDemoSetupPlanToken.verify(plan_token)
        report = await cls.plan(
            session,
            tenant_id=tenant_id,
            storefront_id=storefront_id,
            lock=True,
        )
        if not hmac.compare_digest(verified.plan_digest, report["plan_digest"]):
            raise TenantDemoSetupBlockedError("State changed; review a fresh plan")
        if report["blockers"]:
            raise TenantDemoSetupBlockedError("; ".join(report["blockers"]))
        if report["status"] == "already_ready":
            return {
                "status": "already_ready",
                "tenant_id": tenant_id,
                "storefront_id": storefront_id,
                "fixture_version": FIXTURE_VERSION,
                "customer_ids": report["fixture_state"]["customer_ids"],
                "order_ids": report["fixture_state"]["order_ids"],
            }

        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise TenantDemoSetupBlockedError("Tenant disappeared during execution")

        customers: list[Customer] = []
        for spec in DEMO_CUSTOMERS:
            customer = Customer(
                tenant_id=tenant_id,
                name=spec.name,
                phone=spec.phone,
                email=spec.email,
                type=spec.customer_type,
                city=spec.city,
                actual_address=spec.address,
                inn=None,
            )
            session.add(customer)
            customers.append(customer)
        await session.flush()

        chosen_offers = report["chosen_offers"]
        orders: list[Order] = []
        proposals: list[OrderProposal] = []
        product_lines: list[OrderProductLink] = []
        for order_index, spec in enumerate(DEMO_ORDERS):
            offer = chosen_offers[spec.offer_index]
            price = int(offer["price"])
            order = Order(
                tenant_id=tenant_id,
                storefront_id=storefront_id,
                customer_id=int(customers[spec.customer_index].id),
                delivery_address=spec.delivery_address,
                status=spec.status,
                title=spec.title,
                comment=spec.comment,
                source_fingerprint=_fixture_source_fingerprint(
                    tenant_id=tenant_id,
                    storefront_id=storefront_id,
                    order_index=order_index,
                ),
                technical_meta={
                    "tenant_demo_fixture": {
                        "version": FIXTURE_VERSION,
                        "order_index": order_index,
                    }
                },
                total_amount=float(price),
                total_cost=0.0,
                margin=float(price),
                total_payments=0.0,
                balance_due=float(price),
                is_paid=False,
                proposal_status="draft",
            )
            session.add(order)
            await session.flush()
            proposal = OrderProposal(
                order_id=int(order.id),
                name="Основное демо-предложение",
                status="draft",
                is_selected=True,
                sort_order=0,
            )
            session.add(proposal)
            await session.flush()
            product_line = OrderProductLink(
                order_id=int(order.id),
                proposal_id=int(proposal.id),
                product_id=int(offer["product_id"]),
                quantity=1,
                price=price,
                cost=0,
                title_snapshot=offer["product_title"],
                currency_snapshot="BYN",
                is_installation_included=False,
                installation_price=0,
            )
            session.add(product_line)
            orders.append(order)
            proposals.append(proposal)
            product_lines.append(product_line)
        await session.flush()

        tenant.demo_read_only = True
        tenant.updated_at = datetime.now(timezone.utc)
        fixture = TenantDemoFixtureState(
            tenant_id=tenant_id,
            storefront_id=storefront_id,
            fixture_version=FIXTURE_VERSION,
            customer_ids=[int(value.id) for value in customers],
            order_ids=[int(value.id) for value in orders],
            proposal_ids=[int(value.id) for value in proposals],
            product_line_ids=[int(value.id) for value in product_lines],
            offer_ids=[int(value["offer_id"]) for value in chosen_offers],
        )
        session.add(fixture)
        session.add(
            TenantAuditEvent(
                tenant_id=tenant_id,
                storefront_id=storefront_id,
                actor_staff_user_id=None,
                actor_username="system:tenant-demo-setup",
                action="tenant_demo.fixture_created",
                entity_type="tenant",
                entity_id=tenant_id,
                request_id=current_request_id(),
                change_set={
                    "fixture_version": FIXTURE_VERSION,
                    "plan_digest": report["plan_digest"],
                    "customer_ids": fixture.customer_ids,
                    "order_ids": fixture.order_ids,
                    "offer_ids": fixture.offer_ids,
                    "purchase_costs": 0,
                },
            )
        )
        await session.flush()
        return {
            "status": "initialized",
            "tenant_id": tenant_id,
            "storefront_id": storefront_id,
            "fixture_version": FIXTURE_VERSION,
            "customer_ids": fixture.customer_ids,
            "order_ids": fixture.order_ids,
        }

    @staticmethod
    async def _lock_operation(
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
    ) -> None:
        if session.get_bind().dialect.name != "postgresql":
            return
        await session.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(:lock_key, 0))"
            ),
            {
                "lock_key": (
                    f"mvn:tenant-demo-setup:v1:{tenant_id}:{storefront_id}"
                )
            },
        )

    @staticmethod
    async def _inventory(
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
    ) -> dict[str, list[int]]:
        customers = list(
            (
                await session.execute(
                    select(Customer.id)
                    .where(Customer.tenant_id == tenant_id)
                    .order_by(Customer.id.asc())
                )
            ).scalars().all()
        )
        orders = list(
            (
                await session.execute(
                    select(Order.id)
                    .where(
                        Order.tenant_id == tenant_id,
                        Order.storefront_id == storefront_id,
                    )
                    .order_by(Order.id.asc())
                )
            ).scalars().all()
        )
        leads = list(
            (
                await session.execute(
                    select(Lead.id)
                    .where(
                        Lead.tenant_id == tenant_id,
                        Lead.storefront_id == storefront_id,
                    )
                    .order_by(Lead.id.asc())
                )
            ).scalars().all()
        )
        return {
            "customer_ids": [int(value) for value in customers],
            "order_ids": [int(value) for value in orders],
            "lead_ids": [int(value) for value in leads],
        }

    @classmethod
    async def _chosen_offers(
        cls,
        session: AsyncSession,
        *,
        scope: TenantScope,
        fixture: TenantDemoFixtureState | None,
        lock: bool,
    ) -> tuple[list[dict[str, Any]], int]:
        active_grant = (
            select(TenantCatalogGrant.id)
            .where(
                TenantCatalogGrant.id == TenantOffer.catalog_grant_id,
                TenantCatalogGrant.tenant_id == scope.tenant_id,
                TenantCatalogGrant.storefront_id == scope.storefront_id,
                TenantCatalogGrant.status == "active",
            )
            .exists()
        )
        conditions = (
            TenantOffer.tenant_id == scope.tenant_id,
            TenantOffer.storefront_id == scope.storefront_id,
            TenantOffer.status == "active",
            TenantOffer.is_published.is_(True),
            TenantOffer.price > 0,
            Product.is_published.is_(True),
            or_(TenantOffer.catalog_grant_id.is_(None), active_grant),
        )
        count_statement = (
            select(func.count(TenantOffer.id))
            .select_from(TenantOffer)
            .join(Product, Product.id == TenantOffer.product_id)
            .where(*conditions)
        )
        eligible_count = int((await session.execute(count_statement)).scalar_one())

        statement = (
            select(TenantOffer, Product)
            .join(Product, Product.id == TenantOffer.product_id)
            .where(*conditions)
        )
        if fixture is None:
            statement = statement.order_by(TenantOffer.id.asc()).limit(
                cls.MIN_VISIBLE_OFFERS
            )
        else:
            statement = statement.where(TenantOffer.id.in_(fixture.offer_ids))
        if lock:
            statement = statement.with_for_update(of=(TenantOffer, Product))
        rows = list((await session.execute(statement)).all())
        if fixture is not None:
            by_id = {int(offer.id): (offer, product) for offer, product in rows}
            rows = [by_id[value] for value in fixture.offer_ids if value in by_id]
        return (
            [
                {
                    "offer_id": int(offer.id),
                    "product_id": int(product.id),
                    "product_title": product.title,
                    "product_slug": product.slug,
                    "price": int(offer.price),
                    "offer_updated_at": _datetime_value(offer.updated_at),
                    "product_is_published": bool(product.is_published),
                    "offer_is_published": bool(offer.is_published),
                    "offer_status": offer.status,
                    "catalog_grant_id": offer.catalog_grant_id,
                }
                for offer, product in rows
            ],
            eligible_count,
        )

__all__ = [
    "TenantDemoSetupBlockedError",
    "TenantDemoSetupPlanToken",
    "TenantDemoSetupService",
]
