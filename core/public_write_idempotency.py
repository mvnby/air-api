from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from core.tenant_scope import (
    VerifiedPublicStorefrontRequest,
    verify_public_storefront_request,
)
from services.public_write_idempotency_service import (
    PublicWriteIdempotencyService,
)


async def get_public_write_idempotency_key(
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    verified: VerifiedPublicStorefrontRequest = Depends(
        verify_public_storefront_request
    ),
) -> str:
    """Require client keys for signed traffic; bridge canonical legacy callers."""

    if idempotency_key is not None:
        try:
            return PublicWriteIdempotencyService.normalize_key(idempotency_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if verified.signed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid storefront context",
        )
    return f"legacy:{secrets.token_hex(16)}"


async def get_required_public_write_idempotency_key(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> str:
    try:
        return PublicWriteIdempotencyService.normalize_key(idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
