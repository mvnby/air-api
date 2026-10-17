"""Live remuneration permission independent of CRM/cash authority."""

from services.worker_money_access import WorkerMoneyAccess, manages_cash
from services.installer_collection_service import InstallerWorkspaceError


def manages_pay(member):
    return bool(
        member
        and member.status == "active"
        and (
            member.role in ("owner", "admin")
            or (
                member.role == "manager"
                and "worker.pay.manage" in (member.permissions or [])
            )
        )
    )


class WorkerPayAccess(WorkerMoneyAccess):
    @staticmethod
    def require_manager_read(auth, members):
        if not manages_pay(members.get(auth.staff_user_id)) and not (
            auth.access_kind == "platform_support" and auth.is_platform_owner
        ):
            raise InstallerWorkspaceError(
                "pay_access_denied", "Нет права просматривать оплату труда", 403
            )

    @classmethod
    async def pay_context(
        cls,
        session,
        auth,
        *,
        profile_id=None,
        mutation=False,
        manager=False,
        offset=False,
    ):
        result = await cls.context(
            session, auth, profile_id=profile_id, manager=manager, mutation=mutation
        )
        member = result[4].get(auth.staff_user_id)
        support = bool(
            manager
            and not mutation
            and auth.access_kind == "platform_support"
            and auth.is_platform_owner
        )
        if manager and not manages_pay(member) and not support:
            raise InstallerWorkspaceError(
                "pay_access_denied", "Нет права проводить оплату труда", 403
            )
        if offset and not manages_cash(member):
            raise InstallerWorkspaceError(
                "money_access_denied",
                "Для зачёта нужно право расчётов с деньгами исполнителя",
                403,
            )
        return result
