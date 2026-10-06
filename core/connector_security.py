"""Dedicated bearer dependency: connector tokens never enter Manager JWT auth."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.database import get_session
from services.connector_auth_policy import ConnectorAuthError, issuer, resource
from services.connector_auth_service import ConnectorAuthService


def connector_actor(required_scope: str):
    challenge_scope = " ".join(dict.fromkeys(["kitlane:read", required_scope]))

    async def dependency(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> CommandActor:
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                401,
                "Connector bearer token required",
                headers={
                    "WWW-Authenticate": f'Bearer resource_metadata="{issuer()}/.well-known/oauth-protected-resource", scope="{challenge_scope}"',
                },
            )
        try:
            return await ConnectorAuthService.resolve_actor(
                session, token, required_scope
            )
        except ConnectorAuthError as exc:
            raise HTTPException(
                exc.status_code,
                {"code": exc.error, "message": str(exc)},
                headers={
                    "WWW-Authenticate": f'Bearer error="{exc.error}", resource_metadata="{issuer()}/.well-known/oauth-protected-resource", scope="{challenge_scope}"',
                },
            ) from exc

    return dependency


def connector_resource_metadata() -> dict:
    return {
        "resource": resource(),
        "authorization_servers": [issuer()],
        "scopes_supported": [
            "kitlane:read",
            "kitlane:incoming:write",
            "kitlane:tasks:write",
        ],
        "bearer_methods_supported": ["header"],
        "resource_name": "Kitlane",
    }
