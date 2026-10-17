"""Atomic commitments, accrual and explicit cash/pay settlements."""

from dataclasses import replace
from decimal import Decimal

from sqlalchemy import select

from crud.installer_workspace import InstallerWorkspaceDAO
from crud.worker_money import WorkerMoneyDAO as CashDAO
from crud.worker_pay import WorkerPayDAO as DAO
from models import OrderInstaller, OrderWorkAssignment
from models.worker_money import now
from models.worker_pay import (
    WorkerPayAgreement,
    WorkerPayPayout,
    WorkerPayPayoutAllocation,
    WorkerPayOffsetCashAllocation,
)
from services.installer_collection_service import InstallerWorkspaceError
from services.order_service import OrderService
from services.worker_assignment_access_service import WorkerAssignmentAccessService
from services.worker_pay_reader import WorkerPayReader


class WorkerPayService(WorkerPayReader):
    @staticmethod
    def audit_snapshot(row):
        return dict(
            amount=f"{row.amount:.2f}",
            currency=row.currency,
            cost_byn_amount=f"{row.cost_byn_amount:.2f}",
            status=row.status,
            version=row.version,
            assignment_reference=row.assignment_reference,
            title=row.title,
        )

    @staticmethod
    def frozen_cost(payload):
        if payload.currency == "BYN":
            if (
                payload.cost_byn_amount is not None
                and payload.cost_byn_amount != payload.amount
            ):
                raise InstallerWorkspaceError(
                    "pay_cost_invalid",
                    "Для BYN себестоимость равна согласованной сумме",
                    400,
                )
            return payload.amount
        if payload.cost_byn_amount is None:
            raise InstallerWorkspaceError(
                "pay_cost_required",
                "Подтвердите себестоимость в BYN для валютного соглашения",
                400,
            )
        return payload.cost_byn_amount

    @staticmethod
    async def refresh_cost(session, scope, order):
        await session.flush()
        order.worker_pay_cost_byn = Decimal(
            await DAO.order_cost(session, scope, order.id)
        )
        session.add(order)
        await session.flush()
        await OrderService._refresh_order_financials(session, order)
        session.add(order)
        await session.flush()

    @classmethod
    async def create_agreement(cls, session, auth, order_id, payload):
        scope = auth.tenant_scope()
        hint = await session.scalar(
            select(OrderWorkAssignment).where(
                OrderWorkAssignment.id == payload.assignment_id,
                OrderWorkAssignment.order_id == order_id,
                OrderWorkAssignment.tenant_id == scope.tenant_id,
                OrderWorkAssignment.storefront_id == scope.storefront_id,
            )
        )
        if hint is None:
            raise InstallerWorkspaceError("work_not_found", "Работа не найдена", 404)
        scope, profile, account, staff, _ = await cls.pay_context(
            session,
            auth,
            profile_id=hint.worker_profile_id,
            manager=True,
            mutation=True,
        )
        replay = await cls.replay(
            session, auth, account, "pay_agreed", order_id, payload
        )
        if replay:
            return replay
        cls.check_version(account.version, payload.expected_version)
        person = staff[profile.staff_user_id]
        candidate = replace(
            auth,
            staff_user_id=person.id,
            username=person.username or "",
            auth_version=person.auth_version,
            access_kind="membership",
            is_platform_owner=False,
        )
        assignment = await WorkerAssignmentAccessService.get_for_actor(
            session, candidate, payload.assignment_id, for_update=True
        )
        if assignment is None:
            raise InstallerWorkspaceError("work_not_found", "Работа не найдена", 404)
        order = await InstallerWorkspaceDAO.order(session, scope, order_id, lock=True)
        if order is None:
            raise InstallerWorkspaceError("order_not_found", "Заказ не найден", 404)
        legacy_id = profile.canonical_legacy_installer_id or person.legacy_installer_id
        if legacy_id and await session.scalar(
            select(OrderInstaller.order_id).where(
                OrderInstaller.order_id == order_id,
                OrderInstaller.installer_id == legacy_id,
                OrderInstaller.agreed_pay > 0,
            )
        ):
            raise InstallerWorkspaceError(
                "legacy_pay_conflict",
                "Для этого исполнителя уже согласована оплата в прежнем учёте",
                409,
            )
        work_key = (
            f"stage:{assignment.work_stage_id}"
            if assignment.work_stage_id is not None
            else "order"
        )
        if await session.scalar(
            select(WorkerPayAgreement.id).where(
                WorkerPayAgreement.account_id == account.id,
                WorkerPayAgreement.order_id == order_id,
                WorkerPayAgreement.work_key == work_key,
                WorkerPayAgreement.status != "cancelled",
            )
        ):
            raise InstallerWorkspaceError(
                "pay_already_agreed", "Оплата этой работы уже согласована"
            )
        row = WorkerPayAgreement(
            account_id=account.id,
            tenant_id=scope.tenant_id,
            storefront_id=scope.storefront_id,
            order_id=order_id,
            assignment_reference=assignment.id,
            work_stage_id=assignment.work_stage_id,
            work_key=work_key,
            title=assignment.title,
            amount=payload.amount,
            currency=payload.currency,
            cost_byn_amount=cls.frozen_cost(payload),
        )
        session.add(row)
        await cls.refresh_cost(session, scope, order)
        return await cls.record(
            session,
            auth,
            scope,
            account,
            "pay_agreed",
            order_id,
            payload,
            row=row,
            kind="agreement",
            status=row.status,
            audit_changes={"before": None, "after": cls.audit_snapshot(row)},
        )

    @classmethod
    async def change_agreement(
        cls, session, auth, profile_id, agreement_id, payload, *, action
    ):
        scope, _, account, _, _ = await cls.pay_context(
            session, auth, profile_id=profile_id, manager=True, mutation=True
        )
        replay = await cls.replay(
            session, auth, account, f"pay_{action}", agreement_id, payload
        )
        if replay:
            return replay
        cls.check_version(account.version, payload.expected_version)
        row = await DAO.agreement(session, account.id, agreement_id)
        if row is None:
            raise InstallerWorkspaceError(
                "agreement_not_found", "Соглашение не найдено", 404
            )
        cls.check_version(row.version, payload.expected_agreement_version)
        if row.status == "cancelled" or (action != "cancel" and row.status != "agreed"):
            raise InstallerWorkspaceError(
                "agreement_state_changed", "Состояние соглашения изменилось"
            )
        before = cls.audit_snapshot(row)
        order = await InstallerWorkspaceDAO.order(
            session, scope, row.order_id, lock=True
        )
        if order is None:
            raise InstallerWorkspaceError("order_not_found", "Заказ не найден", 404)
        if action == "revise":
            row.amount, row.currency, row.cost_byn_amount = (
                payload.amount,
                payload.currency,
                cls.frozen_cost(payload),
            )
        elif action == "accrue":
            row.status, row.accrued_at = "accrued", now()
        elif action == "cancel":
            paid = await DAO.paid_map(session, account.id)
            if Decimal(paid.get(row.id, 0)) > 0:
                raise InstallerWorkspaceError(
                    "agreement_already_paid", "Сначала отмените выплаты по соглашению"
                )
            row.status, row.cancelled_at, row.cancellation_reason = (
                "cancelled",
                now(),
                payload.reason,
            )
        row.version += 1
        session.add(row)
        if action != "accrue":
            await cls.refresh_cost(session, scope, order)
        return await cls.record(
            session,
            auth,
            scope,
            account,
            f"pay_{action}",
            agreement_id,
            payload,
            row=row,
            kind="agreement",
            status=row.status,
            audit_changes={"before": before, "after": cls.audit_snapshot(row)},
        )

    @classmethod
    async def create_payout(cls, session, auth, profile_id, payload, *, offset=False):
        scope, _, account, _, _ = await cls.pay_context(
            session,
            auth,
            profile_id=profile_id,
            manager=True,
            mutation=True,
            offset=offset,
        )
        action = "pay_offset" if offset else "pay_payout"
        replay = await cls.replay(session, auth, account, action, profile_id, payload)
        if replay:
            return replay
        cls.check_version(account.version, payload.expected_version)
        paid = await DAO.paid_map(session, account.id)
        available = [
            (row, row.amount - Decimal(paid.get(row.id, 0)))
            for row in await DAO.agreements(session, account.id)
            if row.status == "accrued" and row.currency == payload.currency
        ]
        if sum((amount for _, amount in available), Decimal(0)) < payload.amount:
            raise InstallerWorkspaceError(
                "pay_insufficient", "Сумма превышает начисленную задолженность", 400
            )
        cash = (
            await CashDAO.receipt_remainders(session, account.id, payload.currency)
            if offset
            else []
        )
        if (
            offset
            and sum((Decimal(amount) for _, amount in cash), Decimal(0))
            < payload.amount
        ):
            raise InstallerWorkspaceError(
                "cash_insufficient",
                "Недостаточно свободных денег этой валюты для зачёта",
                400,
            )
        row = WorkerPayPayout(
            account_id=account.id,
            tenant_id=scope.tenant_id,
            storefront_id=scope.storefront_id,
            amount=payload.amount,
            currency=payload.currency,
            method="offset" if offset else payload.method,
        )
        session.add(row)
        await session.flush()
        left = payload.amount
        for agreement, remaining in available:
            share = min(left, remaining)
            if share > 0:
                session.add(
                    WorkerPayPayoutAllocation(
                        payout_id=row.id,
                        agreement_id=agreement.id,
                        account_id=account.id,
                        amount=share,
                    )
                )
                left -= share
            if not left:
                break
        left = payload.amount
        for receipt, remaining in cash:
            share = min(left, Decimal(remaining))
            if share > 0:
                session.add(
                    WorkerPayOffsetCashAllocation(
                        payout_id=row.id,
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
            action,
            profile_id,
            payload,
            row=row,
            kind="offset" if offset else "payout",
            status="recorded",
        )

    @classmethod
    async def reverse_payout(cls, session, auth, profile_id, payout_id, payload):
        # Hint determines only whether both finance grants are needed. The row is
        # reloaded after account locking before its state can be changed.
        from models.worker_money import WorkerCashAccount

        hint = await session.scalar(
            select(WorkerPayPayout)
            .join(WorkerCashAccount, WorkerCashAccount.id == WorkerPayPayout.account_id)
            .where(
                WorkerPayPayout.id == payout_id,
                WorkerCashAccount.worker_profile_id == profile_id,
                WorkerCashAccount.tenant_id == auth.tenant_id,
                WorkerCashAccount.storefront_id == auth.storefront_id,
            )
        )
        scope, _, account, _, _ = await cls.pay_context(
            session,
            auth,
            profile_id=profile_id,
            manager=True,
            mutation=True,
            offset=bool(hint and hint.method == "offset"),
        )
        replay = await cls.replay(
            session, auth, account, "pay_reversed", payout_id, payload
        )
        if replay:
            return replay
        cls.check_version(account.version, payload.expected_version)
        row = await DAO.payout(session, account.id, payout_id)
        if row is None:
            raise InstallerWorkspaceError("payout_not_found", "Выплата не найдена", 404)
        if row.reversed_at is not None:
            raise InstallerWorkspaceError(
                "payout_already_reversed", "Выплата уже отменена"
            )
        row.reversed_at, row.reversal_reason = now(), payload.reason
        row.version += 1
        session.add(row)
        return await cls.record(
            session,
            auth,
            scope,
            account,
            "pay_reversed",
            payout_id,
            payload,
            row=row,
            kind="offset_reversal" if row.method == "offset" else "payout_reversal",
            status="recorded",
        )
