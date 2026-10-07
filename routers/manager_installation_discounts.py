"""Platform Manager API for catalog-product installation discount policies."""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    DELETE_MANAGER_INSTALLATION_DISCOUNT_RULE,
    LIST_MANAGER_INSTALLATION_DISCOUNT_RULES,
    SEARCH_MANAGER_INSTALLATION_DISCOUNT_PRODUCTS,
    UPDATE_MANAGER_INSTALLATION_DISCOUNT_POLICY,
    UPSERT_MANAGER_INSTALLATION_DISCOUNT_RULE,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_manager_installation_discounts import (
    ManagerInstallationDiscountPolicyResponse,
    ManagerInstallationDiscountPolicyUpdatePayload,
    ManagerInstallationDiscountProductResponse,
    ManagerInstallationDiscountProductSearchResponse,
    ManagerInstallationDiscountRuleListResponse,
    ManagerInstallationDiscountRuleUpdatePayload,
)
from services.installation_discount_service import InstallationDiscountService


router = APIRouter(
    prefix="/api/manager/installation-discounts",
    tags=["manager/installation-discounts"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "",
    response_model=ManagerInstallationDiscountRuleListResponse,
    operation_id=LIST_MANAGER_INSTALLATION_DISCOUNT_RULES,
)
async def list_manager_installation_discount_rules(
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """
    Read shared installation-discount policy and product overrides with current
    margin/eligibility projections. page starts at 1 and limit is 1–100. The list covers
    stored overrides rather than every catalog product, and does not change an accepted
    estimate.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await InstallationDiscountService.list_rules(
        session,
        search=search,
        page=page,
        limit=limit,
    )


@router.get(
    "/products/search",
    response_model=ManagerInstallationDiscountProductSearchResponse,
    operation_id=SEARCH_MANAGER_INSTALLATION_DISCOUNT_PRODUCTS,
)
async def search_manager_installation_discount_products(
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    """
    Search shared product candidates for discount overrides, returning current price/margin
    eligibility and whether an override exists. q is at most 200 characters and limit is
    1–50. This only reads suggestions; it does not create rules or recalculate accepted
    installation snapshots.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return ManagerInstallationDiscountProductSearchResponse(
        items=await InstallationDiscountService.search_products(
            session,
            search=q,
            limit=limit,
        )
    )


@router.put(
    "/policy",
    response_model=ManagerInstallationDiscountPolicyResponse,
    operation_id=UPDATE_MANAGER_INSTALLATION_DISCOUNT_POLICY,
)
async def update_manager_installation_discount_policy(
    payload: ManagerInstallationDiscountPolicyUpdatePayload,
    session: AsyncSession = Depends(get_session),
):
    """
    Save the shared enable flag, default installation discount and minimum margin policy.
    The legacy installation-discount fallback is synchronized when toggling this policy.
    This affects future pricing decisions, not tenant rate dictionaries or already accepted
    estimates; a repeated PUT saves the submitted policy without an idempotency receipt.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await InstallationDiscountService.update_policy(session, payload)


@router.put(
    "/products/{product_id}",
    response_model=ManagerInstallationDiscountProductResponse,
    operation_id=UPSERT_MANAGER_INSTALLATION_DISCOUNT_RULE,
)
async def upsert_manager_installation_discount_rule(
    product_id: int,
    payload: ManagerInstallationDiscountRuleUpdatePayload,
    session: AsyncSession = Depends(get_session),
):
    """
    Create or update the unique installation-discount override for one shared product,
    returning its current economic decision after saving. Missing product returns 404.
    Repeating the same product PUT reuses that override; existing accepted estimate
    snapshots are not rewritten.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await InstallationDiscountService.upsert_rule(
        session,
        product_id=product_id,
        payload=payload,
    )


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id=DELETE_MANAGER_INSTALLATION_DISCOUNT_RULE,
)
async def delete_manager_installation_discount_rule(
    product_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Permanently remove a product discount override and return 204 so future decisions use
    the shared policy fallback. Missing override returns 404, including repeats. This does
    not disable the global policy or change accepted estimates.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    await InstallationDiscountService.delete_rule(
        session,
        product_id=product_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
