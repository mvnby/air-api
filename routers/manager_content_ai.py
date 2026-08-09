"""Persistence-free Manager endpoints that return AI content drafts."""

from fastapi import APIRouter, Depends, HTTPException

from core.security import AuthenticatedUser, get_current_auth_context, get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_BRAND_SHORT_DESCRIPTION_AI_DRAFT,
    CREATE_MANAGER_FEATURE_CONTENT_AI_DRAFT,
    CREATE_MANAGER_SERIES_CONTENT_AI_DRAFT,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_content_ai import (
    BrandShortDescriptionDraft,
    BrandShortDescriptionDraftRequest,
    FeatureContentDraft,
    FeatureContentDraftRequest,
    ProductSeriesContentDraft,
    ProductSeriesContentDraftRequest,
)
from services.deepseek_provider_service import DefectActAIProviderError
from services.manager_content_ai_service import ManagerContentAIService
from services.manager_content_ai_limiter import (
    ManagerContentAIRateLimitError,
    manager_content_ai_limiter,
)
from services.manager_content_source_service import ManagerContentSourceError


router = APIRouter(
    prefix="/api/manager/content-ai",
    tags=["manager-content-ai"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)
service = ManagerContentAIService()


@router.post(
    "/brands/short-description/draft",
    response_model=BrandShortDescriptionDraft,
    operation_id=CREATE_MANAGER_BRAND_SHORT_DESCRIPTION_AI_DRAFT,
)
async def create_manager_brand_short_description_ai_draft(
    payload: BrandShortDescriptionDraftRequest,
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> BrandShortDescriptionDraft:
    try:
        async with manager_content_ai_limiter.limit(_limit_key(auth)):
            return await service.generate_brand_short_description_draft(payload)
    except ManagerContentAIRateLimitError as exc:
        raise _rate_limit_http_error(exc) from exc
    except DefectActAIProviderError as exc:
        raise _provider_http_error(exc) from exc


@router.post(
    "/features/draft",
    response_model=FeatureContentDraft,
    operation_id=CREATE_MANAGER_FEATURE_CONTENT_AI_DRAFT,
)
async def create_manager_feature_content_ai_draft(
    payload: FeatureContentDraftRequest,
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> FeatureContentDraft:
    try:
        async with manager_content_ai_limiter.limit(_limit_key(auth)):
            return await service.generate_feature_draft(payload)
    except ManagerContentAIRateLimitError as exc:
        raise _rate_limit_http_error(exc) from exc
    except ManagerContentSourceError as exc:
        raise _source_http_error(exc) from exc
    except DefectActAIProviderError as exc:
        raise _provider_http_error(exc) from exc


@router.post(
    "/series/draft",
    response_model=ProductSeriesContentDraft,
    operation_id=CREATE_MANAGER_SERIES_CONTENT_AI_DRAFT,
)
async def create_manager_series_content_ai_draft(
    payload: ProductSeriesContentDraftRequest,
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> ProductSeriesContentDraft:
    try:
        async with manager_content_ai_limiter.limit(_limit_key(auth)):
            return await service.generate_series_draft(payload)
    except ManagerContentAIRateLimitError as exc:
        raise _rate_limit_http_error(exc) from exc
    except ManagerContentSourceError as exc:
        raise _source_http_error(exc) from exc
    except DefectActAIProviderError as exc:
        raise _provider_http_error(exc) from exc


def _source_http_error(exc: ManagerContentSourceError) -> HTTPException:
    upstream_codes = {"source_unavailable", "source_http_error"}
    status_code = 502 if exc.code in upstream_codes else 422
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _limit_key(auth: AuthenticatedUser) -> str:
    return f"{auth.tenant_id or 0}:{auth.username}"


def _rate_limit_http_error(exc: ManagerContentAIRateLimitError) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={"code": "content_ai_rate_limited", "message": str(exc)},
        headers={"Retry-After": str(exc.retry_after)},
    )


def _provider_http_error(exc: DefectActAIProviderError) -> HTTPException:
    status_code = 503 if exc.retryable or exc.code == "not_configured" else 502
    if exc.code == "invalid_response":
        status_code = 502
    return HTTPException(
        status_code=status_code,
        detail={
            "code": exc.code,
            "message": str(exc),
            "retryable": exc.retryable,
        },
    )
