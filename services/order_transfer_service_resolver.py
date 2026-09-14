"""Tenant-scoped service matching for portable Manager order transfers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Service
from schemas import ManagerOrderTransferServiceRef
from services.service_catalog_scope import service_catalog_scope_clause
from services.tenant_scope_service import TenantScope


class OrderTransferServiceResolver:
    """Resolve transfer references only inside the target service catalog."""

    @staticmethod
    def _optional_clean(value: Any) -> str | None:
        cleaned = " ".join(str(value or "").split())
        return cleaned or None

    @staticmethod
    async def find_service(
        session: AsyncSession,
        service_ref: ManagerOrderTransferServiceRef | None,
        *,
        tenant_scope: TenantScope,
    ) -> Service | None:
        if not service_ref:
            return None

        slug = OrderTransferServiceResolver._optional_clean(service_ref.slug)
        if slug:
            result = await session.execute(
                select(Service)
                .where(
                    Service.slug == slug,
                    service_catalog_scope_clause(Service, tenant_scope),
                )
                .limit(1)
            )
            service = result.scalars().first()
            if service:
                return service

        title = OrderTransferServiceResolver._optional_clean(service_ref.title)
        if not title:
            return None
        result = await session.execute(
            select(Service)
            .where(
                func.lower(Service.title) == title.lower(),
                service_catalog_scope_clause(Service, tenant_scope),
            )
            .limit(1)
        )
        return result.scalars().first()
