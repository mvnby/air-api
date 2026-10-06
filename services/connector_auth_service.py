"""OAuth state transitions and live Kitlane authorization, independent of HTTP."""

import hmac
from datetime import timedelta
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.security import AuthenticatedUser
from models.connector_auth import (
    ConnectorAuthorizationCode,
    ConnectorAuthEvent,
    ConnectorConsent,
    ConnectorGrant,
    ConnectorToken,
    now_utc,
)
from models.staff import StaffUser
from models.tenancy import Storefront, Tenant, TenantMembership, TenantScope
from schemas_connector_auth import ConnectorGrantResponse, ConnectorTokenResponse
from services.connector_auth_policy import (
    CHALLENGE,
    CLIENT_ID,
    ROLE_RANK,
    SCOPES,
    VERIFIER,
    ConnectorAuthError,
    digest,
    pkce,
    resource,
    secret,
    utc,
    validate_client,
    validate_redirect,
)
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.manager_tenant_access_service import (
    ManagerTenantAccessResolutionError,
    ManagerTenantAccessResolver,
)
from services.staff_user_service import StaffUserService


class ConnectorAuthService:
    @staticmethod
    async def consent_labels(
        session: AsyncSession, pending: ConnectorConsent
    ) -> tuple[str, str]:
        tenant = await session.get(Tenant, pending.tenant_id)
        storefront = await session.get(Storefront, pending.storefront_id)
        if tenant is None or storefront is None:
            raise ConnectorAuthError(
                "access_denied", "Consent context no longer exists", 403
            )
        return tenant.display_name, storefront.display_name

    @staticmethod
    async def _live_actor(session: AsyncSession, snapshot) -> CommandActor:
        user = await session.get(
            StaffUser, snapshot.staff_user_id, populate_existing=True
        )
        if (
            user is None
            or not StaffUserService.is_active(user)
            or user.must_change_password
            or user.auth_version != snapshot.auth_version
        ):
            raise ConnectorAuthError(
                "invalid_grant", "Kitlane account credentials changed", 401
            )
        state = await LegacyOwnerAuthGuard.state(session)
        await session.refresh(state)
        if not LegacyOwnerAuthGuard.allows_staff_identity(
            state, staff_user_id=user.id, username=user.username or ""
        ):
            raise ConnectorAuthError(
                "invalid_grant", "Kitlane identity is no longer active", 401
            )
        try:
            # Resolver selects ORM entities. Refresh the security-bearing rows so
            # an earlier call in this same session cannot cache a revoked role or
            # a newly read-only tenant across MCP requests/tool calls.
            await session.get(
                TenantMembership, snapshot.membership_id, populate_existing=True
            )
            await session.get(Tenant, snapshot.tenant_id, populate_existing=True)
            access = await ManagerTenantAccessResolver.resolve(
                session, staff_user_id=user.id
            )
        except ManagerTenantAccessResolutionError:
            raise ConnectorAuthError(
                "invalid_grant", "Active membership required", 401
            ) from None
        storefront = await session.get(
            Storefront, snapshot.storefront_id, populate_existing=True
        )
        if (
            access.membership_id != snapshot.membership_id
            or access.tenant_scope.tenant_id != snapshot.tenant_id
            or ROLE_RANK.get(access.role, 0) < ROLE_RANK.get(snapshot.role, 99)
            or storefront is None
            or storefront.status != "active"
            or storefront.tenant_id != snapshot.tenant_id
        ):
            raise ConnectorAuthError("invalid_grant", "Kitlane access changed", 401)
        if access.tenant_scope.demo_read_only and any(
            scope.endswith(":write") for scope in snapshot.scopes
        ):
            raise ConnectorAuthError(
                "invalid_grant", "Write access is unavailable", 401
            )
        return CommandActor(
            staff_user_id=user.id,
            username=user.username or str(user.telegram_id or ""),
            tenant_scope=TenantScope(
                tenant_id=snapshot.tenant_id,
                storefront_id=snapshot.storefront_id,
                is_system=access.tenant_scope.is_system,
                demo_read_only=access.tenant_scope.demo_read_only,
            ),
            channel="chatgpt",
        )

    @staticmethod
    async def start_consent(
        session: AsyncSession,
        auth: AuthenticatedUser,
        session_credential: str,
        *,
        client_id: str,
        redirect_uri: str,
        requested_resource: str,
        scope: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
        response_type: str,
    ) -> tuple[ConnectorConsent, str]:
        validate_client(client_id, requested_resource)
        validate_redirect(redirect_uri)
        scopes = sorted(set(scope.split()))
        if "kitlane:read" not in scopes or not set(scopes) <= SCOPES:
            raise ConnectorAuthError(
                "invalid_scope", "kitlane:read and supported scopes are required"
            )
        if (
            response_type != "code"
            or code_challenge_method != "S256"
            or not CHALLENGE.fullmatch(code_challenge)
        ):
            raise ConnectorAuthError(
                "invalid_request", "Authorization code with PKCE S256 required"
            )
        if not state or len(state) > 1024:
            raise ConnectorAuthError("invalid_request", "Bounded OAuth state required")
        if (
            not auth.staff_user_id
            or not auth.tenant_membership_id
            or auth.auth_version is None
        ):
            raise ConnectorAuthError(
                "access_denied", "A named staff account is required", 403
            )
        nonce = secret("csrf")
        pending = ConnectorConsent(
            id=secret("consent"),
            staff_user_id=auth.staff_user_id,
            tenant_id=auth.tenant_id,
            storefront_id=auth.storefront_id,
            membership_id=auth.tenant_membership_id,
            auth_version=auth.auth_version,
            role=auth.role,
            session_hash=digest(session_credential),
            csrf_hash=digest(nonce),
            client_id=client_id,
            redirect_uri=redirect_uri,
            resource=requested_resource,
            scopes=scopes,
            state=state,
            code_challenge=code_challenge,
            expires_at=now_utc() + timedelta(minutes=10),
        )
        await ConnectorAuthService._live_actor(session, pending)
        session.add(pending)
        await session.commit()
        return pending, nonce

    @staticmethod
    async def finish_consent(
        session: AsyncSession,
        auth: AuthenticatedUser,
        session_credential: str,
        *,
        consent_id: str,
        nonce: str,
        allow: bool,
    ) -> str:
        pending = (
            await session.execute(
                select(ConnectorConsent)
                .where(ConnectorConsent.id == consent_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            pending is None
            or pending.consumed_at is not None
            or utc(pending.expires_at) <= now_utc()
            or pending.staff_user_id != auth.staff_user_id
            or pending.tenant_id != auth.tenant_id
            or pending.storefront_id != auth.storefront_id
            or not hmac.compare_digest(pending.session_hash, digest(session_credential))
            or not hmac.compare_digest(pending.csrf_hash, digest(nonce))
        ):
            raise ConnectorAuthError(
                "invalid_request", "Consent expired or session/CSRF mismatch", 403
            )
        await ConnectorAuthService._live_actor(session, pending)
        # Configuration changes must not revive a formerly valid redirect/resource.
        validate_client(pending.client_id, pending.resource)
        validate_redirect(pending.redirect_uri)
        pending.consumed_at = now_utc()
        params = {"state": pending.state}
        if allow:
            grant = ConnectorGrant(
                staff_user_id=pending.staff_user_id,
                tenant_id=pending.tenant_id,
                storefront_id=pending.storefront_id,
                membership_id=pending.membership_id,
                auth_version=pending.auth_version,
                role=pending.role,
                client_id=pending.client_id,
                resource=pending.resource,
                scopes=pending.scopes,
                expires_at=now_utc() + timedelta(days=30),
            )
            session.add(grant)
            await session.flush()
            code = secret("code")
            session.add(
                ConnectorAuthorizationCode(
                    code_hash=digest(code),
                    grant_id=grant.id,
                    redirect_uri=pending.redirect_uri,
                    code_challenge=pending.code_challenge,
                    expires_at=now_utc() + timedelta(minutes=2),
                )
            )
            ConnectorAuthService._event(session, grant, "grant_authorized")
            params["code"] = code
        else:
            params["error"] = "access_denied"
        from services.connector_auth_policy import issuer

        params["iss"] = issuer()
        await session.commit()
        return (
            pending.redirect_uri
            + ("&" if "?" in pending.redirect_uri else "?")
            + urlencode(params)
        )

    @staticmethod
    def _event(session: AsyncSession, grant: ConnectorGrant, operation: str) -> None:
        session.add(
            ConnectorAuthEvent(
                grant_id=grant.id,
                staff_user_id=grant.staff_user_id,
                operation=operation,
            )
        )

    @staticmethod
    async def _grant(
        session: AsyncSession, grant_id: int, *, locked: bool = False
    ) -> tuple[ConnectorGrant, CommandActor]:
        query = (
            select(ConnectorGrant)
            .where(ConnectorGrant.id == grant_id)
            .execution_options(populate_existing=True)
        )
        if locked:
            query = query.with_for_update()
        grant = (await session.execute(query)).scalar_one_or_none()
        if (
            grant is None
            or grant.revoked_at is not None
            or utc(grant.expires_at) <= now_utc()
            or grant.client_id != CLIENT_ID
            or grant.resource != resource()
        ):
            raise ConnectorAuthError(
                "invalid_grant", "Connection expired or revoked", 401
            )
        actor = await ConnectorAuthService._live_actor(session, grant)
        return grant, actor

    @staticmethod
    async def _tokens(
        session: AsyncSession, grant: ConnectorGrant
    ) -> ConnectorTokenResponse:
        access, refresh = secret("access"), secret("refresh")
        current = now_utc()
        access_expiry = min(current + timedelta(minutes=15), utc(grant.expires_at))
        for raw, kind, expires in (
            (access, "access", access_expiry),
            (
                refresh,
                "refresh",
                min(current + timedelta(days=30), utc(grant.expires_at)),
            ),
        ):
            session.add(
                ConnectorToken(
                    token_hash=digest(raw),
                    grant_id=grant.id,
                    kind=kind,
                    expires_at=expires,
                )
            )
        await session.commit()
        return ConnectorTokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=int((access_expiry - current).total_seconds()),
            scope=" ".join(grant.scopes),
        )

    @staticmethod
    async def exchange_code(
        session: AsyncSession,
        *,
        code: str,
        client_id: str,
        redirect_uri: str,
        requested_resource: str,
        code_verifier: str,
    ) -> ConnectorTokenResponse:
        validate_client(client_id, requested_resource)
        validate_redirect(redirect_uri)
        row = (
            await session.execute(
                select(ConnectorAuthorizationCode)
                .where(ConnectorAuthorizationCode.code_hash == digest(code))
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            row is None
            or row.consumed_at is not None
            or utc(row.expires_at) <= now_utc()
            or row.redirect_uri != redirect_uri
            or not VERIFIER.fullmatch(code_verifier)
            or not hmac.compare_digest(row.code_challenge, pkce(code_verifier))
        ):
            raise ConnectorAuthError(
                "invalid_grant", "Invalid or consumed authorization code"
            )
        grant, _ = await ConnectorAuthService._grant(session, row.grant_id, locked=True)
        if grant.client_id != client_id or grant.resource != requested_resource:
            raise ConnectorAuthError("invalid_grant", "Code binding mismatch")
        row.consumed_at = now_utc()
        ConnectorAuthService._event(session, grant, "code_exchanged")
        return await ConnectorAuthService._tokens(session, grant)

    @staticmethod
    async def refresh(
        session: AsyncSession,
        *,
        refresh_token: str,
        client_id: str,
        requested_resource: str,
        scope: str | None = None,
    ) -> ConnectorTokenResponse:
        validate_client(client_id, requested_resource)
        row = (
            await session.execute(
                select(ConnectorToken)
                .where(
                    ConnectorToken.token_hash == digest(refresh_token),
                    ConnectorToken.kind == "refresh",
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise ConnectorAuthError("invalid_grant", "Unknown refresh token")
        grant, _ = await ConnectorAuthService._grant(session, row.grant_id, locked=True)
        if grant.client_id != client_id or grant.resource != requested_resource:
            raise ConnectorAuthError("invalid_grant", "Token binding mismatch")
        if row.consumed_at is not None:
            grant.revoked_at = now_utc()
            ConnectorAuthService._event(session, grant, "refresh_replay_revoked")
            await session.commit()
            raise ConnectorAuthError(
                "invalid_grant", "Refresh replay revoked the connection"
            )
        if utc(row.expires_at) <= now_utc():
            raise ConnectorAuthError("invalid_grant", "Refresh token expired")
        if scope is not None and set(scope.split()) != set(grant.scopes):
            raise ConnectorAuthError(
                "invalid_scope", "Refresh cannot change granted scopes"
            )
        row.consumed_at = now_utc()
        ConnectorAuthService._event(session, grant, "refresh_rotated")
        return await ConnectorAuthService._tokens(session, grant)

    @staticmethod
    async def resolve_actor(
        session: AsyncSession, token: str, required_scope: str
    ) -> CommandActor:
        row = (
            await session.execute(
                select(ConnectorToken)
                .where(
                    ConnectorToken.token_hash == digest(token),
                    ConnectorToken.kind == "access",
                )
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if row is None or utc(row.expires_at) <= now_utc():
            raise ConnectorAuthError(
                "invalid_token", "Access token expired or invalid", 401
            )
        try:
            grant, actor = await ConnectorAuthService._grant(session, row.grant_id)
        except ConnectorAuthError as exc:
            raise ConnectorAuthError("invalid_token", str(exc), 401) from exc
        if required_scope not in grant.scopes:
            raise ConnectorAuthError(
                "insufficient_scope", "Required scope was not authorized", 403
            )
        return actor

    @staticmethod
    async def list_grants(
        session: AsyncSession, auth: AuthenticatedUser
    ) -> list[ConnectorGrantResponse]:
        if not auth.staff_user_id:
            raise ConnectorAuthError(
                "access_denied", "Named staff account required", 403
            )
        rows = (
            (
                await session.execute(
                    select(ConnectorGrant)
                    .where(
                        ConnectorGrant.staff_user_id == auth.staff_user_id,
                        ConnectorGrant.tenant_id == auth.tenant_id,
                    )
                    .order_by(ConnectorGrant.id.desc())
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        return [
            ConnectorGrantResponse(
                **{
                    field: getattr(row, field)
                    for field in ConnectorGrantResponse.model_fields
                }
            )
            for row in rows
        ]

    @staticmethod
    async def revoke_grant(
        session: AsyncSession, auth: AuthenticatedUser, grant_id: int
    ) -> None:
        grant = (
            await session.execute(
                select(ConnectorGrant)
                .where(
                    ConnectorGrant.id == grant_id,
                    ConnectorGrant.staff_user_id == auth.staff_user_id,
                    ConnectorGrant.tenant_id == auth.tenant_id,
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if grant is None:
            raise ConnectorAuthError("access_denied", "Connection not found", 404)
        if grant.revoked_at is None:
            grant.revoked_at = now_utc()
            ConnectorAuthService._event(session, grant, "manager_revoked")
            await session.commit()

    @staticmethod
    async def revoke_token(
        session: AsyncSession, *, token: str, client_id: str
    ) -> None:
        if client_id != CLIENT_ID:
            raise ConnectorAuthError("invalid_client", "Unknown OAuth client", 401)
        row = (
            await session.execute(
                select(ConnectorToken).where(ConnectorToken.token_hash == digest(token))
            )
        ).scalar_one_or_none()
        if row is None:
            return
        grant = (
            await session.execute(
                select(ConnectorGrant)
                .where(ConnectorGrant.id == row.grant_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if grant and grant.client_id == client_id and grant.revoked_at is None:
            grant.revoked_at = now_utc()
            ConnectorAuthService._event(session, grant, "oauth_revoked")
            await session.commit()
