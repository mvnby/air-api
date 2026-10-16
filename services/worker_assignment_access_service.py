"""One live explicit assignment ACL shared by installer web and bot operations."""
from sqlalchemy import or_, select
from crud.order_responsibility import OrderResponsibilityDAO
from crud.worker_assignment import WorkerAssignmentDAO
from models import OrderWorkAssignment, OrderWorkStage
from services.worker_assignment_service import WorkerAssignmentService


class WorkerAssignmentAccessService:
    @classmethod
    async def list_for_actor(cls, session, auth, page=1, limit=100):
        scope, _, _ = await WorkerAssignmentService.identity_fence(session, auth)
        return await WorkerAssignmentDAO.visible_list(session, scope, auth.staff_user_id, page, min(limit, 100))

    @classmethod
    async def get_for_actor(cls, session, auth, assignment_id, for_update=False, *, _include_completed=False, _requested_stage_id=None):
        scope, _, _ = await WorkerAssignmentService.identity_fence(session, auth, mutation=for_update)
        profile = await WorkerAssignmentDAO.profile(session, scope.tenant_id, auth.staff_user_id, lock=for_update)
        if profile is None or profile.status != 'active':
            return None
        # Unlocked hint contains immutable linkage only. After the ordered parent
        # fences, lock the Order first, then stage and assignment, and recheck ACL.
        hint = await session.scalar(select(OrderWorkAssignment).where(OrderWorkAssignment.id == assignment_id,
            OrderWorkAssignment.worker_profile_id == profile.id, OrderWorkAssignment.tenant_id == scope.tenant_id,
            OrderWorkAssignment.storefront_id == scope.storefront_id).execution_options(populate_existing=True))
        if hint is None:
            return None
        if for_update:
            if await OrderResponsibilityDAO.lock_order(session, hint.order_id, scope) is None:
                return None
            stage_to_lock = _requested_stage_id if _requested_stage_id is not None else hint.work_stage_id
            if stage_to_lock is not None:
                await WorkerAssignmentService.lock_stage(session, hint.order_id, stage_to_lock)
            await session.scalar(select(OrderWorkAssignment).where(OrderWorkAssignment.id == assignment_id).with_for_update()
                .execution_options(populate_existing=True))
        return await session.scalar(WorkerAssignmentDAO.visible(scope, auth.staff_user_id, include_completed=_include_completed)
            .where(OrderWorkAssignment.id == assignment_id).execution_options(populate_existing=True))

    @classmethod
    async def get_for_stage(cls, session, auth, stage_id, for_update=False, *, existing_action=False):
        scope, _, _ = await WorkerAssignmentService.identity_fence(session, auth, mutation=for_update)
        stage = await session.scalar(select(OrderWorkStage).where(OrderWorkStage.id == stage_id).execution_options(populate_existing=True))
        if stage is None:
            return None
        ids = list((await session.scalars(WorkerAssignmentDAO.visible(scope, auth.staff_user_id, include_completed=existing_action)
            .with_only_columns(OrderWorkAssignment.id).where(OrderWorkAssignment.order_id == stage.order_id,
                or_(OrderWorkAssignment.work_stage_id == stage_id, OrderWorkAssignment.work_stage_id.is_(None)))
            .order_by(OrderWorkAssignment.id))).all())
        for assignment_id in ids:
            result = await cls.get_for_actor(session, auth, assignment_id, for_update=for_update, _include_completed=existing_action, _requested_stage_id=stage_id)
            if result is not None:
                # Order-wide grants still obey the requested visit lifecycle.
                current = await WorkerAssignmentService.lock_stage(session, result.order_id, stage_id) if for_update else stage
                if current.status in (('planned', 'in_progress', 'completed') if existing_action else ('planned', 'in_progress')):
                    return result
        return None
