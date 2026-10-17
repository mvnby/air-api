"""Safe personal obligations and bounded manager pay projections."""

from decimal import Decimal

from api_contracts.worker_pay import (
    ManagerWorkerPayAgreementItem,
    ManagerWorkerPayWorkspace,
    WorkerPayAgreementItem,
    WorkerPayBalance,
    WorkerPayCandidate,
    WorkerPayEntry,
    WorkerPayOrderWorkspace,
    WorkerPayOverview,
    WorkerPayOverviewItem,
    WorkerPayWorkspace,
)
from crud.installer_workspace import InstallerWorkspaceDAO
from crud.worker_money import WorkerMoneyDAO as CashDAO
from crud.worker_pay import WorkerPayDAO as DAO
from models import StaffUser
from models.worker_money import WorkerCashAccount
from services.installer_collection_service import InstallerWorkspaceError
from services.worker_assignment_access_service import WorkerAssignmentAccessService
from services.worker_assignment_service import WorkerAssignmentService
from services.worker_money_access import manages_cash
from services.worker_pay_access import WorkerPayAccess, manages_pay


class WorkerPayReader(WorkerPayAccess):
    @staticmethod
    def agreement_item(row, paid, profile_id, *, manager=False):
        paid = Decimal(paid or 0)
        values = dict(
            id=row.id,
            worker_profile_id=profile_id,
            order_id=row.order_id,
            assignment_reference=row.assignment_reference,
            work_stage_id=row.work_stage_id,
            work_key=row.work_key,
            title=row.title,
            amount=f"{row.amount:.2f}",
            currency=row.currency,
            status=row.status,
            version=row.version,
            paid=f"{paid:.2f}",
            owed=f"{max(Decimal(0), row.amount - paid) if row.status == 'accrued' else Decimal(0):.2f}",
            created_at=row.created_at,
        )
        if manager:
            return ManagerWorkerPayAgreementItem(
                **values, cost_byn_amount=f"{row.cost_byn_amount:.2f}"
            )
        return WorkerPayAgreementItem(**values)

    @classmethod
    async def balances(cls, session, account):
        if account is None:
            return []
        rows = await DAO.agreements(session, account.id)
        paid = await DAO.paid_map(session, account.id)
        buckets = {}
        for row in rows:
            if row.status == "cancelled":
                continue
            bucket = buckets.setdefault(
                row.currency, [Decimal(0), Decimal(0), Decimal(0)]
            )
            bucket[0] += row.amount
            if row.status == "accrued":
                bucket[1] += row.amount
                bucket[2] += Decimal(paid.get(row.id, 0))
        return [
            WorkerPayBalance(
                currency=currency,
                agreed=f"{values[0]:.2f}",
                accrued=f"{values[1]:.2f}",
                paid=f"{values[2]:.2f}",
                owed=f"{values[1] - values[2]:.2f}",
            )
            for currency, values in sorted(buckets.items())
        ]

    @classmethod
    async def workspace(
        cls, session, auth, *, profile_id=None, manager=False, page=1, limit=50
    ):
        _, profile, account, staff, members = await cls.pay_context(
            session, auth, profile_id=profile_id, manager=manager
        )
        person = (
            await session.get(StaffUser, profile.staff_user_id)
            if profile
            else staff[auth.staff_user_id]
        )
        can_manage = bool(manager and manages_pay(members.get(auth.staff_user_id)))
        paid = await DAO.paid_map(session, account.id) if account else {}
        agreements = await DAO.agreements(session, account.id) if account else []
        payouts = await DAO.payouts(session, account.id) if account else []
        events = []
        for row in payouts:
            kind = "offset" if row.method == "offset" else "payout"
            events.append(
                WorkerPayEntry(
                    id=row.id,
                    kind=kind,
                    status="reversed" if row.reversed_at else "recorded",
                    amount=f"{row.amount:.2f}",
                    currency=row.currency,
                    method=row.method,
                    created_at=row.created_at,
                    version=row.version,
                    can_reverse=bool(
                        can_manage
                        and row.reversed_at is None
                        and (
                            row.method != "offset"
                            or manages_cash(members.get(auth.staff_user_id))
                        )
                    ),
                )
            )
            if row.reversed_at:
                events.append(
                    WorkerPayEntry(
                        id=row.id,
                        kind=f"{kind}_reversal",
                        status="recorded",
                        amount=f"{row.amount:.2f}",
                        currency=row.currency,
                        method=row.method,
                        created_at=row.reversed_at,
                        version=row.version,
                    )
                )
        events.sort(key=lambda row: (row.created_at, row.id, row.kind), reverse=True)
        result = ManagerWorkerPayWorkspace if manager else WorkerPayWorkspace
        return result(
            worker_profile_id=profile.id if profile else None,
            staff_user_id=person.id,
            display_name=person.display_name,
            version=account.version if account else 0,
            can_manage=can_manage,
            can_offset=bool(
                can_manage and manages_cash(members.get(auth.staff_user_id))
            ),
            balances=await cls.balances(session, account),
            agreements=[
                cls.agreement_item(
                    row, paid.get(row.id, 0), profile.id, manager=manager
                )
                for row in agreements[(page - 1) * limit : page * limit]
            ],
            items=events[(page - 1) * limit : page * limit],
            total=max(len(events), len(agreements)),
            page=page,
            limit=limit,
        )

    @classmethod
    async def overview(cls, session, auth, page=1, limit=50):
        scope, _, members = await WorkerAssignmentService.identity_fence(
            session, auth, manager=True
        )
        cls.require_manager_read(auth, members)
        rows, total = await CashDAO.profiles(session, scope, page, limit)
        member = members.get(auth.staff_user_id)
        items = []
        for profile, person in rows:
            account = await CashDAO.account(session, scope, profile.id)
            items.append(
                WorkerPayOverviewItem(
                    worker_profile_id=profile.id,
                    staff_user_id=person.id,
                    display_name=person.display_name,
                    balances=await cls.balances(session, account),
                )
            )
        return WorkerPayOverview(
            items=items,
            total=total,
            page=page,
            limit=limit,
            can_manage=manages_pay(member),
            can_offset=manages_pay(member) and manages_cash(member),
        )

    @classmethod
    async def order_workspace(cls, session, auth, order_id):
        scope, _, members = await WorkerAssignmentService.identity_fence(
            session, auth, manager=True
        )
        cls.require_manager_read(auth, members)
        order = await InstallerWorkspaceDAO.order(session, scope, order_id)
        if order is None:
            raise InstallerWorkspaceError("order_not_found", "Заказ не найден", 404)
        candidates = []
        # The public assignment ACL supplies the same lifecycle/membership fence;
        # its identity is immutable and no finance permission grants work access.
        from dataclasses import replace

        for assignment, profile, person in await DAO.candidates(
            session, scope, order_id
        ):
            candidate_auth = replace(
                auth,
                staff_user_id=person.id,
                auth_version=person.auth_version,
                username=person.username or "",
                access_kind="membership",
                is_platform_owner=False,
            )
            if (
                await WorkerAssignmentAccessService.get_for_actor(
                    session, candidate_auth, assignment.id
                )
                is None
            ):
                continue
            account = await CashDAO.account(session, scope, profile.id)
            candidates.append(
                WorkerPayCandidate(
                    assignment_id=assignment.id,
                    worker_profile_id=profile.id,
                    staff_user_id=person.id,
                    display_name=person.display_name,
                    title=assignment.title,
                    work_stage_id=assignment.work_stage_id,
                    account_version=account.version if account else 0,
                )
            )
        rows = await DAO.order_agreements(session, scope, order_id)
        agreements = []
        for row in rows:
            account = await session.get(WorkerCashAccount, row.account_id)
            paid = await DAO.paid_map(session, row.account_id)
            agreements.append(
                cls.agreement_item(
                    row, paid.get(row.id, 0), account.worker_profile_id, manager=True
                )
            )
        return WorkerPayOrderWorkspace(
            order_id=order_id,
            candidates=candidates,
            agreements=agreements,
            can_manage=manages_pay(members.get(auth.staff_user_id)),
        )
