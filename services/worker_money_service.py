"""Atomic client receipts, cash reservations and recipient-acknowledged handovers."""

from datetime import datetime, timezone
from decimal import Decimal


from crud.installer_workspace import InstallerWorkspaceDAO
from crud.worker_money import WorkerMoneyDAO as DAO
from models import Payment
from models.worker_money import (
    WorkerCashHandover,
    WorkerCashHandoverAllocation,
    WorkerCashReceipt,
)
from services.installer_collection_service import (
    InstallerCollectionService as Collection,
    InstallerWorkspaceError,
)
from services.order_service import OrderService
from services.worker_assignment_access_service import WorkerAssignmentAccessService
from services.worker_money_access import manages_cash
from services.worker_money_reader import WorkerMoneyReader


class WorkerMoneyService(WorkerMoneyReader):
    @classmethod
    async def receive(cls, session, auth, assignment_id, payload):
        scope, profile, account, _, _ = await cls.context(session, auth, mutation=True)
        replay = await cls.replay(
            session, auth, account, "client_received", assignment_id, payload
        )
        if replay:
            return replay
        assignment = await WorkerAssignmentAccessService.get_for_actor(
            session, auth, assignment_id, for_update=True
        )
        if assignment is None:
            raise InstallerWorkspaceError("work_not_found", "Работа не найдена", 404)
        order = await InstallerWorkspaceDAO.order(
            session, scope, assignment.order_id, lock=True
        )
        instruction = await InstallerWorkspaceDAO.collection(session, order.id)
        if instruction is None or instruction.assignment_id != assignment.id:
            raise InstallerWorkspaceError(
                "collection_not_found", "Поручение на получение денег не найдено", 404
            )
        cls.check_version(instruction.version, payload.expected_version)
        snapshot = await Collection.snapshot(session, order)
        if (
            not snapshot.stable
            or instruction.financial_fingerprint != snapshot.fingerprint
            or instruction.currency not in snapshot.balances
            or instruction.amount > snapshot.balances[instruction.currency]
        ):
            raise InstallerWorkspaceError(
                "collection_requires_review",
                "Сумма к получению изменилась. Обратитесь к менеджеру",
            )
        if (
            payload.currency != instruction.currency
            or payload.amount > instruction.amount
        ):
            raise InstallerWorkspaceError(
                "collection_amount_invalid",
                "Сумма или валюта не соответствует поручению",
                400,
            )
        # The exact custody source is NUMERIC. Payment retains the existing
        # cent-compatible float transport/storage until its separate money migration.
        payment = Payment(
            order_id=order.id,
            amount=float(payload.amount),
            currency=payload.currency,
            type="postpayment",
            comment=f"Получено исполнителем #{auth.staff_user_id}",
        )
        session.add(payment)
        await session.flush()
        receipt = WorkerCashReceipt(
            account_id=account.id,
            tenant_id=scope.tenant_id,
            storefront_id=scope.storefront_id,
            order_id=order.id,
            assignment_reference=assignment.id,
            collection_version=instruction.version,
            amount=payload.amount,
            currency=payload.currency,
            title=assignment.title,
            payment_id=payment.id,
        )
        session.add(receipt)
        await OrderService._refresh_order_financials(session, order)
        session.add(order)
        await session.flush()
        # Only this known payment consumes the instruction. Unrelated concurrent
        # payment/price changes are serialized by Order and still invalidate it.
        order = await InstallerWorkspaceDAO.order(session, scope, order.id)
        refreshed = await Collection.snapshot(session, order)
        instruction.amount -= payload.amount
        instruction.version += 1
        instruction.financial_fingerprint = refreshed.fingerprint
        instruction.updated_at = datetime.now()
        session.add(instruction)
        return await cls.record(
            session,
            auth,
            scope,
            account,
            "client_received",
            assignment_id,
            payload,
            row=receipt,
            kind="client_receipt",
            status="recorded",
        )

    @classmethod
    async def create_handover(cls, session, auth, payload):
        scope, profile, account, staff, members = await cls.context(
            session,
            auth,
            mutation=True,
            extra_staff_ids=[payload.recipient_staff_user_id],
        )
        replay = await cls.replay(
            session, auth, account, "handover_created", profile.id, payload
        )
        if replay:
            return replay
        cls.check_version(account.version, payload.expected_version)
        recipient = staff.get(payload.recipient_staff_user_id)
        if (
            recipient is None
            or recipient.id == auth.staff_user_id
            or not manages_cash(members.get(recipient.id))
            or recipient.status != "active"
            or recipient.merged_into_staff_user_id is not None
            or recipient.must_change_password
        ):
            raise InstallerWorkspaceError(
                "recipient_unavailable", "Получатель денег недоступен", 400
            )
        available = [
            (row, Decimal(amount))
            for row, amount in await DAO.receipt_remainders(
                session, account.id, payload.currency
            )
        ]
        if sum((amount for _, amount in available), Decimal(0)) < payload.amount:
            raise InstallerWorkspaceError(
                "cash_insufficient", "Недостаточно свободных денег для передачи", 400
            )
        handover = WorkerCashHandover(
            account_id=account.id,
            tenant_id=scope.tenant_id,
            storefront_id=scope.storefront_id,
            recipient_staff_user_id=recipient.id,
            recipient_name=recipient.display_name,
            amount=payload.amount,
            currency=payload.currency,
        )
        session.add(handover)
        await session.flush()
        left = payload.amount
        for receipt, remaining in available:
            share = min(left, remaining)
            if share > 0:
                session.add(
                    WorkerCashHandoverAllocation(
                        handover_id=handover.id,
                        receipt_id=receipt.id,
                        account_id=account.id,
                        amount=share,
                    )
                )
                left -= share
            if not left:
                break
        return await cls.record(
            session,
            auth,
            scope,
            account,
            "handover_created",
            profile.id,
            payload,
            row=handover,
            kind="handover",
            status="pending",
        )

    @classmethod
    async def resolve_handover(
        cls, session, auth, handover_id, payload, *, profile_id=None, action
    ):
        manager = action in ("confirm", "reject")
        scope, profile, account, _, _ = await cls.context(
            session,
            auth,
            profile_id=profile_id,
            manager=manager,
            mutation=True,
            finance=manager,
        )
        replay = await cls.replay(
            session, auth, account, f"handover_{action}", handover_id, payload
        )
        if replay:
            return replay
        row = await DAO.handover(session, account.id, handover_id)
        if row is None:
            raise InstallerWorkspaceError(
                "handover_not_found", "Передача денег не найдена", 404
            )
        if action == "confirm" and row.recipient_staff_user_id != auth.staff_user_id:
            raise InstallerWorkspaceError(
                "recipient_required",
                "Получение подтверждает указанный получатель денег",
                403,
            )
        cls.check_version(row.version, payload.expected_version)
        if row.status != "pending":
            raise InstallerWorkspaceError(
                "handover_resolved", "Передача уже обработана"
            )
        row.status = {
            "confirm": "confirmed",
            "reject": "rejected",
            "cancel": "cancelled",
        }[action]
        row.version += 1
        row.resolved_at = datetime.now(timezone.utc)
        session.add(row)
        return await cls.record(
            session,
            auth,
            scope,
            account,
            f"handover_{action}",
            handover_id,
            payload,
            row=row,
            kind="handover",
            status=row.status,
        )

    @classmethod
    async def reverse_receipt(cls, session, auth, profile_id, receipt_id, payload):
        scope, _, account, _, _ = await cls.context(
            session,
            auth,
            profile_id=profile_id,
            manager=True,
            mutation=True,
            finance=True,
        )
        replay = await cls.replay(
            session, auth, account, "receipt_reversed", receipt_id, payload
        )
        if replay:
            return replay
        cls.check_version(account.version, payload.expected_version)
        receipt = await DAO.receipt(session, account.id, receipt_id)
        if receipt is None:
            raise InstallerWorkspaceError(
                "receipt_not_found", "Получение денег не найдено", 404
            )
        if receipt.reversed_at is not None:
            raise InstallerWorkspaceError(
                "receipt_already_reversed", "Получение денег уже исправлено"
            )
        available = {
            row.id: Decimal(amount)
            for row, amount in await DAO.receipt_remainders(
                session, account.id, receipt.currency
            )
        }
        if available.get(receipt.id) != receipt.amount:
            raise InstallerWorkspaceError(
                "receipt_cash_committed",
                "Деньги уже переданы или ожидают подтверждения передачи",
            )
        order = await InstallerWorkspaceDAO.order(
            session, scope, receipt.order_id, lock=True
        )
        if order is None:
            raise InstallerWorkspaceError("order_not_found", "Заказ не найден", 404)
        payment = Payment(
            order_id=receipt.order_id,
            amount=-float(receipt.amount),
            currency=receipt.currency,
            type="postpayment",
            comment=f"Исправление получения #{receipt.id}: {payload.reason}",
        )
        session.add(payment)
        await session.flush()
        receipt.reversal_payment_id = payment.id
        receipt.reversed_at = datetime.now(timezone.utc)
        receipt.reversal_reason = payload.reason
        session.add(receipt)
        await OrderService._refresh_order_financials(session, order)
        session.add(order)
        await session.flush()
        # Never silently republish a collection instruction after a correction.
        return await cls.record(
            session,
            auth,
            scope,
            account,
            "receipt_reversed",
            receipt_id,
            payload,
            row=receipt,
            kind="receipt_reversal",
            status="recorded",
        )
