"""ChatGPT inputs for the shared order sites and equipment commands."""

from pydantic import Field

from schemas_connector_mcp import OrderIdInput
from schemas_order_sites import OrderSiteAddRequest, OrderSiteEquipmentLinkRequest


class OrderSitesListInput(OrderIdInput):
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SiteEquipmentListInput(OrderSitesListInput):
    site_id: int = Field(gt=0)


class OrderSiteAddInput(OrderIdInput, OrderSiteAddRequest):
    pass


class SiteEquipmentLinkInput(OrderIdInput, OrderSiteEquipmentLinkRequest):
    site_id: int = Field(gt=0)
