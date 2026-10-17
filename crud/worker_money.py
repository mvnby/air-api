"""Scoped cash persistence. Account UPDATE locks serialize all custody commands."""

from sqlalchemy import and_, exists, func, literal, or_, select, union_all

from models import OrderWorkAssignment, StaffUser, TenantMembership, TenantWorkerProfile
from models.worker_money import (
    WorkerCashAccount,
    WorkerCashHandover,
    WorkerCashHandoverAllocation,
    WorkerCashReceipt,
    WorkerMoneyCommand,
)


class WorkerMoneyDAO:
    @staticmethod
    async def profile_in_site(session, scope, profile_id):
        return bool(
            await session.scalar(
                select(
                    or_(
                        exists(
                            select(WorkerCashAccount.id).where(
                                WorkerCashAccount.worker_profile_id == profile_id,
                                WorkerCashAccount.tenant_id == scope.tenant_id,
                                WorkerCashAccount.storefront_id == scope.storefront_id,
                            )
                        ),
                        exists(
                            select(OrderWorkAssignment.id).where(
                                OrderWorkAssignment.worker_profile_id == profile_id,
                                OrderWorkAssignment.tenant_id == scope.tenant_id,
                                OrderWorkAssignment.storefront_id
                                == scope.storefront_id,
                            )
                        ),
                    )
                )
            )
        )

    @staticmethod
    async def profile(session, scope, *, profile_id=None, staff_id=None, lock=False):
        query = select(TenantWorkerProfile).where(
            TenantWorkerProfile.tenant_id == scope.tenant_id
        )
        query = (
            query.where(TenantWorkerProfile.id == profile_id)
            if profile_id is not None
            else query.where(TenantWorkerProfile.staff_user_id == staff_id)
        )
        return await session.scalar(
            (query.with_for_update(read=True) if lock else query).execution_options(
                populate_existing=True
            )
        )

    @staticmethod
    async def account(session, scope, profile_id, *, lock=False):
        if lock:
            dialect = session.get_bind().dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            await session.execute(
                insert(WorkerCashAccount)
                .values(
                    tenant_id=scope.tenant_id,
                    storefront_id=scope.storefront_id,
                    worker_profile_id=profile_id,
                    version=0,
                )
                .on_conflict_do_nothing(
                    index_elements=["worker_profile_id", "storefront_id"]
                )
            )
        query = select(WorkerCashAccount).where(
            WorkerCashAccount.tenant_id == scope.tenant_id,
            WorkerCashAccount.storefront_id == scope.storefront_id,
            WorkerCashAccount.worker_profile_id == profile_id,
        )
        return await session.scalar(
            (query.with_for_update() if lock else query).execution_options(
                populate_existing=True
            )
        )

    @staticmethod
    async def command(session, account_id, key):
        return await session.scalar(
            select(WorkerMoneyCommand).where(
                WorkerMoneyCommand.account_id == account_id,
                WorkerMoneyCommand.idempotency_key == str(key),
            )
        )

    @staticmethod
    async def receipt(session, account_id, receipt_id):
        return await session.scalar(
            select(WorkerCashReceipt)
            .where(
                WorkerCashReceipt.account_id == account_id,
                WorkerCashReceipt.id == receipt_id,
            )
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def handover(session, account_id, handover_id):
        return await session.scalar(
            select(WorkerCashHandover)
            .where(
                WorkerCashHandover.account_id == account_id,
                WorkerCashHandover.id == handover_id,
            )
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def receipt_remainders(session, account_id, currency):
        from models.worker_pay import WorkerPayPayout, WorkerPayOffsetCashAllocation

        used = (
            select(
                WorkerCashHandoverAllocation.receipt_id,
                func.sum(WorkerCashHandoverAllocation.amount).label("used"),
            )
            .join(
                WorkerCashHandover,
                WorkerCashHandover.id == WorkerCashHandoverAllocation.handover_id,
            )
            .where(
                WorkerCashHandover.account_id == account_id,
                WorkerCashHandover.status.in_(("pending", "confirmed")),
            )
            .group_by(WorkerCashHandoverAllocation.receipt_id)
            .subquery()
        )
        offsets = (
            select(
                WorkerPayOffsetCashAllocation.receipt_id,
                func.sum(WorkerPayOffsetCashAllocation.amount).label("used"),
            )
            .join(
                WorkerPayPayout,
                WorkerPayPayout.id == WorkerPayOffsetCashAllocation.payout_id,
            )
            .where(
                WorkerPayPayout.account_id == account_id,
                WorkerPayPayout.reversed_at.is_(None),
            )
            .group_by(WorkerPayOffsetCashAllocation.receipt_id)
            .subquery()
        )
        return (
            await session.execute(
                select(
                    WorkerCashReceipt,
                    (
                        WorkerCashReceipt.amount
                        - func.coalesce(used.c.used, 0)
                        - func.coalesce(offsets.c.used, 0)
                    ).label("remaining"),
                )
                .outerjoin(used, used.c.receipt_id == WorkerCashReceipt.id)
                .outerjoin(offsets, offsets.c.receipt_id == WorkerCashReceipt.id)
                .where(
                    WorkerCashReceipt.account_id == account_id,
                    WorkerCashReceipt.currency == currency,
                    WorkerCashReceipt.reversed_at.is_(None),
                )
                .order_by(WorkerCashReceipt.id)
            )
        ).all()

    @staticmethod
    async def balance_rows(session, account_id):
        receipts = (
            await session.execute(
                select(WorkerCashReceipt.currency, func.sum(WorkerCashReceipt.amount))
                .where(
                    WorkerCashReceipt.account_id == account_id,
                    WorkerCashReceipt.reversed_at.is_(None),
                )
                .group_by(WorkerCashReceipt.currency)
            )
        ).all()
        handovers = (
            await session.execute(
                select(
                    WorkerCashHandover.currency,
                    WorkerCashHandover.status,
                    func.sum(WorkerCashHandover.amount),
                )
                .where(
                    WorkerCashHandover.account_id == account_id,
                    WorkerCashHandover.status.in_(("pending", "confirmed")),
                )
                .group_by(WorkerCashHandover.currency, WorkerCashHandover.status)
            )
        ).all()
        return receipts, handovers

    @staticmethod
    async def offset_totals(session, account_id):
        from models.worker_pay import WorkerPayPayout

        return (
            await session.execute(
                select(WorkerPayPayout.currency, func.sum(WorkerPayPayout.amount))
                .where(
                    WorkerPayPayout.account_id == account_id,
                    WorkerPayPayout.method == "offset",
                    WorkerPayPayout.reversed_at.is_(None),
                )
                .group_by(WorkerPayPayout.currency)
            )
        ).all()

    @staticmethod
    async def journal(session, account_id, page, limit):
        from models.worker_pay import WorkerPayPayout

        events = union_all(
            select(
                literal("client_receipt").label("kind"),
                WorkerCashReceipt.id.label("id"),
                WorkerCashReceipt.created_at.label("date"),
            ).where(WorkerCashReceipt.account_id == account_id),
            select(
                literal("receipt_reversal"),
                WorkerCashReceipt.id,
                WorkerCashReceipt.reversed_at,
            ).where(
                WorkerCashReceipt.account_id == account_id,
                WorkerCashReceipt.reversed_at.is_not(None),
            ),
            select(
                literal("handover"),
                WorkerCashHandover.id,
                WorkerCashHandover.created_at,
            ).where(WorkerCashHandover.account_id == account_id),
            select(
                literal("handover_reversal"),
                WorkerCashHandover.id,
                WorkerCashHandover.reversed_at,
            ).where(
                WorkerCashHandover.account_id == account_id,
                WorkerCashHandover.reversed_at.is_not(None),
            ),
            select(
                literal("offset"), WorkerPayPayout.id, WorkerPayPayout.created_at
            ).where(
                WorkerPayPayout.account_id == account_id,
                WorkerPayPayout.method == "offset",
            ),
            select(
                literal("offset_reversal"),
                WorkerPayPayout.id,
                WorkerPayPayout.reversed_at,
            ).where(
                WorkerPayPayout.account_id == account_id,
                WorkerPayPayout.method == "offset",
                WorkerPayPayout.reversed_at.is_not(None),
            ),
        ).subquery()
        total = int(await session.scalar(select(func.count()).select_from(events)) or 0)
        rows = (
            await session.execute(
                select(events)
                .order_by(events.c.date.desc(), events.c.id.desc(), events.c.kind)
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        sources = {}
        for prefix, model in [
            ("receipt", WorkerCashReceipt),
            ("handover", WorkerCashHandover),
            ("offset", WorkerPayPayout),
        ]:
            ids = [
                row.id
                for row in rows
                if (row.kind.startswith("client") or row.kind.startswith("receipt"))
                and prefix == "receipt"
                or row.kind.startswith(prefix)
            ]
            sources[prefix] = (
                {
                    row.id: row
                    for row in (
                        await session.scalars(
                            select(model).where(
                                model.account_id == account_id, model.id.in_(ids)
                            )
                        )
                    ).all()
                }
                if ids
                else {}
            )
        return [
            (
                row.kind,
                sources[
                    "receipt"
                    if row.kind.startswith(("client", "receipt"))
                    else "handover"
                    if row.kind.startswith("handover")
                    else "offset"
                ][row.id],
            )
            for row in rows
        ], total

    @staticmethod
    async def profiles(session, scope, page, limit):
        query = (
            select(TenantWorkerProfile, StaffUser)
            .join(StaffUser, StaffUser.id == TenantWorkerProfile.staff_user_id)
            .where(
                TenantWorkerProfile.tenant_id == scope.tenant_id,
                or_(
                    exists(
                        select(WorkerCashAccount.id).where(
                            WorkerCashAccount.worker_profile_id
                            == TenantWorkerProfile.id,
                            WorkerCashAccount.storefront_id == scope.storefront_id,
                            WorkerCashAccount.tenant_id == scope.tenant_id,
                        )
                    ),
                    exists(
                        select(OrderWorkAssignment.id).where(
                            OrderWorkAssignment.worker_profile_id
                            == TenantWorkerProfile.id,
                            OrderWorkAssignment.storefront_id == scope.storefront_id,
                            OrderWorkAssignment.tenant_id == scope.tenant_id,
                        )
                    ),
                ),
            )
        )
        total = int(
            await session.scalar(select(func.count()).select_from(query.subquery()))
            or 0
        )
        rows = (
            await session.execute(
                query.order_by(StaffUser.display_name, TenantWorkerProfile.id)
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        return rows, total

    @staticmethod
    async def recipient_rows(session, scope):
        return (
            await session.execute(
                select(StaffUser, TenantMembership)
                .join(
                    TenantMembership,
                    and_(
                        TenantMembership.staff_user_id == StaffUser.id,
                        TenantMembership.tenant_id == scope.tenant_id,
                    ),
                )
                .where(
                    TenantMembership.status == "active",
                    TenantMembership.role.in_(("owner", "admin", "manager")),
                    StaffUser.status == "active",
                    StaffUser.merged_into_staff_user_id.is_(None),
                    StaffUser.must_change_password.is_(False),
                )
                .order_by(StaffUser.display_name, StaffUser.id)
            )
        ).all()
