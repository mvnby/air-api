import schemas
from schemas_catalog import CatalogRevisionResponse
from schemas_common import Meta
from schemas_manager_installers import ManagerInstallerResponse
from schemas_manager_leads import LeadQualifyPayload, ProductAvailabilityLeadPayload
from schemas_manager_order_transfer import ManagerOrderTransferPackage
from schemas_manager_orders import (
    ManagerOrderDetailResponse,
    ManagerOrderUpdatePayload,
    OrderWorkStageCreatePayload,
)


def test_legacy_schema_facade_reexports_domain_contracts():
    assert schemas.CatalogRevisionResponse is CatalogRevisionResponse
    assert schemas.Meta is Meta
    assert schemas.ManagerInstallerResponse is ManagerInstallerResponse
    assert schemas.LeadQualifyPayload is LeadQualifyPayload
    assert schemas.ProductAvailabilityLeadPayload is ProductAvailabilityLeadPayload
    assert schemas.ManagerOrderDetailResponse is ManagerOrderDetailResponse
    assert schemas.ManagerOrderUpdatePayload is ManagerOrderUpdatePayload
    assert schemas.OrderWorkStageCreatePayload is OrderWorkStageCreatePayload
    assert schemas.ManagerOrderTransferPackage is ManagerOrderTransferPackage
