"""Fresh authority, ordered account locks and durable command receipts."""

import hashlib
import json


from api_contracts.worker_money import WorkerMoneyCommandResult
from core.request_context import current_request_id
from crud.worker_money import WorkerMoneyDAO as DAO
from models import TenantAuditEvent
from models.worker_money import WorkerMoneyCommand
from services.installer_collection_service import InstallerWorkspaceError
from services.worker_assignment_service import WorkerAssignmentService as Assignments

MANAGE_CASH = "worker.money.manage"


def manages_cash(member):
    return bool(
        member
        and member.status == "active"
        and (
            member.role in ("owner", "admin")
            or (member.role == "manager" and MANAGE_CASH in (member.permissions or []))
        )
    )


class WorkerMoneyAccess:
    @classmethod
    async def context(
        cls,
        session,
        auth,
        *,
        profile_id=None,
        manager=False,
        mutation=False,
        finance=False,
        extra_staff_ids=(),
    ):
        scope = auth.tenant_scope()
        hint = (
            await DAO.profile(session, scope, profile_id=profile_id)
            if manager
            else None
        )
        scope, staff, members = await Assignments.identity_fence(
            session,
            auth,
            staff_ids=[
                *(extra_staff_ids or ()),
                *([hint.staff_user_id] if hint else []),
            ],
            mutation=mutation,
            manager=manager,
        )
        if finance and not manages_cash(members.get(auth.staff_user_id)):
            raise InstallerWorkspaceError(
                "money_access_denied", "Нет права проводить расчёты с монтажниками", 403
            )
        profile = (
            await DAO.profile(session, scope, profile_id=profile_id, lock=mutation)
            if manager
            else await DAO.profile(
                session, scope, staff_id=auth.staff_user_id, lock=mutation
            )
        )
        if (manager or mutation) and profile is None:
            raise InstallerWorkspaceError(
                "worker_not_found", "Исполнитель не найден", 404
            )
        if manager and not await DAO.profile_in_site(session, scope, profile.id):
            raise InstallerWorkspaceError(
                "worker_not_found", "Исполнитель не найден", 404
            )
        if mutation and not manager and profile.status != "active":
            raise InstallerWorkspaceError(
                "worker_disabled", "Профиль исполнителя отключён", 403
            )
        account = (
            await DAO.account(session, scope, profile.id, lock=mutation)
            if profile
            else None
        )
        return scope, profile, account, staff, members

    @staticmethod
    def check_version(actual, expected):
        if actual != expected:
            raise InstallerWorkspaceError(
                "money_changed", "Данные расчётов изменились. Обновите страницу"
            )

    @staticmethod
    def request_hash(action, target_id, payload):
        return hashlib.sha256(
            json.dumps(
                {
                    "action": action,
                    "target": target_id,
                    "payload": payload.model_dump(mode="json"),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

    @classmethod
    async def replay(cls, session, auth, account, action, target_id, payload):
        row = await DAO.command(session, account.id, payload.idempotency_key)
        if row is None:
            return None
        if (
            row.actor_staff_user_id != auth.staff_user_id
            or row.request_hash != cls.request_hash(action, target_id, payload)
        ):
            raise InstallerWorkspaceError(
                "idempotency_key_reused",
                "Ключ операции уже использован с другими данными",
            )
        return WorkerMoneyCommandResult.model_validate(row.result)

    @classmethod
    async def record(
        cls,
        session,
        auth,
        scope,
        account,
        action,
        target_id,
        payload,
        *,
        row,
        kind,
        status,
        audit_changes=None,
    ):
        account.version += 1
        session.add(account)
        await session.flush()
        result = WorkerMoneyCommandResult(
            id=row.id,
            kind=kind,
            status=status,
            version=getattr(row, "version", 0),
            account_version=account.version,
        )
        session.add(
            WorkerMoneyCommand(
                account_id=account.id,
                actor_staff_user_id=auth.staff_user_id,
                idempotency_key=str(payload.idempotency_key),
                request_hash=cls.request_hash(action, target_id, payload),
                result=result.model_dump(mode="json"),
            )
        )
        session.add(
            TenantAuditEvent(
                tenant_id=scope.tenant_id,
                storefront_id=scope.storefront_id,
                actor_staff_user_id=auth.staff_user_id,
                actor_username=auth.username,
                request_id=current_request_id(),
                action=f"worker_money.{action}",
                entity_type=kind,
                entity_id=row.id,
                change_set={
                    "account_id": account.id,
                    "worker_profile_id": account.worker_profile_id,
                    "account_version": account.version,
                    "amount": str(row.amount),
                    "currency": row.currency,
                    "status": status,
                    **(audit_changes or {}),
                    **(
                        {"reason": payload.reason} if hasattr(payload, "reason") else {}
                    ),
                },
            )
        )
        await session.flush()
        return result
