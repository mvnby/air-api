"""Add a small editable teaching set; never reset shared demos or send messages."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.request_context import current_request_id
from models import (
    Customer, Lead, Order, OrderProductLink, OrderProposal, Storefront, Tenant,
    TenantAuditEvent, TenantDemoFixtureState,
)
from models.common import CustomerType, OrderStatus
from models.tenancy import TenantScope
from services.storefront_onboarding_plan_token import StorefrontOnboardingPlanToken
from services.tenant_demo_setup_service import TenantDemoSetupService


OPERATION = "tenant_training_setup_v1"
ACTION = "tenant_training.fixture_created"
PREFIX = "[ОБУЧЕНИЕ]"


class TenantTrainingSetupBlockedError(RuntimeError):
    pass


class TenantTrainingPlanToken(StorefrontOnboardingPlanToken):
    @staticmethod
    def _key() -> bytes:
        return hashlib.sha256(
            b"mvn:tenant-training-setup:plan-token:v1\0"
            + settings.SECRET_KEY.encode("utf-8")
        ).digest()


class TenantTrainingSetupService:
    @classmethod
    async def plan(
        cls, session: AsyncSession, *, tenant_id: int, storefront_id: int,
        tenant_slug: str, lock: bool = False,
    ) -> dict[str, Any]:
        if tenant_id <= 0 or storefront_id <= 0:
            raise TenantTrainingSetupBlockedError("Target IDs must be positive")
        if lock and session.get_bind().dialect.name == "postgresql":
            await session.execute(text(
                "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"
            ), {"key": f"mvn:{OPERATION}:{tenant_id}"})
        statement = select(Tenant, Storefront).join(
            Storefront, Storefront.tenant_id == Tenant.id
        ).where(Tenant.id == tenant_id, Storefront.id == storefront_id)
        if lock:
            statement = statement.with_for_update()
        pair = (await session.execute(statement)).first()
        if pair is None:
            raise TenantTrainingSetupBlockedError("Exact tenant/storefront pair not found")
        tenant, storefront = pair
        blockers = []
        if tenant.slug != tenant_slug or not tenant_slug.startswith("training-"):
            blockers.append("exact private training- tenant slug is required")
        if tenant.is_system or tenant.kind != "independent_seller":
            blockers.append("target must be a non-system independent seller")
        if tenant.status != "active" or storefront.status != "active" or not storefront.is_default:
            blockers.append("target must have an active default storefront")
        if tenant.demo_read_only:
            blockers.append("shared read-only demo cannot be used for teaching writes")
        demo = (await session.execute(select(TenantDemoFixtureState).where(
            TenantDemoFixtureState.tenant_id == tenant_id
        ))).scalar_one_or_none()
        if demo is not None:
            blockers.append("shared demo fixture identity exists")

        receipts = list((await session.execute(select(TenantAuditEvent).where(
            TenantAuditEvent.tenant_id == tenant_id,
            TenantAuditEvent.action == ACTION,
        ).order_by(TenantAuditEvent.id))).scalars().all())
        if len(receipts) > 1:
            blockers.append("multiple teaching fixture identities exist")
        receipt = receipts[0] if receipts else None
        identity = receipt.change_set.get("records", {}) if receipt else None
        if receipt:
            if receipt.storefront_id != storefront_id or receipt.change_set.get("operation") != OPERATION:
                blockers.append("teaching fixture identity conflicts with target")
            blockers.extend(await cls._identity_blockers(session, identity, tenant_id, storefront_id))

        # Reuse the current storefront offer/grant eligibility contract. No CRM
        # data is borrowed from the shared demo or from any other tenant.
        offers, count = await TenantDemoSetupService._chosen_offers(
            session, scope=TenantScope(
                tenant_id=tenant_id, storefront_id=storefront_id,
                is_system=bool(tenant.is_system), demo_read_only=bool(tenant.demo_read_only),
                is_canonical_storefront=False,
            ), fixture=None, lock=lock,
        )
        if receipt is None and len(offers) < 2:
            blockers.append("two current positive-price allowed storefront offers are required")
        inventory = await TenantDemoSetupService._inventory(
            session, tenant_id=tenant_id, storefront_id=storefront_id,
        )
        if receipt is None:
            # A missing receipt must never silently recreate partly deleted data.
            collisions = (await session.execute(select(Customer.id).where(
                Customer.tenant_id == tenant_id,
                Customer.email.in_(["training.individual@example.invalid", "training.company@example.invalid"]),
            ))).first()
            marked_orders = (await session.execute(select(Order.id).where(
                Order.tenant_id == tenant_id,
                Order.source_fingerprint.in_([cls._fingerprint(tenant_id, storefront_id, i) for i in range(2)]),
            ))).first()
            marked_leads = (await session.execute(select(Lead.id).where(
                Lead.tenant_id == tenant_id,
                Lead.intake_event_key == f"{OPERATION}:{tenant_id}:{storefront_id}",
            ))).first()
            if collisions or marked_orders or marked_leads:
                blockers.append("teaching markers exist without an intact identity receipt")
        report = {
            "operation": OPERATION,
            "status": "blocked" if blockers else "already_created" if receipt else "planned",
            "target": {
                "tenant_id": tenant_id, "tenant_slug": tenant.slug,
                "tenant_display_name": tenant.display_name, "tenant_status": tenant.status,
                "tenant_kind": tenant.kind, "tenant_is_system": tenant.is_system,
                "tenant_demo_read_only": tenant.demo_read_only,
                "tenant_updated_at": tenant.updated_at.isoformat(),
                "storefront_id": storefront_id, "storefront_slug": storefront.slug,
                "storefront_status": storefront.status,
                "storefront_is_default": storefront.is_default,
                "storefront_updated_at": storefront.updated_at.isoformat(),
            },
            "inventory": inventory, "records": identity,
            "receipt_id": receipt.id if receipt else None,
            "chosen_offers": offers, "eligible_offer_count": count,
            "planned_records": {
                "customers": 2, "new_leads": 1, "negotiation_orders": 2,
                "draft_proposals": 4, "product_lines": 4, "purchase_costs": 0,
                "documents": 0, "external_effects": [],
            },
            "blockers": blockers,
        }
        report["plan_digest"] = hashlib.sha256(json.dumps(
            report, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        return report

    @staticmethod
    def _fingerprint(tenant_id: int, storefront_id: int, index: int) -> str:
        return hashlib.sha256(f"{OPERATION}:{tenant_id}:{storefront_id}:{index}".encode()).hexdigest()

    @staticmethod
    async def _identity_blockers(session, identity, tenant_id, storefront_id):
        blockers = []
        if not isinstance(identity, dict) or set(identity) != {"customer_ids", "lead_ids", "order_ids", "proposal_ids", "line_ids"}:
            return ["teaching fixture identity receipt is malformed"]
        for key, model, size in (
            ("customer_ids", Customer, 2), ("lead_ids", Lead, 1),
            ("order_ids", Order, 2), ("proposal_ids", OrderProposal, 4),
            ("line_ids", OrderProductLink, 4),
        ):
            ids = identity[key]
            if not isinstance(ids, list) or len(ids) != size or any(type(i) is not int for i in ids) or len(set(ids)) != size:
                blockers.append(f"invalid recorded {key}")
                continue
            statement = select(model.id).where(model.id.in_(ids))
            if model in (Customer, Lead, Order):
                statement = statement.where(model.tenant_id == tenant_id)
                if model is not Customer:
                    statement = statement.where(model.storefront_id == storefront_id)
            else:
                statement = statement.where(model.order_id.in_(identity["order_ids"]))
            found = set((await session.execute(statement)).scalars().all())
            if found != set(ids):
                blockers.append(f"recorded {key} missing or outside target; no automatic repair")
        return blockers

    @classmethod
    async def execute(cls, session: AsyncSession, *, tenant_id: int, storefront_id: int,
                      tenant_slug: str, plan_token: str) -> dict[str, Any]:
        verified = TenantTrainingPlanToken.verify(plan_token)
        report = await cls.plan(session, tenant_id=tenant_id, storefront_id=storefront_id,
                                tenant_slug=tenant_slug, lock=True)
        if not hmac.compare_digest(verified.plan_digest, report["plan_digest"]):
            raise TenantTrainingSetupBlockedError("State changed; review a fresh plan")
        if report["blockers"]:
            raise TenantTrainingSetupBlockedError("; ".join(report["blockers"]))
        if report["status"] == "already_created":
            return {"status": "already_created", "records": report["records"]}

        records = {k: [] for k in ("customer_ids", "lead_ids", "order_ids", "proposal_ids", "line_ids")}
        customers = []
        for index, (name, kind, email) in enumerate((
            ("Анна Примерова", CustomerType.individual, "individual"),
            ('ООО «Учебный климат»', CustomerType.company, "company"),
        )):
            customer = Customer(
                tenant_id=tenant_id, name=f"{PREFIX} {name}",
                full_legal_name=f"{PREFIX} {name}" if index else None,
                type=kind, phone="Не указан (учебный клиент)",
                email=f"training.{email}@example.invalid", inn=None,
                signing_mode="statutory_body" if index else "self",
                signer_position="Директор (учебный пример)" if index else "",
                signer_name="Иван Примеров (учебный пример)" if index else None,
                acting_basis="Устав (учебный пример)" if index else "",
                city="Минск (учебный пример)",
                actual_address=f"{PREFIX} г. Минск, ул. Примерная, {index + 1}",
            )
            session.add(customer)
            await session.flush()
            customers.append(customer)
            records["customer_ids"].append(int(customer.id))
        lead = Lead(
            tenant_id=tenant_id, storefront_id=storefront_id,
            name=f"{PREFIX} Заявка на подбор для квартиры", status="new", source="manager",
            segment_hint="b2c", email="training.lead@example.invalid", phone=None,
            request_text=f"{PREFIX} Нужен кондиционер для комнаты 25 м². Подберите два варианта. Данные вымышлены; связь не требуется.",
            intake_event_key=f"{OPERATION}:{tenant_id}:{storefront_id}",
            intake_meta={"training_fixture": OPERATION},
        )
        session.add(lead)
        await session.flush()
        records["lead_ids"].append(int(lead.id))
        for index, customer in enumerate(customers):
            first_price = int(report["chosen_offers"][0]["price"])
            order = Order(
                tenant_id=tenant_id, storefront_id=storefront_id, customer_id=int(customer.id),
                title=f"{PREFIX} {'Подбор для квартиры' if index == 0 else 'Климат для офиса: подготовка договора'}",
                status=OrderStatus.NEGOTIATION, delivery_address=customer.actual_address,
                comment=("Учебная запись: варианты можно менять. Контакты и реквизиты вымышлены. "
                         "Документы ещё не созданы. Для урока открыть документы заказа, "
                         "создать черновик договора, проверить PDF и выпустить учебный образец "
                         "с номером из учебной серии."),
                source_fingerprint=cls._fingerprint(tenant_id, storefront_id, index),
                technical_meta={"training_fixture": OPERATION},
                total_amount=float(first_price), total_cost=0, margin=float(first_price),
                balance_due=float(first_price), proposal_status="draft",
            )
            session.add(order)
            await session.flush()
            records["order_ids"].append(int(order.id))
            for option_index, offer in enumerate(report["chosen_offers"]):
                proposal = OrderProposal(order_id=int(order.id),
                    name=f"{PREFIX} Вариант {option_index + 1}", status="draft",
                    is_selected=option_index == 0, sort_order=option_index)
                session.add(proposal)
                await session.flush()
                line = OrderProductLink(order_id=int(order.id), proposal_id=int(proposal.id),
                    product_id=int(offer["product_id"]), quantity=1, price=int(offer["price"]),
                    cost=0, title_snapshot=offer["product_title"], currency_snapshot="BYN",
                    is_installation_included=False, installation_price=0)
                session.add(line)
                await session.flush()
                records["proposal_ids"].append(int(proposal.id))
                records["line_ids"].append(int(line.id))
        session.add(TenantAuditEvent(
            tenant_id=tenant_id, storefront_id=storefront_id,
            actor_username="system:tenant-training-setup", action=ACTION,
            entity_type="tenant", entity_id=tenant_id, request_id=current_request_id(),
            change_set={"operation": OPERATION, "plan_digest": report["plan_digest"], "records": records},
        ))
        await session.flush()
        return {"status": "created", "records": records}
