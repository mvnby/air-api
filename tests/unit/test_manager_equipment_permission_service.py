from datetime import datetime

import pytest

from models import EquipmentComponent
from models.tenancy import TenantScope
from services.manager_equipment_permission_service import (
    ManagerEquipmentPermissionService,
    TenantEquipmentCommercialFieldsDeniedError,
)
from services.equipment_service import EquipmentService


@pytest.mark.parametrize(
    "payload",
    [
        {"supplier_id": 7},
        {"supplier_id": None},
        {"supplier_invoice_number": "INV-1"},
        {"supplier_invoice_date": None},
    ],
)
def test_non_system_tenant_cannot_submit_supplier_component_fields(payload):
    with pytest.raises(TenantEquipmentCommercialFieldsDeniedError):
        ManagerEquipmentPermissionService.assert_supplier_fields_allowed(
            payload=payload,
            tenant_scope=TenantScope(tenant_id=2, storefront_id=20, is_system=False),
        )


def test_non_system_tenant_can_submit_non_commercial_component_fields():
    ManagerEquipmentPermissionService.assert_supplier_fields_allowed(
        payload={"title": "Indoor unit", "serial": "A-1"},
        tenant_scope=TenantScope(tenant_id=2, storefront_id=20, is_system=False),
    )


def test_system_tenant_can_submit_supplier_component_fields():
    ManagerEquipmentPermissionService.assert_supplier_fields_allowed(
        payload={"supplier_id": 7, "supplier_invoice_number": "INV-1"},
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
    )


def test_component_serializer_redacts_supplier_fields_only_for_non_system_tenant():
    component = EquipmentComponent(
        id=3,
        equipment_id=4,
        supplier_id=5,
        supplier_invoice_number="INV-SECRET",
        supplier_invoice_date=datetime(2026, 8, 1),
    )

    tenant_item = EquipmentService._to_component_item(
        component,
        tenant_scope=TenantScope(tenant_id=2, storefront_id=20, is_system=False),
    )
    system_item = EquipmentService._to_component_item(
        component,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
    )

    assert tenant_item["supplier_id"] is None
    assert tenant_item["supplier_invoice_number"] is None
    assert tenant_item["supplier_invoice_date"] is None
    assert system_item["supplier_id"] == 5
    assert system_item["supplier_invoice_number"] == "INV-SECRET"
    assert system_item["supplier_invoice_date"] == datetime(2026, 8, 1)
