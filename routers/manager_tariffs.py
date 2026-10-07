from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    CREATE_MANAGER_TARIFF,
    PUBLISH_MANAGER_INSTALLATION_PRICE_BOOK,
    LIST_MANAGER_INSTALLATION_LEGACY_COMPARISON,
    CREATE_MANAGER_TARIFF_RULE,
    DELETE_MANAGER_TARIFF,
    DELETE_MANAGER_TARIFF_RULE,
    LIST_MANAGER_FAVORITE_TARIFF_RULES,
    LIST_MANAGER_QUICK_TARIFFS,
    LIST_MANAGER_TARIFFS,
    LIST_MANAGER_TARIFF_RULES,
    UPDATE_MANAGER_TARIFF,
    UPDATE_MANAGER_TARIFF_RULE,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    ManagerActionMessageResponse,
    ManagerQuickTariffListResponse,
    ManagerTariffCreatePayload,
    ManagerTariffListResponse,
    ManagerTariffResponse,
    ManagerTariffRuleCreatePayload,
    ManagerTariffRuleListResponse,
    ManagerTariffRuleResponse,
    ManagerTariffServiceKind,
    ManagerTariffUpdatePayload,
    ManagerTariffRuleUpdatePayload,
)
from services.tariffs_service import TariffsService
from services.installation_price_book_service import InstallationPriceBookService
from schemas_installation_price_book import InstallationPublishResponse, InstallationLegacyComparisonResponse

