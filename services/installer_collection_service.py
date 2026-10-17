"""A reviewed collection instruction is not a receipt or a payment."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from api_contracts.installer_workspace import (
    InstallerCollection,
    ManagerCollectionInstruction,
)
from crud.installer_workspace import InstallerWorkspaceDAO as DAO
from core.request_context import current_request_id
from models import Order, TenantAuditEvent
from models.installer_publication import InstallerCollectionInstruction
from services.service_estimate_money import money


class InstallerWorkspaceError(ValueError):
    def __init__(self, code, message, status_code=409):
        super().__init__(message)
        self.code, self.status_code = code, status_code


@dataclass(frozen=True)
class CollectionFinancialSnapshot:
    fingerprint: str
    balances: dict[str, Decimal]
    stable: bool


def _value(value):
    return value.value if hasattr(value, "value") else value


class InstallerCollectionService:
    @staticmethod
    async def withdraw_for_stage(session, scope, order_id, stage_id):
        """Keep the per-order revision when its visit is removed under the Order lock."""
        from models.installer_workspace import OrderWorkAssignment

        row = await session.scalar(
            select(InstallerCollectionInstruction)
            .where(
                InstallerCollectionInstruction.order_id == order_id,
                InstallerCollectionInstruction.tenant_id == scope.tenant_id,
                InstallerCollectionInstruction.storefront_id == scope.storefront_id,
                InstallerCollectionInstruction.assignment_id.in_(
                    select(OrderWorkAssignment.id).where(
                        OrderWorkAssignment.order_id == order_id,
                        OrderWorkAssignment.work_stage_id == stage_id,
                    )
                ),
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            return
        before = {
            "assignment_id": row.assignment_id,
            "amount": str(row.amount),
            "currency": row.currency,
            "version": row.version,
        }
        row.assignment_id, row.amount, row.currency = None, None, None
        row.financial_fingerprint = ""
        row.version += 1
        row.updated_at = datetime.now()
        session.add(row)
        session.add(
            TenantAuditEvent(
                tenant_id=scope.tenant_id,
                storefront_id=scope.storefront_id,
                actor_username="manager_stage_delete",
                request_id=current_request_id(),
                action="installer.collection_withdrawn",
                entity_type="order",
                entity_id=order_id,
                change_set={
                    "before": before,
                    "after": {"assignment_id": None, "version": row.version},
                    "work_stage_id": stage_id,
                },
            )
        )
        await session.flush()

    @staticmethod
    async def snapshot(session, order) -> CollectionFinancialSnapshot:
        active = [p for p in order.proposals if not p.is_archived]
        selected = [p for p in active if p.is_selected]
        proposal = (
            selected[0]
            if len(selected) == 1
            else active[0]
            if len(active) == 1
            else None
        )
        certain = len(selected) == 1 or len(active) <= 1
        lines = [
            link
            for link in [*order.product_links, *order.service_links]
            if link.proposal_id == (proposal.id if proposal else None)
        ]
        total = money(
            sum(
                (
                    money(link.price) * Decimal(str(link.quantity or 0))
                    for link in lines
                ),
                Decimal(0),
            )
        )
        target = _value(order.target_currency)
        target_amount = money(order.target_currency_amount or 0)
        rate = (
            total / target_amount
            if target and target_amount > 0 and total > 0
            else None
        )
        byn_paid = Decimal(0)
        target_paid = Decimal(0)
        payments = []
        convertible = True
        for payment in sorted(order.payments, key=lambda p: p.id):
            currency, amount = _value(payment.currency), money(payment.amount)
            payments.append([payment.id, str(amount), currency])
            if currency == "BYN":
                byn_paid += amount
                if rate:
                    target_paid += amount / rate
            elif target and currency == target and rate:
                target_paid += amount
                byn_paid += amount * rate
            else:
                convertible = False
        balances = {"BYN": money(max(Decimal(0), total - byn_paid))}
        if target and rate:
            balances[target] = money(max(Decimal(0), target_amount - target_paid))
        payload = {
            "order": order.id,
            "proposal": proposal.id if proposal else None,
            "certain": certain,
            "total": str(total),
            "target": target,
            "target_amount": str(target_amount),
            "payments": payments,
        }
        stamp = await session.scalar(
            select(Order.updated_at).where(Order.id == order.id)
        )
        stable = certain and convertible and stamp == order.updated_at
        payload["stable"] = stable
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        return CollectionFinancialSnapshot(digest, balances if stable else {}, stable)

    @staticmethod
    async def _recipient(session, row, scope):
        if row is None or row.assignment_id is None:
            return None, None
        from models.installer_workspace import OrderWorkAssignment, TenantWorkerProfile
        from models import StaffUser
        from crud.worker_assignment import WorkerAssignmentDAO

        record = await session.execute(
            select(OrderWorkAssignment, TenantWorkerProfile, StaffUser)
            .join(
                TenantWorkerProfile,
                TenantWorkerProfile.id == OrderWorkAssignment.worker_profile_id,
            )
            .join(StaffUser, StaffUser.id == TenantWorkerProfile.staff_user_id)
            .where(
                OrderWorkAssignment.id == row.assignment_id,
                OrderWorkAssignment.tenant_id == scope.tenant_id,
                OrderWorkAssignment.storefront_id == scope.storefront_id,
            )
        )
        result = record.first()
        if result is None:
            return None, None
        assignment, profile, person = result
        live = await session.scalar(
            WorkerAssignmentDAO.visible(scope, profile.staff_user_id)
            .where(OrderWorkAssignment.id == assignment.id)
            .execution_options(populate_existing=True)
        )
        return live, person

    @classmethod
    async def installer_view(cls, session, *, order, scope, assignment, snapshot=None):
        row = await DAO.collection(session, order.id)
        if row is None or row.assignment_id is None:
            return InstallerCollection(status="not_assigned")
        recipient, person = await cls._recipient(session, row, scope)
        if row.assignment_id != assignment.id:
            return InstallerCollection(
                status="not_collector",
                recipient_name=person.display_name if person else None,
            )
        snapshot = snapshot or await cls.snapshot(session, order)
        valid = bool(
            recipient is not None
            and snapshot.stable
            and row.financial_fingerprint == snapshot.fingerprint
            and row.currency in snapshot.balances
            and row.amount <= snapshot.balances[row.currency]
        )
        return InstallerCollection(
            status="ready" if valid else "requires_review",
            version=row.version,
            amount=f"{row.amount:.2f}" if valid else None,
            currency=row.currency if valid else None,
            recipient_name=person.display_name if person else None,
            updated_at=row.updated_at,
        )

    @classmethod
    async def manager_view(cls, session, *, order, scope, snapshot):
        row = await DAO.collection(session, order.id)
        if row is None:
            return ManagerCollectionInstruction(
                version=0,
                assignment_id=None,
                amount=None,
                currency=None,
                status="not_assigned",
                updated_at=None,
            )
        recipient, _ = await cls._recipient(session, row, scope)
        valid = bool(
            recipient is not None
            and snapshot.stable
            and row.financial_fingerprint == snapshot.fingerprint
            and row.currency in snapshot.balances
            and row.amount <= snapshot.balances[row.currency]
        )
        return ManagerCollectionInstruction(
            version=row.version,
            assignment_id=row.assignment_id,
            amount=f"{row.amount:.2f}" if row.amount is not None else None,
            currency=row.currency,
            status="not_assigned"
            if row.assignment_id is None
            else "ready"
            if valid
            else "requires_review",
            updated_at=row.updated_at,
        )

    @classmethod
    async def update(cls, session, *, auth, order_id, payload):
        from services.worker_assignment_service import WorkerAssignmentService

        scope = await WorkerAssignmentService.actor_fence(session, auth, mutation=True)
        order = await DAO.order(session, scope, order_id, lock=True)
        if order is None:
            raise InstallerWorkspaceError("order_not_found", "Заказ не найден", 404)
        row = await DAO.collection(session, order.id)
        if (row.version if row else 0) != payload.expected_version:
            raise InstallerWorkspaceError(
                "collection_changed", "Поручение уже изменено. Обновите данные"
            )
        snapshot = await cls.snapshot(session, order)
        if payload.financial_fingerprint != snapshot.fingerprint:
            raise InstallerWorkspaceError(
                "financials_changed",
                "Оплаты или сумма заказа изменились. Обновите данные",
            )
        if payload.assignment_id is not None:
            candidate = InstallerCollectionInstruction(
                assignment_id=payload.assignment_id
            )
            assignment, _ = await cls._recipient(session, candidate, scope)
            if assignment is None or assignment.order_id != order.id:
                raise InstallerWorkspaceError(
                    "assignment_unavailable", "Назначение недоступно", 400
                )
            if not snapshot.stable or payload.currency not in snapshot.balances:
                raise InstallerWorkspaceError(
                    "collection_currency_unavailable",
                    "Уточните предложение и валюту заказа",
                    400,
                )
            if payload.amount > snapshot.balances[payload.currency]:
                raise InstallerWorkspaceError(
                    "collection_exceeds_balance",
                    "Сумма превышает актуальный остаток по заказу",
                    400,
                )
        before = (
            None
            if row is None
            else {
                "assignment_id": row.assignment_id,
                "amount": str(row.amount) if row.amount is not None else None,
                "currency": row.currency,
                "version": row.version,
                "financial_fingerprint": row.financial_fingerprint,
            }
        )
        if row is None:
            row = InstallerCollectionInstruction(
                tenant_id=scope.tenant_id,
                storefront_id=scope.storefront_id,
                order_id=order.id,
            )
        row.assignment_id, row.amount, row.currency = (
            payload.assignment_id,
            payload.amount,
            payload.currency,
        )
        row.financial_fingerprint = snapshot.fingerprint
        row.version += 1
        row.updated_at = datetime.now()
        session.add(row)
        session.add(
            TenantAuditEvent(
                tenant_id=scope.tenant_id,
                storefront_id=scope.storefront_id,
                actor_staff_user_id=auth.staff_user_id,
                actor_username=auth.username,
                request_id=current_request_id(),
                action="installer.collection_published",
                entity_type="order",
                entity_id=order.id,
                change_set={
                    "before": before,
                    "after": {
                        "assignment_id": row.assignment_id,
                        "amount": str(row.amount) if row.amount is not None else None,
                        "currency": row.currency,
                        "version": row.version,
                    },
                },
            )
        )
        await session.flush()
        return order
