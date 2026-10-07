"""Factual observations: no order workflow, service event or document writes."""
from datetime import datetime, timezone
from hashlib import sha256
import json

from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.maintenance_observations import (
    CreateMaintenanceObservation, MaintenanceObservationContent, MaintenanceObservationDetail,
    MaintenanceObservationItem, UpdateMaintenanceObservation,
)
from crud.maintenance_observations import MaintenanceObservationDAO as DAO
from models import CustomerBranch
from models.maintenance_observation import MaintenanceObservation, MaintenanceObservationPhoto, MaintenanceObservationRevision
from models.tenancy import TenantScope
from services.service_attachment_service import ServiceAttachmentService
from services.tenant_entity_access_service import TenantEntityAccessService as Access


class ObservationNotFound(Exception):
    pass


class ObservationConflict(Exception):
    pass


def command_hash(payload: dict) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class MaintenanceObservationService:
    @staticmethod
    async def validate_context(session, *, customer_id, branch_id, equipment_id, scope, allow_archived=False):
        customer = await Access.get_customer(session, customer_id, tenant_scope=scope)
        if customer is None:
            raise ObservationNotFound("Customer not found")
        if branch_id is not None:
            branch = await session.get(CustomerBranch, branch_id)
            if branch is None or branch.customer_id != customer_id:
                raise ValueError("Object does not belong to the observation customer")
        if equipment_id is not None:
            equipment = await Access.get_equipment(session, equipment_id, tenant_scope=scope)
            if equipment is None or (equipment.is_archived and not allow_archived):
                raise ValueError("Equipment not found")
            if equipment.customer_id != customer_id:
                raise ValueError("Equipment does not belong to the observation customer")
            # Known objects must match exactly; unknown equipment remains unlinked.
            if equipment.customer_branch_id != branch_id:
                raise ValueError("Equipment does not belong to the observation object")

    @classmethod
    async def get(cls, session, observation_id, scope, *, lock=False):
        observation = await DAO.get(session, observation_id, scope, lock=lock)
        if observation is None:
            raise ObservationNotFound("Observation not found")
        await cls.validate_context(session, customer_id=observation.customer_id,
                                   branch_id=observation.customer_branch_id,
                                   equipment_id=None, scope=scope)
        return observation

    @staticmethod
    def revision(observation, actor):
        return MaintenanceObservationRevision(
            observation_id=observation.id, version=observation.version, actor=actor,
            snapshot=MaintenanceObservationContent.model_validate(observation, from_attributes=True).model_dump(mode="json"),
        )

    @classmethod
    async def create(cls, session: AsyncSession, *, order_id: int, payload: CreateMaintenanceObservation,
                     actor: str, scope: TenantScope):
        order = await Access.get_order(session, order_id, tenant_scope=scope, for_update=True, populate_existing=True)
        if order is None:
            raise ObservationNotFound("Order not found")
        key = str(payload.command_key)
        digest = command_hash(payload.model_dump(mode="json", exclude={"command_key"}))
        existing = await DAO.by_command(session, order_id, key)
        if existing:
            if existing.command_hash != digest:
                raise ObservationConflict("Ключ команды уже использован для другого замечания")
            await cls.get(session, existing.id, scope)
            return await cls.detail(session, existing, scope)
        if order.workflow_type != "maintenance" or order.customer_id is None:
            raise ValueError("Observation requires a maintenance order with a customer")
        await cls.validate_context(session, customer_id=order.customer_id, branch_id=order.customer_branch_id,
                                   equipment_id=payload.equipment_id, scope=scope)
        observation = MaintenanceObservation(
            tenant_id=order.tenant_id, storefront_id=order.storefront_id,
            source_order_id=order_id, customer_id=order.customer_id,
            customer_branch_id=order.customer_branch_id, command_key=key, command_hash=digest,
            created_by=actor, updated_by=actor, **payload.model_dump(exclude={"command_key"}),
        )
        session.add(observation)
        await session.flush()
        session.add(cls.revision(observation, actor))
        await session.commit()
        await session.refresh(observation)
        return await cls.detail(session, observation, scope)

    @classmethod
    async def update(cls, session, *, observation_id, payload: UpdateMaintenanceObservation, actor, scope):
        observation = await cls.get(session, observation_id, scope, lock=True)
        if observation.version != payload.expected_version:
            raise ObservationConflict("Замечание уже изменено. Откройте актуальную версию перед сохранением.")
        await cls.validate_context(session, customer_id=observation.customer_id, branch_id=observation.customer_branch_id,
                                   equipment_id=payload.equipment_id, scope=scope,
                                   allow_archived=payload.equipment_id == observation.equipment_id)
        for field, value in payload.model_dump(exclude={"expected_version"}).items():
            setattr(observation, field, value)
        observation.version += 1
        observation.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        observation.updated_by = actor
        session.add(observation)
        session.add(cls.revision(observation, actor))
        await session.commit()
        await session.refresh(observation)
        return await cls.detail(session, observation, scope)

    @classmethod
    async def list(cls, session, *, scope, order_id=None, equipment_id=None, limit=50, offset=0):
        if order_id is not None and await Access.get_order(session, order_id, tenant_scope=scope) is None:
            raise ObservationNotFound("Order not found")
        if equipment_id is not None and await Access.get_equipment(session, equipment_id, tenant_scope=scope) is None:
            raise ObservationNotFound("Equipment not found")
        return await DAO.list(session, scope, order_id=order_id, equipment_id=equipment_id, limit=limit, offset=offset)

    @classmethod
    async def detail(cls, session, observation, scope):
        data = MaintenanceObservationItem.model_validate(observation).model_dump()
        links = await DAO.photos(session, observation.id)
        order_files = await ServiceAttachmentService.list_order_attachments(session, order_id=observation.source_order_id, tenant_scope=scope)
        ids = {link.attachment_id for link in links}
        data["photos"] = [item for item in (order_files or {}).get("items", []) if item["id"] in ids]
        data["revisions"] = await DAO.revisions(session, observation.id)
        return MaintenanceObservationDetail.model_validate(data)

    @classmethod
    async def upload_photo(cls, session, *, observation_id, key, content, filename, mime_type, actor, scope):
        observation = await cls.get(session, observation_id, scope, lock=True)
        normalized_mime = ServiceAttachmentService._normalize_mime_type(mime_type, filename)
        if not normalized_mime.startswith("image/"):
            raise ValueError("Observation photos must be images")
        digest = command_hash({"hash": sha256(content).hexdigest(), "filename": filename, "mime_type": normalized_mime})
        previous = next((p for p in await DAO.photos(session, observation_id) if p.command_key == str(key)), None)
        if previous:
            if previous.command_hash != digest:
                raise ObservationConflict("Ключ загрузки уже использован для другого фото")
            detail = await cls.detail(session, observation, scope)
            item = next((p for p in detail.photos if p.id == previous.attachment_id), None)
            if item is None:
                raise ObservationConflict("Фото удалено из активных вложений")
            return item
        # The observation owns equipment association; avoid stale duplicated links
        # when unknown equipment is identified or corrected later.
        item = await ServiceAttachmentService.create_and_link_order_attachment(
            session, order_id=observation.source_order_id, content=content, filename=filename,
            mime_type=normalized_mime, category="defect", caption=f"Замечание #{observation.id}",
            source="manager_maintenance", created_by=actor,
            source_meta={"maintenance_observation_id": observation.id}, commit=False, tenant_scope=scope,
        )
        session.add(MaintenanceObservationPhoto(observation_id=observation_id, attachment_id=item["id"],
                                              command_key=str(key), command_hash=digest))
        await session.commit()
        return item
