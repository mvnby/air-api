"""Authentication dependency for the private Telegram bot API."""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings


bot_service_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="BotServiceBearer",
    description="Dedicated bearer token used only by the MVN Telegram bot service.",
)


async def require_bot_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bot_service_bearer),
) -> None:
    configured = settings.BOT_API_TOKEN.strip()
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot API token is not configured",
        )

    provided = credentials.credentials if credentials is not None else ""
    if not provided or not secrets.compare_digest(provided, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bot API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
