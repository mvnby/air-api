from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    CALCULATE_MANAGER_INSTALLATION_MATERIAL_COST,
    CREATE_MANAGER_INSTALLATION_MATERIAL_PRICE,
    LIST_MANAGER_INSTALLATION_MATERIAL_PRICES,
    UPDATE_MANAGER_INSTALLATION_MATERIAL_PRICE,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_installation_materials import (
    InstallationMaterialCostInput,
    InstallationMaterialCostResult,
    InstallationMaterialPriceInput,
    InstallationMaterialPriceItem,
    InstallationMaterialPriceList,
    InstallationMaterialPriceUpdate,
)
from services.installation_material_cost_service import (
    calculate_material_cost,
    list_material_prices,
    save_material_price,
)

router = APIRouter(
    prefix="/api/manager/installation-materials",
    tags=["manager-installation-materials"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


@router.get("", response_model=InstallationMaterialPriceList, operation_id=LIST_MANAGER_INSTALLATION_MATERIAL_PRICES)
async def list_manager_installation_material_prices(
    response: Response,
    q: str = Query("", max_length=180), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Read the authenticated company's private purchase prices for installation materials."""
    response.headers["Cache-Control"] = "private, no-store"
    return await list_material_prices(session, scope, query=q, offset=offset, limit=limit)


@router.post("", status_code=201, response_model=InstallationMaterialPriceItem,
             operation_id=CREATE_MANAGER_INSTALLATION_MATERIAL_PRICE)
async def create_manager_installation_material_price(
    payload: InstallationMaterialPriceInput,
    session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Record the listed purchase price and quantity of a supplier pack."""
    return await save_material_price(session, scope, payload)


@router.put("/{price_id}", response_model=InstallationMaterialPriceItem,
            operation_id=UPDATE_MANAGER_INSTALLATION_MATERIAL_PRICE)
async def update_manager_installation_material_price(
    price_id: int, payload: InstallationMaterialPriceUpdate,
    session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Replace a price using its current version in the authenticated company."""
    return await save_material_price(session, scope, payload, price_id=price_id)


@router.post("/calculate", response_model=InstallationMaterialCostResult,
             operation_id=CALCULATE_MANAGER_INSTALLATION_MATERIAL_COST)
async def calculate_manager_installation_material_cost(
    payload: InstallationMaterialCostInput,
    session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Calculate consumption costs in BYN from current prices. This read saves no order or estimate."""
    return await calculate_material_cost(session, scope, payload)
