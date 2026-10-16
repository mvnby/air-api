"""Explicit work grants; caller owns the transaction and response snapshot."""
from datetime import datetime, timezone

from sqlalchemy import select

from api_contracts.installer_workspace import WorkerCandidatesResponse, WorkerPerson
from core.request_context import current_request_id
from crud.order_responsibility import ELIGIBLE_ROLES, OrderResponsibilityDAO
from crud.worker_assignment import ACTIVE_STAGES, WORKER_ROLES, WorkerAssignmentDAO
from models import OrderWorkAssignment, OrderWorkStage, TenantAuditEvent, TenantWorkerProfile, Tenant
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.order_responsibility_service import OrderResponsibilityError, OrderResponsibilityService
from services.staff_avatar_service import staff_avatar_url
from services.staff_user_service import StaffUserService


class WorkerAssignmentError(OrderResponsibilityError):
    pass


class WorkerAssignmentService:
    @staticmethod
    def eligible(staff, member):
        return bool(staff and StaffUserService.is_active(staff) and member and member.status == 'active'
                    and member.role in WORKER_ROLES)

    @classmethod
    async def identity_fence(cls, session, auth, *, staff_ids=(), mutation=False, manager=False):
        if auth.staff_user_id is None:
            raise WorkerAssignmentError('staff_account_required', 'Нужна учётная запись сотрудника', 403)
        scope = auth.tenant_scope()
        try:
            state, staff, members = await OrderResponsibilityService._fence(
                session, scope, [auth.staff_user_id, *staff_ids], mutation=mutation, lock=mutation)
        except OrderResponsibilityError as exc:
            raise WorkerAssignmentError(exc.code, str(exc), exc.status_code) from exc
        actor = staff.get(auth.staff_user_id)
        if (not actor or not StaffUserService.is_active(actor) or actor.must_change_password
                or actor.auth_version != auth.auth_version or not LegacyOwnerAuthGuard.allows_staff_identity(
                    state, staff_user_id=actor.id, username=actor.username or '')):
            raise WorkerAssignmentError('staff_access_changed', 'Доступ сотрудника изменён', 403)
        bound = LegacyOwnerAuthGuard.allows_bound_staff(state, staff_user_id=actor.id)
        if bound and not await LegacyOwnerManagedIdentityService.exact_bound_staff_identity_allowed(session, state=state, user=actor):
            raise WorkerAssignmentError('staff_access_changed', 'Профиль владельца недоступен', 403)
        member = members.get(actor.id)
        actual = cls.eligible(actor, member) and (not manager or member.role in ELIGIBLE_ROLES)
        support = manager and auth.access_kind == 'platform_support' and auth.is_platform_owner and bound
        if not actual and not support:
            raise WorkerAssignmentError('worker_access_denied', 'Недостаточно прав в этой компании', 403)
        return scope, staff, members

    @classmethod
    async def actor_fence(cls, session, auth, *, staff_ids=(), mutation=True):
        scope, _, _ = await cls.identity_fence(session, auth, staff_ids=staff_ids, mutation=mutation, manager=True)
        return scope

    @classmethod
    async def candidates(cls, session, auth, page=1, limit=100):
        scope = await cls.actor_fence(session, auth, mutation=False)
        rows, total = await WorkerAssignmentDAO.candidates(session, scope.tenant_id, page, min(limit, 100))
        return WorkerCandidatesResponse(items=[WorkerPerson(staff_user_id=row.id, display_name=row.display_name,
            avatar_url=staff_avatar_url(row, tenant_id=scope.tenant_id)) for row in rows], total=total, page=page, limit=min(limit, 100))

    @staticmethod
    async def ensure_profile(session, scope, staff):
        profile = await WorkerAssignmentDAO.profile(session, scope.tenant_id, staff.id, lock=True)
        if profile is None:
            # Parent/member fences precede this first FK write. Concurrent explicit
            # assignments may create the same profile; never roll back their caller.
            dialect = session.get_bind().dialect.name
            if dialect == 'postgresql':
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            tenant = await session.get(Tenant, scope.tenant_id)
            canonical_installer = staff.legacy_installer_id if tenant.is_system and tenant.slug == 'mvn' else None
            await session.execute(insert(TenantWorkerProfile).values(tenant_id=scope.tenant_id, staff_user_id=staff.id,
                status='active', version=0, canonical_legacy_installer_id=canonical_installer
            ).on_conflict_do_nothing(index_elements=['tenant_id', 'staff_user_id']))
            profile = await WorkerAssignmentDAO.profile(session, scope.tenant_id, staff.id, lock=True)
        if profile.status != 'active':
            raise WorkerAssignmentError('worker_disabled', 'Профиль исполнителя отключён', 400)
        return profile

    @staticmethod
    def audit(session, scope, auth, assignment, action, changes):
        session.add(TenantAuditEvent(tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
            actor_staff_user_id=auth.staff_user_id if auth else None, actor_username=auth.username if auth else "legacy_manager_assignment",
            request_id=current_request_id(), action=action, entity_type='order_work_assignment', entity_id=assignment.id,
            change_set=changes))

    @staticmethod
    async def lock_stage(session, order_id, stage_id):
        if stage_id is None:
            return None
        stage = await session.scalar(select(OrderWorkStage).where(OrderWorkStage.id == stage_id,
            OrderWorkStage.order_id == order_id).with_for_update().execution_options(populate_existing=True))
        if stage is None:
            raise WorkerAssignmentError('stage_not_found', 'Работа не найдена', 404)
        return stage

    @classmethod
    async def create(cls, session, auth, order_id, payload):
        scope, staff, members = await cls.identity_fence(session, auth, staff_ids=[payload.staff_user_id], mutation=True, manager=True)
        candidate = staff.get(payload.staff_user_id)
        if not cls.eligible(candidate, members.get(payload.staff_user_id)):
            raise WorkerAssignmentError('worker_unavailable', 'Сотрудник недоступен для назначения', 400)
        profile = await cls.ensure_profile(session, scope, candidate)
        order = await OrderResponsibilityDAO.lock_order(session, order_id, scope)
        if order is None:
            raise WorkerAssignmentError('order_not_found', 'Заказ не найден', 404)
        stage = await cls.lock_stage(session, order_id, payload.work_stage_id)
        if order.status == 'closed' or (stage and stage.status not in ACTIVE_STAGES):
            raise WorkerAssignmentError('work_inactive', 'Завершённая работа недоступна для назначения', 400)
        row = await session.scalar(select(OrderWorkAssignment).where(OrderWorkAssignment.order_id == order_id,
            OrderWorkAssignment.worker_profile_id == profile.id, OrderWorkAssignment.work_stage_id == payload.work_stage_id,
            OrderWorkAssignment.revoked_at.is_(None)).with_for_update().execution_options(populate_existing=True))
        if row is not None:
            if row.source != 'manual':
                previous = row.source
                row.source = 'manual'
                row.version += 1
                cls.audit(session, scope, auth, row, 'work_assignment.confirmed', {'source': {'before': previous, 'after': 'manual'}})
                await session.flush()
            return row
        row = OrderWorkAssignment(tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
            order_id=order_id, work_stage_id=payload.work_stage_id, worker_profile_id=profile.id)
        session.add(row)
        await session.flush()
        cls.audit(session, scope, auth, row, 'work_assignment.created', {'staff_user_id': payload.staff_user_id,
            'work_stage_id': payload.work_stage_id, 'version': 0})
        await session.flush()
        return row

    @classmethod
    async def revoke(cls, session, auth, order_id, assignment_id, expected_version):
        hint = await session.scalar(select(TenantWorkerProfile.staff_user_id).join(OrderWorkAssignment,
            OrderWorkAssignment.worker_profile_id == TenantWorkerProfile.id).where(OrderWorkAssignment.id == assignment_id,
                OrderWorkAssignment.order_id == order_id, OrderWorkAssignment.tenant_id == auth.tenant_id,
                OrderWorkAssignment.storefront_id == auth.storefront_id))
        scope = await cls.actor_fence(session, auth, staff_ids=[hint], mutation=True)
        if hint is not None:
            await WorkerAssignmentDAO.profile(session, scope.tenant_id, hint, lock=True)
        order = await OrderResponsibilityDAO.lock_order(session, order_id, scope)
        if order is None:
            raise WorkerAssignmentError('order_not_found', 'Заказ не найден', 404)
        row = await session.scalar(select(OrderWorkAssignment).where(OrderWorkAssignment.id == assignment_id,
            OrderWorkAssignment.order_id == order_id).with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise WorkerAssignmentError('assignment_not_found', 'Назначение не найдено', 404)
        if row.version != expected_version:
            raise WorkerAssignmentError('assignment_changed', 'Назначение изменено. Обновите страницу')
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            row.version += 1
            cls.audit(session, scope, auth, row, 'work_assignment.revoked', {'version': row.version})
            await session.flush()
        return row
