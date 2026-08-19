from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from models.tenancy import TenantScope


class TenantEquipmentCommercialFieldsDeniedError(ValueError):
    pass


class ManagerEquipmentPermissionService:
    SYSTEM_ONLY_SUPPLIER_FIELDS = frozenset(
        {
            "supplier_id",
            "supplier_invoice_number",
            "supplier_invoice_date",
        }
    )

    @classmethod
    def assert_supplier_fields_allowed(
        cls,
        *,
        payload: Mapping[str, Any],
        tenant_scope: TenantScope,
    ) -> None:
        if tenant_scope.is_system:
            return
        denied_fields = sorted(cls.SYSTEM_ONLY_SUPPLIER_FIELDS.intersection(payload))
        if denied_fields:
            raise TenantEquipmentCommercialFieldsDeniedError(
                "Supplier and supplier invoice fields are managed by the system operator"
            )
