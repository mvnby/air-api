"""Published books retire new legacy installation estimates per tenant."""

import pytest
from fastapi import HTTPException
from sqlmodel import func, select

from models import InstallationPriceBook, ServiceEstimate, ServiceTariff
from models.tenancy import TenantScope
from schemas import ManagerInstallEstimateCalculatePayload, ManagerInstallEstimateSavePayload
from services.service_estimate_service import ServiceEstimateService
from services.tariffs_service import TariffsService


@pytest.mark.asyncio
async def test_published_book_blocks_legacy_installation_but_preserves_other_services(db):
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True,
                        is_canonical_storefront=True)
    installation = ServiceTariff(
        service_kind="installation", selector_label="Монтаж", short_name="Монтаж",
        category="Wall", base_price=500, is_active=True,
    )
    repair = ServiceTariff(
        service_kind="repair", selector_label="Ремонт", short_name="Ремонт",
        category="repair", base_price=150, is_active=True,
    )
    db.add_all([installation, repair])
    await db.commit()

    before = await ServiceEstimateService.calculate_install_estimate(
        db, ManagerInstallEstimateCalculatePayload(tariff_id=installation.id), scope,
    )
    assert before.total == 500
    db.add(InstallationPriceBook(tenant_id=1, revision=1,
                                 fingerprint="legacy-retirement-one", entries=[]))
    await db.commit()

    for action in (
        ServiceEstimateService.calculate_install_estimate(
            db, ManagerInstallEstimateCalculatePayload(tariff_id=installation.id), scope,
        ),
        ServiceEstimateService.create_install_estimate(
            db, ManagerInstallEstimateSavePayload(tariff_id=installation.id),
            created_by="manager", tenant_scope=scope,
        ),
    ):
        with pytest.raises(HTTPException) as refused:
            await action
        assert refused.value.status_code == 409
        assert refused.value.detail["code"] == "book_preview_required"

    quick = await TariffsService.list_quick_add_tariffs(db, tenant_scope=scope)
    assert [item.tariff_id for item in quick] == [repair.id]
    other = await ServiceEstimateService.calculate_install_estimate(
        db, ManagerInstallEstimateCalculatePayload(tariff_id=repair.id), scope,
    )
    assert other.total == 150
    assert await db.scalar(select(func.count(ServiceEstimate.id))) == 0
