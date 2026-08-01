"""Trusted tenant/storefront dependencies for public and internal callers."""

from fastapi import Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from services.tenant_scope_service import SystemTenantScopeResolver, TenantScope
from services.storefront_context_service import StorefrontContextService
from services.storefront_context_signature_service import (
    StorefrontContextSignatureService,
)


async def get_system_tenant_scope(
    session: AsyncSession = Depends(get_session),
) -> TenantScope:
    """Resolve the canonical MVN scope without accepting client-owned input."""
    return await SystemTenantScopeResolver.resolve(session)


async def get_public_tenant_scope(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    storefront_host: str | None = Header(
        default=None,
        alias="X-MVN-Storefront-Host",
    ),
    storefront_timestamp: str | None = Header(
        default=None,
        alias="X-MVN-Storefront-Timestamp",
    ),
    storefront_signature: str | None = Header(
        default=None,
        alias="X-MVN-Storefront-Signature",
    ),
) -> TenantScope:
    """Resolve public provenance without trusting browser-owned tenant IDs.

    No headers preserves the current canonical MVN behaviour. Selecting any
    other active storefront requires the complete short-lived HMAC envelope
    produced by a trusted website server or edge proxy.
    """

    supplied = (
        storefront_host is not None,
        storefront_timestamp is not None,
        storefront_signature is not None,
    )
    if not any(supplied):
        return await SystemTenantScopeResolver.resolve(session)
    if not all(supplied):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incomplete storefront context",
        )

    primary_secret = settings.STOREFRONT_CONTEXT_SIGNING_SECRET
    if not primary_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid storefront context",
        )

    try:
        timestamp = int(str(storefront_timestamp))
        hostname = StorefrontContextSignatureService.verify_any(
            secrets=(
                primary_secret,
                settings.STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET,
            ),
            timestamp=timestamp,
            method=request.method,
            path=request.url.path,
            hostname=str(storefront_host),
            signature=str(storefront_signature),
            max_age_seconds=settings.STOREFRONT_CONTEXT_MAX_AGE_SECONDS,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid storefront context",
        ) from exc

    context = await StorefrontContextService.resolve_by_host(session, hostname)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storefront is unavailable",
        )
    # Signed projections vary by a trusted header rather than by URL. Never
    # let a shared browser/CDN cache replay one storefront into another.
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["CDN-Cache-Control"] = "no-store"
    response.headers["Vary"] = "X-MVN-Storefront-Host"
    return TenantScope(
        tenant_id=context.tenant_id,
        storefront_id=context.storefront_id,
        is_system=context.tenant_is_system,
    )
