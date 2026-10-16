"""Explicit, audited delegation. Company owners cannot grant platform access."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_access import ManagerAccessItem, ManagerAccessList, ManagerAccessMeta, ManagerAccessUpdate
from crud.manager_access import ManagerAccessDAO
from models import TenantAuditEvent
from core.request_context import current_request_id


class ManagerAccessConflict(ValueError):
    pass


class ManagerAccessService:
    @staticmethod
    def item(row) -> ManagerAccessItem:
        membership, staff_name, tenant_name = row
        return ManagerAccessItem(
            membership_id=membership.id, staff_user_id=membership.staff_user_id,
            display_name=staff_name, tenant_id=membership.tenant_id, tenant_name=tenant_name,
            role=membership.role, status=membership.status,
            permissions=membership.permissions or [], updated_at=membership.updated_at,
        )

    @classmethod
    async def list(cls, session: AsyncSession, *, page: int, limit: int, search: str | None):
        rows, total = await ManagerAccessDAO.list_memberships(session, page=page, limit=limit, search=search)
        return ManagerAccessList(
            items=[cls.item(row) for row in rows],
            meta=ManagerAccessMeta(page=page, limit=limit, total=total, pages=(total + limit - 1) // limit),
        )

    @classmethod
    async def update(cls, session: AsyncSession, *, membership_id: int, payload: ManagerAccessUpdate, actor):
        if not actor.is_platform_owner:
            raise PermissionError("Only the platform owner can delegate shared catalog access")
        row = await ManagerAccessDAO.get_membership(session, membership_id)
        if row is None:
            return None
        membership = row[0]
        # Normalize old naive timestamps to UTC for databases created before timezone use.
        current = membership.updated_at.replace(tzinfo=timezone.utc) if membership.updated_at.tzinfo is None else membership.updated_at
        expected = payload.expected_updated_at.replace(tzinfo=timezone.utc) if payload.expected_updated_at.tzinfo is None else payload.expected_updated_at
        if current != expected:
            raise ManagerAccessConflict("Доступ уже изменён. Обновите список и повторите действие.")
        permissions = sorted(payload.permissions)
        before = list(membership.permissions or [])
        if sorted(before) != permissions:
            storefront_id = await ManagerAccessDAO.default_storefront_id(session, membership.tenant_id)
            if storefront_id is None:
                raise ManagerAccessConflict("У компании не настроена основная витрина")
            membership.permissions = permissions
            membership.updated_at = datetime.now(timezone.utc)
            session.add(membership)
            session.add(TenantAuditEvent(
                tenant_id=membership.tenant_id, storefront_id=storefront_id,
                actor_staff_user_id=actor.staff_user_id, request_id=current_request_id(),
                actor_username=actor.username, action="staff.catalog_permissions_changed",
                entity_type="tenant_membership", entity_id=membership.id,
                change_set={"permissions": {"before": before, "after": permissions}},
            ))
            await session.commit()
            await session.refresh(membership)
        return cls.item(row)
