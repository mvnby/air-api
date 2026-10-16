"""Assign one actual company staff member without changing installation ownership."""

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.order_responsibility import ManagerOrderResponsiblePerson, ManagerOrderResponsiblesResponse
from core.request_context import current_request_id
from crud.order_responsibility import ELIGIBLE_ROLES, OrderResponsibilityDAO
from models import TenantAuditEvent
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.staff_avatar_service import staff_avatar_url
from services.staff_user_service import StaffUserService


class OrderResponsibilityError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code, self.status_code = code, status_code


class OrderResponsibilityService:
    @staticmethod
    def _eligible(staff, membership) -> bool:
        return bool(staff is not None and StaffUserService.is_active(staff)
            and membership is not None and membership.status == "active"
            and membership.role in ELIGIBLE_ROLES)

    @staticmethod
    def _person(row):
        return ManagerOrderResponsiblePerson(
            staff_user_id=row.id, display_name=row.display_name,
            avatar_url=staff_avatar_url(SimpleNamespace(id=row.id, avatar_version=row.avatar_version), tenant_id=row.tenant_id),
            is_active=(row.staff_status == "active" and row.merged_into_staff_user_id is None
                       and row.membership_status == "active" and row.role in ELIGIBLE_ROLES),
        )

    @classmethod
    async def person_map(cls, session: AsyncSession, orders):
        """One minimal batched lookup; preserve historical identities, never aliases."""
        orders = list(orders)
        pairs = {(order.tenant_id, order.responsible_staff_user_id) for order in orders
                 if order.responsible_staff_user_id is not None}
        people = {(row.tenant_id, row.id): cls._person(row)
                  for row in await OrderResponsibilityDAO.people(session, pairs)}
        return {order.id: people.get((order.tenant_id, order.responsible_staff_user_id)) for order in orders}

    @classmethod
    async def _fence(cls, session, scope, staff_ids, *, mutation, lock=True):
        # Must run before receipt/Customer/Order INSERTs, including nested commands.
        # Tenant SHARE conflicts with staff administration's parent UPDATE lock.
        state = await LegacyOwnerAuthGuard.state(session, for_share=lock)
        tenant, site, staff, memberships = await OrderResponsibilityDAO.context(session, scope, staff_ids, lock=lock)
        if tenant is None or tenant.status != "active" or site is None or site.status != "active":
            raise OrderResponsibilityError("company_access_changed", "Компания или витрина недоступна", 403)
        if mutation and tenant.demo_read_only:
            raise OrderResponsibilityError("demo_read_only", "Демонстрационная компания доступна только для чтения", 403)
        return state, staff, memberships

    @classmethod
    async def initial_responsible(cls, session: AsyncSession, scope, creator_staff_user_id: int | None) -> int | None:
        """Allocation eligibility only; caller provides verified identity and owns commit.

        Invoke before the first child FK/receipt write. This is not authentication:
        it neither upgrades credential snapshots nor creates virtual memberships.
        """
        if creator_staff_user_id is None:
            return None
        _, staff, memberships = await cls._fence(session, scope, [creator_staff_user_id], mutation=True)
        return creator_staff_user_id if cls._eligible(staff.get(creator_staff_user_id), memberships.get(creator_staff_user_id)) else None

    @classmethod
    async def _actor_fence(cls, session, auth, *, candidate_id=None, mutation):
        if auth.staff_user_id is None:
            raise OrderResponsibilityError("staff_account_required", "Нужна учётная запись сотрудника", 403)
        scope = auth.tenant_scope()
        state, staff, memberships = await cls._fence(session, scope, [auth.staff_user_id, candidate_id], mutation=mutation, lock=mutation)
        actor = staff.get(auth.staff_user_id)
        if (actor is None or not StaffUserService.is_active(actor) or actor.must_change_password
                or actor.auth_version != auth.auth_version
                or not LegacyOwnerAuthGuard.allows_staff_identity(state, staff_user_id=auth.staff_user_id, username=actor.username or "")):
            raise OrderResponsibilityError("staff_access_changed", "Доступ сотрудника изменён. Войдите повторно", 403)
        bound = LegacyOwnerAuthGuard.allows_bound_staff(state, staff_user_id=auth.staff_user_id)
        if bound and not await LegacyOwnerManagedIdentityService.exact_bound_staff_identity_allowed(session, state=state, user=actor):
            raise OrderResponsibilityError("staff_access_changed", "Профиль владельца недоступен", 403)
        member = memberships.get(auth.staff_user_id)
        actual = cls._eligible(actor, member)
        support = auth.access_kind == "platform_support" and auth.is_platform_owner and bound
        if not actual and not support:
            raise OrderResponsibilityError("responsible_access_denied", "Недостаточно прав в этой компании", 403)
        return scope, staff, memberships

    @classmethod
    async def list_candidates(cls, session: AsyncSession, *, auth, page: int, limit: int):
        scope, _, _ = await cls._actor_fence(session, auth, mutation=False)
        rows, total = await OrderResponsibilityDAO.candidates(session, tenant_id=scope.tenant_id, page=page, limit=limit)
        return ManagerOrderResponsiblesResponse(items=[cls._person(row) for row in rows], total=total, page=page, limit=limit)

    @classmethod
    async def assign(cls, session: AsyncSession, *, order_id: int, payload, auth):
        candidate_id = payload.responsible_staff_user_id
        scope, staff, memberships = await cls._actor_fence(session, auth, candidate_id=candidate_id, mutation=True)
        order = await OrderResponsibilityDAO.lock_order(session, order_id, scope)
        if order is None:
            raise OrderResponsibilityError("order_not_found", "Заказ не найден", 404)
        if order.responsible_version != payload.expected_version:
            raise OrderResponsibilityError("responsible_changed", "Ответственный уже изменён. Обновите заказ")
        previous = order.responsible_staff_user_id
        if previous != candidate_id:
            if candidate_id is not None and not cls._eligible(staff.get(candidate_id), memberships.get(candidate_id)):
                raise OrderResponsibilityError("responsible_unavailable", "Сотрудник недоступен для назначения", 400)
            previous_version = order.responsible_version
            order.responsible_staff_user_id = candidate_id
            order.responsible_version += 1
            order.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            session.add(order)
            session.add(TenantAuditEvent(
                tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
                actor_staff_user_id=auth.staff_user_id, actor_username=auth.username,
                request_id=current_request_id(), action="order.responsible_changed", entity_type="order", entity_id=order.id,
                change_set={"responsible_staff_user_id": {"before": previous, "after": candidate_id},
                            "responsible_version": {"before": previous_version, "after": order.responsible_version}},
            ))
            await session.flush()
        # Freeze the detail under the same locks; post-commit refresh must not
        # silently turn a concurrent reassignment into this command's response.
        from services.order_projection_service import OrderProjectionService
        detail = await OrderProjectionService.get_order_detail_for_manager(
            session, order.id, tenant_scope=scope, repair_legacy_state=False,
        )
        await session.commit()
        return detail
