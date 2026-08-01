"""Trusted tenant/storefront dependencies for public and internal callers."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from core.storefront_request_auth import (
    STOREFRONT_VERIFIED_ENVELOPE_SCOPE_KEY,
    VerifiedStorefrontEnvelope,
    resolve_allowed_api_hostname,
)
from core.storefront_request_envelope import (
    private_storefront_response_headers,
    storefront_signing_header_state,
)
from services.storefront_context_service import (
    StorefrontContext,
    StorefrontContextService,
)
from services.tenant_scope_service import SystemTenantScopeResolver, TenantScope


@dataclass(frozen=True)
class VerifiedPublicStorefrontRequest:
    signed: bool
    context: StorefrontContext | None = None


def _invalid_context() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid storefront context",
        headers=private_storefront_response_headers(),
    )


def _request_api_hostname(request: Request) -> str:
    return resolve_allowed_api_hostname(
        raw_headers=request.scope.get("headers", ()),
        allowed_api_hosts=settings.storefront_context_api_hosts,
    )


async def get_system_tenant_scope(
    session: AsyncSession = Depends(get_session),
) -> TenantScope:
    """Resolve the canonical MVN scope without accepting client-owned input."""
    return await SystemTenantScopeResolver.resolve(session)


def _verified_public_storefront_envelope(
    request: Request,
) -> VerifiedStorefrontEnvelope | None:
    has_signing_headers, _ = storefront_signing_header_state(
        request.scope.get("headers", ())
    )
    if not has_signing_headers:
        try:
            _request_api_hostname(request)
        except (TypeError, ValueError) as exc:
            raise _invalid_context() from exc
        if settings.STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS:
            raise _invalid_context()
        return None

    verified = request.scope.get(STOREFRONT_VERIFIED_ENVELOPE_SCOPE_KEY)
    if not isinstance(verified, VerifiedStorefrontEnvelope):
        raise _invalid_context()
    return verified


async def verify_public_storefront_request(
    verified: VerifiedStorefrontEnvelope | None = Depends(
        _verified_public_storefront_envelope
    ),
    session: AsyncSession = Depends(get_session),
) -> VerifiedPublicStorefrontRequest:
    """Resolve a request authenticated by the outer ASGI gateway."""

    if verified is None:
        return VerifiedPublicStorefrontRequest(signed=False)
    context = await StorefrontContextService.resolve_by_host(
        session,
        verified.hostname,
    )
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storefront is unavailable",
            headers=private_storefront_response_headers(),
        )
    return VerifiedPublicStorefrontRequest(signed=True, context=context)


async def get_public_tenant_scope(
    verified: VerifiedPublicStorefrontRequest = Depends(
        verify_public_storefront_request
    ),
    session: AsyncSession = Depends(get_session),
) -> TenantScope:
    """Resolve exact public provenance after authenticating the request."""

    if verified.context is None:
        return await SystemTenantScopeResolver.resolve(session)
    context = verified.context
    return TenantScope(
        tenant_id=context.tenant_id,
        storefront_id=context.storefront_id,
        is_system=context.tenant_is_system,
    )
