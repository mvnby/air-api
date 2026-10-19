"""Shared catalog compatibility editing; no tenant commercial writes."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_catalog_username
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_catalog_accessories import ManagerAccessoriesWorkspace, ProductAccessoriesUpdate, SeriesAccessoriesUpdate
from services.catalog_accessory_service import CatalogAccessoryService


router = APIRouter(
    prefix="/api/manager/catalog-accessories", tags=["manager catalog accessories"],
    dependencies=[Depends(get_current_catalog_username)], route_class=ManagerPermissionRoute,
)


@router.get("/series/{target_id}", response_model=ManagerAccessoriesWorkspace, operation_id="get_manager_series_accessories")
async def get_series_accessories(target_id: int = Path(ge=1), session: AsyncSession = Depends(get_session)):
    """Read ordered accessory product links for a shared series. Catalog master edit
    permission is required; missing series returns 404. Published and unpublished
    accessories are shown for editing. Compatibility does not imply availability,
    automatic order lines or a Wi-Fi capability. Prices are resolved on public read.
    """
    return await CatalogAccessoryService.get_workspace(session, target_type="series", target_id=target_id)


@router.put("/series/{target_id}", response_model=ManagerAccessoriesWorkspace, operation_id="set_manager_series_accessories")
async def set_series_accessories(payload: SeriesAccessoriesUpdate, target_id: int = Path(ge=1), session: AsyncSession = Depends(get_session)):
    """Replace the complete ordered accessory set for a shared series (up to 100).
    Catalog master edit permission is required. Missing series returns 404; missing
    products, non-accessory products or a self-compatible series returns 400;
    duplicate/nonpositive IDs return 422. Empty list clears links. Model exceptions
    remain intact. Identical saves preserve catalog revision and ordering; repeating
    the exact PUT is safe. This updates compatibility only, never orders or offers.
    """
    return await CatalogAccessoryService.set_series_accessories(session, series_id=target_id, payload=payload)


@router.get("/products/{target_id}", response_model=ManagerAccessoriesWorkspace, operation_id="get_manager_product_accessories")
async def get_product_accessories(target_id: int = Path(ge=1), session: AsyncSession = Depends(get_session)):
    """Read series accessories and explicit model includes/excludes for a shared
    product. Catalog master edit permission is required; missing product returns
    404. inherited records their series origin, override is true/false for model
    decisions or null for inheritance, and is_enabled is the effective decision.
    Compatibility never follows from matching brands or Wi-Fi flags.
    """
    return await CatalogAccessoryService.get_workspace(session, target_type="product", target_id=target_id)


@router.put("/products/{target_id}", response_model=ManagerAccessoriesWorkspace, operation_id="set_manager_product_accessories")
async def set_product_accessories(payload: ProductAccessoriesUpdate, target_id: int = Path(ge=1), session: AsyncSession = Depends(get_session)):
    """Replace all explicit model overrides (up to 100). Catalog master edit
    permission is required. is_enabled=true includes an accessory, false excludes
    it, and omitting a previous override restores series inheritance. Series order
    stays intact; additional model items follow it in submitted order. Missing
    product returns 404; invalid accessory kind, missing accessory or self-link
    returns 400; duplicate IDs return 422. Repeating an unchanged PUT is safe and
    creates no new catalog revision. No order, price or tenant offer is changed.
    """
    return await CatalogAccessoryService.set_product_accessories(session, product_id=target_id, payload=payload)
