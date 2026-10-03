import pytest
from fastapi import HTTPException

from models.tenancy import TenantScope
from routers.manager_customers import create_customer_reconciliation_document_for_manager
from services.customer_reconciliation_service import (
    CustomerReconciliationService, ReconciliationNotReadyError,
)


@pytest.mark.asyncio
async def test_generation_conflict_returns_actionable_warnings(monkeypatch):
    warnings = [{
        "code": "legacy_source_changed", "message": "Оригинал изменился",
        "order_id": 1, "document_id": 12, "payment_id": None,
        "related_document_ids": [], "can_review_legacy": True,
    }]

    async def rejected(cls, **kwargs):
        raise ReconciliationNotReadyError(warnings)

    monkeypatch.setattr(CustomerReconciliationService, "generate_google_doc", classmethod(rejected))
    with pytest.raises(HTTPException) as captured:
        await create_customer_reconciliation_document_for_manager(
            customer_id=1, date_from=None, date_to=None, contract_id=None,
            session=None, tenant_scope=TenantScope(tenant_id=1, storefront_id=1),
        )
    assert captured.value.status_code == 409
    assert captured.value.detail["warnings"] == warnings
    assert captured.value.detail["message"]
    assert captured.value.detail["error_code"]
