"""Narrow projections for assigned work; no Manager order DTO crosses this boundary."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select

from api_contracts.installer_workspace import (
    InstallerEquipment,
    InstallerTechnicalSpec,
    InstallerWorkDetail,
    InstallerWorksResponse,
    InstallerWorkSummary,
    ManagerCollectionBalance,
    ManagerInstallerWorkspace,
    ManagerWorkerAssignment,
)
from core.config import settings
from crud.installer_workspace import InstallerWorkspaceDAO as DAO
from crud.worker_assignment import WorkerAssignmentDAO
from models import (
    Order,
    OrderWorkAssignment,
    OrderWorkStage,
    Product,
    StaffUser,
    TenantWorkerProfile,
)
from services.installer_collection_service import (
    InstallerCollectionService as Collection,
    InstallerWorkspaceError,
)
from services.installer_material_service import InstallerMaterialService as Materials
from services.worker_assignment_access_service import (
    WorkerAssignmentAccessService as Access,
)
from services.worker_assignment_service import WorkerAssignmentService as Assignments


class InstallerWorkspaceService:
    @staticmethod
    async def _summary(session, scope, assignment, order, stage=None):
        start = stage.start_time if stage is not None else order.installation_date
        status = stage.status if stage is not None else order.status
        return InstallerWorkSummary(
            id=assignment.id,
            order_id=order.id,
            work_stage_id=assignment.work_stage_id,
            version=assignment.version,
            title=assignment.title,
            status=status.value if hasattr(status, "value") else status,
            start_time=start,
            end_time=stage.end_time if stage else None,
            customer_name=order.customer.name if order.customer else "Клиент",
            customer_phone=order.customer.phone if order.customer else None,
            address=order.delivery_address,
            collection=await Collection.installer_view(
                session, order=order, scope=scope, assignment=assignment
            ),
        )

    @classmethod
    async def list_works(cls, session, auth, page=1, limit=50, bucket="all"):
        scope, _, _ = await Assignments.identity_fence(session, auth)
        statement = WorkerAssignmentDAO.visible(scope, auth.staff_user_id)
        scheduled = case(
            (OrderWorkAssignment.work_stage_id.is_not(None), OrderWorkStage.start_time),
            else_=Order.installation_date,
        )
        today = datetime.now(ZoneInfo(settings.BOT_TASK_TIMEZONE)).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        if bucket == "today":
            statement = statement.where(
                scheduled >= today, scheduled < today + timedelta(days=1)
            )
        elif bucket == "upcoming":
            statement = statement.where(scheduled >= today + timedelta(days=1))
        elif bucket == "unscheduled":
            statement = statement.where(scheduled.is_(None))
        elif bucket != "all":
            raise InstallerWorkspaceError(
                "invalid_bucket", "Неизвестный период работ", 400
            )
        total = int(
            await session.scalar(select(func.count()).select_from(statement.subquery()))
            or 0
        )
        assignments = list(
            (
                await session.scalars(
                    statement.order_by(
                        scheduled.asc().nullslast(), OrderWorkAssignment.id
                    )
                    .offset((page - 1) * limit)
                    .limit(limit)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        orders = (
            await DAO.orders(session, scope, {a.order_id for a in assignments})
            if assignments
            else {}
        )
        stage_ids = {
            a.work_stage_id for a in assignments if a.work_stage_id is not None
        }
        stages = (
            {
                row.id: row
                for row in (
                    await session.scalars(
                        select(OrderWorkStage).where(OrderWorkStage.id.in_(stage_ids))
                    )
                ).all()
            }
            if stage_ids
            else {}
        )
        items = [
            await cls._summary(
                session, scope, a, orders[a.order_id], stages.get(a.work_stage_id)
            )
            for a in assignments
            if a.order_id in orders
        ]
        return InstallerWorksResponse(items=items, total=total, page=page, limit=limit)

    @classmethod
    async def detail(cls, session, auth, assignment_id):
        assignment = await Access.get_for_actor(session, auth, assignment_id)
        if assignment is None:
            raise InstallerWorkspaceError("work_not_found", "Работа не найдена", 404)
        scope = auth.tenant_scope()
        order = await DAO.order(session, scope, assignment.order_id)
        if order is None:
            raise InstallerWorkspaceError("work_not_found", "Работа не найдена", 404)
        stage = (
            await session.get(OrderWorkStage, assignment.work_stage_id)
            if assignment.work_stage_id
            else None
        )
        summary = await cls._summary(session, scope, assignment, order, stage)
        return InstallerWorkDetail(
            **summary.model_dump(),
            instructions=assignment.instructions,
            equipment=await cls.equipment(session, order, scope),
            materials=await Materials.visible(session, assignment),
        )

    @staticmethod
    async def equipment(session, order, scope):
        from services.spec_normalizer import normalize_specs

        result = []
        for unit in await DAO.equipment(session, order, scope):
            result.append(
                InstallerEquipment(
                    key=f"equipment:{unit.id}",
                    name=unit.display_name or unit.model or "Оборудование",
                    brand=unit.brand,
                    model=unit.model,
                    serial=unit.serial,
                    quantity=1,
                    technical_specs=[
                        InstallerTechnicalSpec(
                            label="Хладагент", value=unit.refrigerant_type
                        )
                    ]
                    if unit.refrigerant_type
                    else [],
                )
            )
        active = [p for p in order.proposals if not p.is_archived]
        selected = [p for p in active if p.is_selected]
        proposal_id = (
            selected[0].id
            if len(selected) == 1
            else active[0].id
            if len(active) == 1
            else None
        )
        lines = [
            line for line in order.product_links if line.proposal_id == proposal_id
        ]
        product_ids = {line.product_id for line in lines if line.product_id}
        products = (
            {
                p.id: p
                for p in (
                    await session.scalars(
                        select(Product).where(Product.id.in_(product_ids))
                    )
                ).all()
            }
            if product_ids
            else {}
        )
        labels = {
            "refrigerant": "Хладагент",
            "area_m2": "Площадь, м²",
            "power_supply_voltage": "Питание",
            "pipe_liquid_mm": "Жидкостная труба, мм",
            "pipe_gas_mm": "Газовая труба, мм",
            "refrigerant_charge_g": "Заправка хладагента, г",
        }
        for line in lines:
            product = products.get(line.product_id)
            specs = normalize_specs(product.specs or {}) if product else {}
            technical = []
            for key, label in labels.items():
                value = specs.get(key)
                if isinstance(value, dict):
                    value = value.get("value")
                if isinstance(value, (str, int, float)):
                    technical.append(
                        InstallerTechnicalSpec(label=label, value=str(value)[:200])
                    )
            if product and product.power_cooling:
                technical.append(
                    InstallerTechnicalSpec(
                        label="Холодопроизводительность, кВт",
                        value=str(product.power_cooling),
                    )
                )
            result.append(
                InstallerEquipment(
                    key=f"product:{line.id}",
                    name=line.title_snapshot
                    or (product.title if product else "Оборудование"),
                    quantity=max(1, line.quantity),
                    technical_specs=technical,
                )
            )
        return result

    @classmethod
    async def manager_view(cls, session, auth, order_id):
        scope = await Assignments.actor_fence(session, auth, mutation=False)
        order = await DAO.order(session, scope, order_id)
        if order is None:
            raise InstallerWorkspaceError("order_not_found", "Заказ не найден", 404)
        rows = (
            await session.execute(
                select(OrderWorkAssignment, TenantWorkerProfile, StaffUser)
                .join(
                    TenantWorkerProfile,
                    TenantWorkerProfile.id == OrderWorkAssignment.worker_profile_id,
                )
                .join(StaffUser, StaffUser.id == TenantWorkerProfile.staff_user_id)
                .where(
                    OrderWorkAssignment.order_id == order.id,
                    OrderWorkAssignment.tenant_id == scope.tenant_id,
                    OrderWorkAssignment.storefront_id == scope.storefront_id,
                )
                .order_by(OrderWorkAssignment.id)
            )
        ).all()
        items = []
        for assignment, profile, staff in rows:
            live = await session.scalar(
                WorkerAssignmentDAO.visible(scope, profile.staff_user_id).where(
                    OrderWorkAssignment.id == assignment.id
                )
            )
            items.append(
                ManagerWorkerAssignment(
                    id=assignment.id,
                    staff_user_id=profile.staff_user_id,
                    display_name=staff.display_name,
                    work_stage_id=assignment.work_stage_id,
                    version=assignment.version,
                    title=assignment.title,
                    instructions=assignment.instructions,
                    source=assignment.source,
                    revoked_at=assignment.revoked_at,
                    is_active=live is not None,
                    material_link_ids=[
                        p.order_attachment_link_id
                        for p in await DAO.publications(session, assignment.id)
                        if p.revoked_at is None
                    ],
                )
            )
        snapshot = await Collection.snapshot(session, order)
        return ManagerInstallerWorkspace(
            order_id=order.id,
            assignments=items,
            materials=await Materials.manager_materials(session, order.id),
            collection=await Collection.manager_view(
                session, order=order, scope=scope, snapshot=snapshot
            ),
            balances=[
                ManagerCollectionBalance(currency=k, remaining_amount=f"{v:.2f}")
                for k, v in snapshot.balances.items()
            ],
            financial_fingerprint=snapshot.fingerprint,
        )

    @classmethod
    async def publish(cls, session, auth, order_id, assignment_id, payload):
        scope = await Assignments.actor_fence(session, auth, mutation=True)
        if await DAO.order(session, scope, order_id, lock=True) is None:
            raise InstallerWorkspaceError("order_not_found", "Заказ не найден", 404)
        row = await session.scalar(
            select(OrderWorkAssignment)
            .where(
                OrderWorkAssignment.id == assignment_id,
                OrderWorkAssignment.order_id == order_id,
                OrderWorkAssignment.tenant_id == scope.tenant_id,
                OrderWorkAssignment.storefront_id == scope.storefront_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or row.revoked_at is not None:
            raise InstallerWorkspaceError(
                "assignment_not_found", "Назначение не найдено", 404
            )
        if row.version != payload.expected_version:
            raise InstallerWorkspaceError(
                "assignment_changed", "Работа уже изменена. Обновите данные"
            )
        await Materials.publish(session, row, payload.material_link_ids)
        before = {
            "title": row.title,
            "instructions": row.instructions,
            "version": row.version,
        }
        row.title, row.instructions = payload.title, payload.instructions.strip()
        row.version += 1
        session.add(row)
        Assignments.audit(
            session,
            scope,
            auth,
            row,
            "work_assignment.published",
            {
                "before": before,
                "after": {
                    "title": row.title,
                    "instructions": row.instructions,
                    "version": row.version,
                    "material_link_ids": payload.material_link_ids,
                },
            },
        )
        await session.flush()
