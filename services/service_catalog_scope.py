"""Tenant boundary helpers for service catalogs and their pricing rows."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_

from models.tenancy import TenantScope


def service_catalog_scope_clause(entity: Any, tenant_scope: TenantScope):
    """Return rows owned by one tenant, with legacy NULL rows reserved for MVN."""

    if tenant_scope.is_system:
        return or_(
            entity.tenant_id == tenant_scope.tenant_id,
            entity.tenant_id.is_(None),
        )
    return entity.tenant_id == tenant_scope.tenant_id


def service_catalog_write_tenant_id(tenant_scope: TenantScope) -> int | None:
    """Keep canonical MVN writes compatible with the legacy NULL ownership marker."""

    return None if tenant_scope.is_system else tenant_scope.tenant_id


def canonical_service_catalog_clause(entity: Any):
    """Select only the detached-copy template owned by canonical MVN."""

    return entity.tenant_id.is_(None)
