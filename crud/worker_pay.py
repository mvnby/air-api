"""Exact scoped pay persistence; caller holds shared cash-account mutex."""

from sqlalchemy import func, select

from models import OrderWorkAssignment, StaffUser, TenantWorkerProfile
from models.worker_pay import (
    WorkerPayAgreement,
    WorkerPayPayout,
    WorkerPayPayoutAllocation,
)


class WorkerPayDAO:
    @staticmethod
    async def agreement(session, account_id, agreement_id):
        return await session.scalar(
            select(WorkerPayAgreement)
            .where(
                WorkerPayAgreement.account_id == account_id,
                WorkerPayAgreement.id == agreement_id,
            )
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def payout(session, account_id, payout_id):
        return await session.scalar(
            select(WorkerPayPayout)
            .where(
                WorkerPayPayout.account_id == account_id,
                WorkerPayPayout.id == payout_id,
            )
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def paid_map(session, account_id):
        return dict(
            (
                await session.execute(
                    select(
                        WorkerPayPayoutAllocation.agreement_id,
                        func.sum(WorkerPayPayoutAllocation.amount),
                    )
                    .join(
                        WorkerPayPayout,
                        WorkerPayPayout.id == WorkerPayPayoutAllocation.payout_id,
                    )
                    .where(
                        WorkerPayPayout.account_id == account_id,
                        WorkerPayPayout.reversed_at.is_(None),
                    )
                    .group_by(WorkerPayPayoutAllocation.agreement_id)
                )
            ).all()
        )

    @staticmethod
    async def agreements(session, account_id):
        return list(
            (
                await session.scalars(
                    select(WorkerPayAgreement)
                    .where(WorkerPayAgreement.account_id == account_id)
                    .order_by(WorkerPayAgreement.id)
                )
            ).all()
        )

    @staticmethod
    async def payouts(session, account_id):
        return list(
            (
                await session.scalars(
                    select(WorkerPayPayout)
                    .where(WorkerPayPayout.account_id == account_id)
                    .order_by(WorkerPayPayout.id.desc())
                )
            ).all()
        )

    @staticmethod
    async def order_agreements(session, scope, order_id):
        return list(
            (
                await session.scalars(
                    select(WorkerPayAgreement)
                    .where(
                        WorkerPayAgreement.order_id == order_id,
                        WorkerPayAgreement.tenant_id == scope.tenant_id,
                        WorkerPayAgreement.storefront_id == scope.storefront_id,
                    )
                    .order_by(WorkerPayAgreement.id)
                )
            ).all()
        )

    @staticmethod
    async def candidates(session, scope, order_id):
        return (
            await session.execute(
                select(OrderWorkAssignment, TenantWorkerProfile, StaffUser)
                .join(
                    TenantWorkerProfile,
                    TenantWorkerProfile.id == OrderWorkAssignment.worker_profile_id,
                )
                .join(StaffUser, StaffUser.id == TenantWorkerProfile.staff_user_id)
                .where(
                    OrderWorkAssignment.tenant_id == scope.tenant_id,
                    OrderWorkAssignment.storefront_id == scope.storefront_id,
                    OrderWorkAssignment.order_id == order_id,
                    OrderWorkAssignment.revoked_at.is_(None),
                    TenantWorkerProfile.status == "active",
                    StaffUser.status == "active",
                    StaffUser.merged_into_staff_user_id.is_(None),
                )
                .order_by(OrderWorkAssignment.id)
            )
        ).all()

    @staticmethod
    async def order_cost(session, scope, order_id):
        return await session.scalar(
            select(
                func.coalesce(func.sum(WorkerPayAgreement.cost_byn_amount), 0)
            ).where(
                WorkerPayAgreement.tenant_id == scope.tenant_id,
                WorkerPayAgreement.storefront_id == scope.storefront_id,
                WorkerPayAgreement.order_id == order_id,
                WorkerPayAgreement.status != "cancelled",
            )
        )
