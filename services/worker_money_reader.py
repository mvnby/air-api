"""Own financial history stays readable without restoring access to closed orders."""

from decimal import Decimal

from api_contracts.worker_money import (
    WorkerCashBalance,
    WorkerMoneyEntry,
    WorkerMoneyOverview,
    WorkerMoneyOverviewItem,
    WorkerMoneyRecipient,
    WorkerMoneyRecipients,
    WorkerMoneyWorkspace,
)
from crud.worker_money import WorkerMoneyDAO as DAO
from models import StaffUser
from services.worker_money_access import WorkerMoneyAccess, manages_cash


class WorkerMoneyReader(WorkerMoneyAccess):
    @staticmethod
    async def balances(session, account):
        if account is None:
            return []
        receipts, handovers = await DAO.balance_rows(session, account.id)
        buckets = {}
        for currency, amount in receipts:
            buckets.setdefault(currency, {})["received"] = Decimal(amount)
        for currency, status, amount in handovers:
            buckets.setdefault(currency, {})[status] = Decimal(amount)
        result = []
        for currency, values in sorted(buckets.items()):
            received = values.get("received", Decimal(0))
            handed = values.get("confirmed", Decimal(0))
            pending = values.get("pending", Decimal(0))
            result.append(
                WorkerCashBalance(
                    currency=currency,
                    received=f"{received:.2f}",
                    handed_over=f"{handed:.2f}",
                    held=f"{received - handed:.2f}",
                    pending=f"{pending:.2f}",
                    available=f"{received - handed - pending:.2f}",
                )
            )
        return result

    @classmethod
    async def workspace(
        cls, session, auth, *, profile_id=None, manager=False, page=1, limit=50
    ):
        scope, profile, account, staff, members = await cls.context(
            session, auth, profile_id=profile_id, manager=manager
        )
        person = (
            await session.get(StaffUser, profile.staff_user_id)
            if profile
            else staff[auth.staff_user_id]
        )
        can_manage = manager and manages_cash(members.get(auth.staff_user_id))
        events, total = (
            await DAO.journal(session, account.id, page, limit) if account else ([], 0)
        )
        remaining = {}
        if can_manage:
            for currency in {
                row.currency for kind, row in events if kind == "client_receipt"
            }:
                remaining.update(
                    {
                        row.id: Decimal(amount)
                        for row, amount in await DAO.receipt_remainders(
                            session, account.id, currency
                        )
                    }
                )
        items = []
        for kind, row in events:
            if kind == "handover":
                items.append(
                    WorkerMoneyEntry(
                        id=row.id,
                        kind=kind,
                        status=row.status,
                        amount=f"{row.amount:.2f}",
                        currency=row.currency,
                        created_at=row.created_at,
                        recipient_staff_user_id=row.recipient_staff_user_id,
                        recipient_name=row.recipient_name,
                        version=row.version,
                    )
                )
            else:
                items.append(
                    WorkerMoneyEntry(
                        id=row.id,
                        kind=kind,
                        status="recorded"
                        if kind == "receipt_reversal" or row.reversed_at is None
                        else "reversed",
                        amount=f"{row.amount:.2f}",
                        currency=row.currency,
                        created_at=row.reversed_at
                        if kind == "receipt_reversal"
                        else row.created_at,
                        order_id=row.order_id,
                        title=row.title,
                        can_reverse=bool(
                            can_manage
                            and kind == "client_receipt"
                            and row.reversed_at is None
                            and remaining.get(row.id) == row.amount
                        ),
                    )
                )
        return WorkerMoneyWorkspace(
            worker_profile_id=profile.id if profile else None,
            staff_user_id=person.id,
            display_name=person.display_name,
            version=account.version if account else 0,
            can_manage=can_manage,
            balances=await cls.balances(session, account),
            items=items,
            total=total,
            page=page,
            limit=limit,
        )

    @classmethod
    async def overview(cls, session, auth, page=1, limit=50):
        from services.worker_assignment_service import WorkerAssignmentService

        scope, _, members = await WorkerAssignmentService.identity_fence(
            session, auth, manager=True
        )
        rows, total = await DAO.profiles(session, scope, page, limit)
        items = []
        for profile, person in rows:
            account = await DAO.account(session, scope, profile.id)
            items.append(
                WorkerMoneyOverviewItem(
                    worker_profile_id=profile.id,
                    staff_user_id=person.id,
                    display_name=person.display_name,
                    balances=await cls.balances(session, account),
                )
            )
        return WorkerMoneyOverview(
            items=items,
            total=total,
            page=page,
            limit=limit,
            can_manage=manages_cash(members.get(auth.staff_user_id)),
        )

    @classmethod
    async def recipients(cls, session, auth, page=1, limit=50):
        scope, _, _, _, _ = await cls.context(session, auth)
        rows = [
            (person, member)
            for person, member in await DAO.recipient_rows(session, scope)
            if person.id != auth.staff_user_id and manages_cash(member)
        ]
        return WorkerMoneyRecipients(
            items=[
                WorkerMoneyRecipient(
                    staff_user_id=person.id, display_name=person.display_name
                )
                for person, _ in rows[(page - 1) * limit : page * limit]
            ],
            total=len(rows),
            page=page,
            limit=limit,
        )