router = APIRouter(
    prefix="/api/manager/tariffs",
    tags=["manager/tariffs"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


@router.post(
    "/price-book/publish",
    response_model=InstallationPublishResponse,
    operation_id=PUBLISH_MANAGER_INSTALLATION_PRICE_BOOK,
)
async def publish_manager_installation_price_book(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    username: str = Depends(get_current_username),
):
    """
    Validate active typed installation drafts and atomically publish an immutable tenant
    price-book revision under the publication lock. Invalid/empty pricing, conflicting codes
    or equally specific matchers, incompatible historical matcher/component identity or
    invalid required prices return 422 without publication. An unchanged fingerprint reuses
    the current revision. New publication changes future resolution and retires legacy
    installation-rate/estimate writes; accepted estimates and documents retain their
    snapshots.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await InstallationPriceBookService.publish(session, tenant_scope, actor=username)


@router.get(
    "/price-book/legacy-comparison",
    response_model=InstallationLegacyComparisonResponse,
    operation_id=LIST_MANAGER_INSTALLATION_LEGACY_COMPARISON,
)
async def list_manager_installation_legacy_comparison(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read a paginated comparison of legacy installation tariff data for review, using offset
    and limit 1–100. This report does not migrate prices, repair drafts, publish a book or
    rewrite accepted estimates.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await InstallationPriceBookService.legacy_comparison(session, tenant_scope, offset=offset, limit=limit)


@router.get("", response_model=ManagerTariffListResponse, operation_id=LIST_MANAGER_TARIFFS)
async def list_manager_tariffs(
    service_kind: ManagerTariffServiceKind | None = Query(None),
    include_inactive: bool = Query(True),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read the tenant’s service tariff drafts, optionally by service kind; inactive entries
    are included by default. This route is unpaginated. Draft amounts may differ from the
    active immutable installation price book and do not themselves define its current
    resolver.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    items = await TariffsService.get_all_tariffs(
        session=session,
        service_kind=service_kind,
        include_inactive=include_inactive,
        tenant_scope=tenant_scope,
    )
    return ManagerTariffListResponse(items=items)


@router.get("/quick-add", response_model=ManagerQuickTariffListResponse, operation_id=LIST_MANAGER_QUICK_TARIFFS)
async def list_manager_quick_tariffs(
    q: str = Query(""),
    service_kind: ManagerTariffServiceKind | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read bounded quick-add service suggestions with optional text filter and limit 1–100.
    These combine active ordinary draft tariffs and fixed published installation standards;
    after book publication legacy installation drafts are excluded. Published standards may
    have no legacy tariff_id. Suggestions for free commercial rows do not confirm an
    installation estimate or establish equipment identity.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    items = await TariffsService.list_quick_add_tariffs(
        session=session,
        service_kind=service_kind,
        q=q,
        limit=limit,
        tenant_scope=tenant_scope,
    )
    return ManagerQuickTariffListResponse(items=items)


@router.post("", response_model=ManagerTariffResponse, status_code=status.HTTP_201_CREATED, operation_id=CREATE_MANAGER_TARIFF)
async def create_manager_tariff(
    payload: ManagerTariffCreatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create a tenant service tariff draft with its calculation/matching and price fields.
    Required nonblank short name is validated; included route length is reset to zero for
    service kinds that do not support it. This does not publish an installation price book.
    No idempotency receipt exists, so repeated creation can add another draft.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await TariffsService.create_tariff(session, payload, tenant_scope)


@router.put("/{tariff_id}", response_model=ManagerTariffResponse, operation_id=UPDATE_MANAGER_TARIFF)
async def update_manager_tariff(
    tariff_id: int,
    payload: ManagerTariffUpdatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Update only submitted tariff draft fields. Missing/out-of-scope tariff returns 404 and
    blank short name fails validation. Included route length is reset to zero when
    incompatible with the service kind. Changes take effect in the draft dictionary;
    published installation pricing and accepted estimate snapshots remain unchanged until a
    separate successful publication.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await TariffsService.update_tariff(
        session, tariff_id, payload, tenant_scope
    )


@router.delete("/{tariff_id}", response_model=ManagerActionMessageResponse, operation_id=DELETE_MANAGER_TARIFF)
async def delete_manager_tariff(
    tariff_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Permanently delete a tenant tariff draft. Missing/out-of-scope tariff returns 404,
    including repeats. This is not publication of a replacement price book; existing
    immutable published installation data is not rewritten.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    await TariffsService.delete_tariff(session, tariff_id, tenant_scope)
    return ManagerActionMessageResponse(message="Tariff deleted successfully")


@router.get(
    "/rules/favorites",
    response_model=ManagerTariffRuleListResponse,
    operation_id=LIST_MANAGER_FAVORITE_TARIFF_RULES,
)
async def list_manager_favorite_tariff_rules(
    service_kind: ManagerTariffServiceKind = Query(...),
    include_inactive: bool = Query(False),
    exclude_tariff_id: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read favorite draft rules for the required service kind, optionally excluding one
    tariff. Inactive rules are excluded by default and the result is unpaginated. These are
    reusable draft options, not accepted estimate components or automatically attached order
    lines.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    items = await TariffsService.list_favorite_tariff_rules(
        session=session,
        service_kind=service_kind,
        include_inactive=include_inactive,
        exclude_tariff_id=exclude_tariff_id,
        tenant_scope=tenant_scope,
    )
    return ManagerTariffRuleListResponse(items=items)


@router.get(
    "/{tariff_id}/rules",
    response_model=ManagerTariffRuleListResponse,
    operation_id=LIST_MANAGER_TARIFF_RULES,
)
async def list_manager_tariff_rules(
    tariff_id: int,
    include_inactive: bool = Query(True),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read draft rules belonging to one tenant tariff; inactive rules are included by default
    and no pagination is accepted. Missing/out-of-scope tariff returns 404. This does not
    select a rule into an estimate or publish installation components.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    items = await TariffsService.list_tariff_rules(
        session=session,
        tariff_id=tariff_id,
        include_inactive=include_inactive,
        tenant_scope=tenant_scope,
    )
    return ManagerTariffRuleListResponse(items=items)


@router.post(
    "/{tariff_id}/rules",
    response_model=ManagerTariffRuleResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_TARIFF_RULE,
)
async def create_manager_tariff_rule(
    tariff_id: int,
    payload: ManagerTariffRuleCreatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create a rule under a tenant tariff; missing parent returns 404. An existing rule with
    matching semantic fields is reused, and a requested favorite flag may promote it to
    favorite. This deduplication does not apply every submitted field to an existing rule
    and is not an idempotency receipt. Changes remain draft data until a separate
    installation price-book publication.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await TariffsService.create_tariff_rule(
        session=session,
        tariff_id=tariff_id,
        payload=payload,
        tenant_scope=tenant_scope,
    )


@router.put(
    "/{tariff_id}/rules/{rule_id}",
    response_model=ManagerTariffRuleResponse,
    operation_id=UPDATE_MANAGER_TARIFF_RULE,
)
async def update_manager_tariff_rule(
    tariff_id: int,
    rule_id: int,
    payload: ManagerTariffRuleUpdatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Update submitted draft-rule fields after cleaning text. Missing/out-of-scope tariff or
    rule belonging to another tariff returns 404. This edits the draft component definition
    without modifying current published installation entries or saved estimate snapshots.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await TariffsService.update_tariff_rule(
        session=session,
        tariff_id=tariff_id,
        rule_id=rule_id,
        payload=payload,
        tenant_scope=tenant_scope,
    )


@router.delete(
    "/{tariff_id}/rules/{rule_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_TARIFF_RULE,
)
async def delete_manager_tariff_rule(
    tariff_id: int,
    rule_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Permanently remove a draft rule from its tenant tariff. Missing/out-of-scope parent or
    rule returns 404, including repeats. Current immutable price-book revisions and accepted
    installation snapshots are not rewritten.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    await TariffsService.delete_tariff_rule(
        session=session,
        tariff_id=tariff_id,
        rule_id=rule_id,
        tenant_scope=tenant_scope,
    )
    return ManagerActionMessageResponse(message="Tariff rule deleted successfully")
