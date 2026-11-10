"""Versioned physical equipment commands shared by Manager and MCP.

The order lock serializes new units and links. Receipts make retries durable;
source-document audit references let a reopened legacy snapshot reuse its unit
without rewriting the issued snapshot or matching unrelated serial numbers.
"""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import select

from core.config import settings
from models import CustomerEquipment, EquipmentOrderLink
from models.command_audit import CommandAuditEvent
from modules.documents.application.draft_parameters import read_draft_parameters
from schemas_order_equipment_identity import (
    OrderEquipmentIdentity, OrderEquipmentSaveInput, OrderEquipmentSaveResult, OrderEquipmentState,
)
from services.authenticated_command_service import AuthenticatedCommandService
from services.equipment_service import EquipmentService
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.tenant_entity_access_service import TenantEntityAccessService as Access


def _version(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _url(order_id):
    return f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{order_id}"


def _identity(row, roles=()):
    fields = {name: getattr(row, name) for name in (
        "customer_id", "customer_branch_id", "catalog_product_id", "equipment_source", "brand", "model", "serial",
    )}
    return OrderEquipmentIdentity(equipment_id=row.id, version=_version({
        **fields, "id": row.id, "updated_at": row.updated_at, "is_archived": row.is_archived,
    }), roles=sorted(set(roles)), **fields)


class OrderEquipmentIdentityService:
    @staticmethod
    async def _order(session, actor, order_id, *, lock=False):
        order = await Access.get_order(session, order_id, tenant_scope=actor.tenant_scope,
                                       for_update=lock, populate_existing=True)
        if order is None:
            raise LookupError("Order not found")
        return order

    @staticmethod
    async def _equipment(session, actor, order, equipment_id, *, lock=False):
        equipment = await Access.get_equipment(session, equipment_id,
            tenant_scope=actor.tenant_scope, for_update=lock)
        if equipment is None:
            raise LookupError("Equipment not found")
        # Refresh before validating ownership: another command may have moved
        # the cached unit to a different customer in this same company.
        await session.refresh(equipment)
        if equipment.is_archived:
            raise LookupError("Equipment not found")
        await EquipmentService._validate_order_link(session, equipment=equipment,
            order_id=order.id, tenant_scope=actor.tenant_scope)
        return equipment

    @staticmethod
    async def _source(session, actor, order_id, document_id):
        document = await Access.get_order_document(session, document_id, tenant_scope=actor.tenant_scope)
        if document is not None:
            await session.refresh(document)
        if (document is None or document.order_id != order_id
                or document.tenant_id not in {None, actor.tenant_scope.tenant_id}):
            raise LookupError("Document not found on this order")
        return document

    @staticmethod
    async def _state(session, actor, order, *, lock=False, equipment_id=None, limit=100, offset=0):
        linked = select(EquipmentOrderLink.equipment_id).where(EquipmentOrderLink.order_id == order.id)
        statement = select(CustomerEquipment).where(
            CustomerEquipment.customer_id == order.customer_id,
            CustomerEquipment.is_archived == False,
            or_(CustomerEquipment.source_order_id == order.id, CustomerEquipment.id.in_(linked)),
        ).order_by(CustomerEquipment.id)
        if lock:
            statement = statement.with_for_update(of=CustomerEquipment)
        rows = (await session.execute(statement.execution_options(populate_existing=True))).scalars().all()
        links = (await session.execute(select(EquipmentOrderLink).where(
            EquipmentOrderLink.order_id == order.id).execution_options(populate_existing=True))).scalars().all()
        items = [_identity(row, [link.role for link in links if link.equipment_id == row.id]) for row in rows]
        candidate = None
        if equipment_id is not None:
            row = await OrderEquipmentIdentityService._equipment(session, actor, order, equipment_id, lock=lock)
            candidate = _identity(row, [link.role for link in links if link.equipment_id == row.id])
        return OrderEquipmentState(order_id=order.id,
            version=_version({"customer_id": order.customer_id, "branch_id": order.customer_branch_id,
                              "items": [item.model_dump() for item in items]}),
            items=items[offset:offset + limit], total=len(items), candidate=candidate, manager_url=_url(order.id))

    @classmethod
    async def read(cls, session, actor, order_id, *, equipment_id=None, limit=100, offset=0):
        order = await cls._order(session, actor, order_id)
        return await cls._state(session, actor, order, equipment_id=equipment_id, limit=limit, offset=offset)

    @classmethod
    async def save(cls, session, actor, data: OrderEquipmentSaveInput):
        # Recheck live access even when the durable receipt is replayed.
        await cls._order(session, actor, data.order_id)
        if data.equipment_id is not None:
            order = await cls._order(session, actor, data.order_id)
            await cls._equipment(session, actor, order, data.equipment_id)
        if data.source_document_id is not None:
            await cls._source(session, actor, data.order_id, data.source_document_id)

        async def operation():
            order = await cls._order(session, actor, data.order_id, lock=True)
            if order.customer_id is None:
                raise ValueError("Choose the order customer before saving equipment")
            state = await cls._state(session, actor, order, lock=True)
            if state.version != data.expected_version:
                raise HTTPException(status_code=409, detail="Order equipment changed; reload its current version")
            fields = data.model_dump(exclude_unset=True, include={"brand", "model", "serial", "equipment_source"})
            equipment_id = data.equipment_id
            source_operation = None
            source_terms = {}
            if data.source_document_id is not None:
                document = await cls._source(session, actor, order.id, data.source_document_id)
                source_terms = read_draft_parameters(document).get("consumer_terms") or {}
                source_operation = f"order_equipment.source.{document.id}"
                previous = (await session.execute(select(CommandAuditEvent).where(
                    CommandAuditEvent.tenant_id == actor.tenant_scope.tenant_id,
                    CommandAuditEvent.storefront_id == actor.tenant_scope.storefront_id,
                    CommandAuditEvent.operation == source_operation,
                    CommandAuditEvent.resource_type == "customer_equipment",
                ).order_by(CommandAuditEvent.id.desc()))).scalars().first()
                if equipment_id is None:
                    equipment_id = source_terms.get("equipment_id") or (previous.resource_id if previous else None)
            if equipment_id is not None:
                equipment = await cls._equipment(session, actor, order, equipment_id, lock=True)
                changed_fields = {name: value for name, value in fields.items() if value != getattr(equipment, name)}
                if changed_fields:
                    if _identity(equipment).version != data.expected_equipment_version:
                        raise HTTPException(status_code=409, detail="Equipment changed; read its current identity version before editing")
                    for field, value in changed_fields.items():
                        if field == "equipment_source" and value is None:
                            raise ValueError("Equipment source cannot be cleared")
                        setattr(equipment, field, value)
                    session.add(equipment)
            else:
                for field in ("brand", "model", "serial"):
                    if field not in fields and source_terms.get(f"equipment_{field}"):
                        fields[field] = source_terms[f"equipment_{field}"]
                if not any(fields.get(field) for field in ("brand", "model", "serial")):
                    raise ValueError("Provide at least one known brand, model or serial number")
                equipment = CustomerEquipment(customer_id=order.customer_id, customer_branch_id=order.customer_branch_id,
                    source_order_id=order.id, equipment_source=fields.pop("equipment_source", None) or "customer_owned", **fields)
                session.add(equipment)
                await session.flush()
            await EquipmentService._ensure_equipment_order_link(session, equipment_id=equipment.id,
                order_id=order.id, role=data.role)
            if source_operation is not None:
                session.add(CommandAuditEvent(tenant_id=actor.tenant_scope.tenant_id,
                    storefront_id=actor.tenant_scope.storefront_id, staff_user_id=actor.staff_user_id,
                    channel=actor.channel, operation=source_operation,
                    request_id=_version({"document": data.source_document_id, "equipment": equipment.id}),
                    resource_type="customer_equipment", resource_id=equipment.id))
            await session.flush()
            current = await cls._state(session, actor, order, equipment_id=equipment.id)
            result = OrderEquipmentSaveResult(order_id=order.id, equipment_id=equipment.id, version=current.version,
                equipment=current.candidate, manager_url=current.manager_url)
            return PublicWriteCommandResponse(result, resource_type="customer_equipment", resource_id=equipment.id)

        outcome = await AuthenticatedCommandService.execute(session, actor=actor, command_name="order_equipment.save",
            idempotency_key=data.idempotency_key, payload=data.model_dump(mode="json", exclude={"idempotency_key"}, exclude_unset=True),
            response_model=OrderEquipmentSaveResult, operation=operation)
        if outcome.replayed:
            # A receipt cannot disclose equipment moved to a different customer.
            order = await cls._order(session, actor, data.order_id)
            await cls._equipment(session, actor, order, outcome.value.equipment_id)
        return outcome
