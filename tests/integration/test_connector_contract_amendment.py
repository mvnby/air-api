"""Connected OAuth MCP protocol: discover/read a basis, save/read/retry its draft."""

from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlmodel import select
from starlette.applications import Starlette
from starlette.routing import Route
from core.security import AuthenticatedUser
from models import StaffUser, OrderDocument
from models.tenancy import TenantMembership
from services.connector_auth_policy import CLIENT_ID, pkce, resource
from services.connector_auth_service import ConnectorAuthService
from services.connector_mcp import ConnectorMCPApplication
from tests.integration.test_contract_amendments import setup, terms
from tests.integration.test_contract_amendments import amendment_db  # noqa: F401 - fixture


@pytest.mark.asyncio
async def test_connected_mcp_amendment_durable_replay_version_and_scope(
    amendment_db, tmp_path, monkeypatch
):
    db = amendment_db
    scope, order, _, storage, _, basis, _ = await setup(db, tmp_path)
    monkeypatch.setattr(
        "services.connector_contract_amendment._storage", lambda: storage
    )
    user = StaffUser(
        display_name="Тестовый владелец",
        username="amendment-owner",
        primary_role="admin",
        roles=["admin"],
    )
    db.add(user)
    await db.flush()
    membership = TenantMembership(
        tenant_id=scope.tenant_id, staff_user_id=user.id, role="admin"
    )
    db.add(membership)
    await db.commit()
    auth = AuthenticatedUser(
        username=user.username,
        auth_source="staff",
        staff_user_id=user.id,
        role="admin",
        tenant_id=scope.tenant_id,
        storefront_id=scope.storefront_id,
        tenant_membership_id=membership.id,
        is_system_tenant=True,
        auth_version=1,
    )
    verifier = "a" * 64
    redirect = "https://chatgpt.com/connector_platform_oauth_redirect"
    pending, nonce = await ConnectorAuthService.start_consent(
        db,
        auth,
        "manager-session",
        client_id=CLIENT_ID,
        redirect_uri=redirect,
        requested_resource=resource(),
        scope="kitlane:read kitlane:contracts:drafts:write",
        state="amendment-state",
        code_challenge=pkce(verifier),
        code_challenge_method="S256",
        response_type="code",
    )
    callback = await ConnectorAuthService.finish_consent(
        db, auth, "manager-session", consent_id=pending.id, nonce=nonce, allow=True
    )
    token = await ConnectorAuthService.exchange_code(
        db,
        code=parse_qs(urlsplit(callback).query)["code"][0],
        client_id=CLIENT_ID,
        redirect_uri=redirect,
        requested_resource=resource(),
        code_verifier=verifier,
    )

    @asynccontextmanager
    async def factory():
        yield db

    adapter = ConnectorMCPApplication(session_factory=factory)
    app = Starlette(
        routes=[Route("/api/connector/mcp", adapter, methods=["GET", "POST", "DELETE"])]
    )
    async with adapter.lifespan():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url="https://api.mvn.by",
            headers={
                "Authorization": f"Bearer {token.access_token}",
                "Accept": "application/json, text/event-stream",
            },
        ) as client:

            async def rpc(method, params):
                response = await client.post(
                    "/api/connector/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                        "params": params,
                    },
                )
                assert response.status_code == 200, response.text
                return response.json()["result"]

            async def call(name, args):
                return await rpc("tools/call", {"name": name, "arguments": args})

            await rpc(
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            )
            definitions = await rpc("tools/list", {})
            assert {
                "list_contract_amendment_bases",
                "prepare_contract_amendment",
                "get_contract_amendment",
            } <= {t["name"] for t in definitions["tools"]}
            bases = await call("list_contract_amendment_bases", {"order_id": order.id})
            assert not bases["isError"], bases
            candidate = bases["structuredContent"]["items"][0]
            assert (
                candidate["document_id"] == basis.id
                and candidate["original_amount"] == "4160.00"
            )
            assert candidate["lines"] and candidate["customer_name"]
            args = dict(
                order_id=order.id,
                base_document_id=basis.id,
                expected_basis_revision=candidate["revision"],
                issue_date="2026-11-10",
                amendment_terms=terms().model_dump(mode="json"),
                idempotency_key="amendment-native-draft-0001",
            )
            created = await call("prepare_contract_amendment", args)
            assert not created["isError"], created
            saved = created["structuredContent"]["result"]
            assert (saved["change_amount"], saved["new_total"], saved["status"]) == (
                "250.00",
                "4410.00",
                "draft",
            )
            assert f"documentId={saved['document_id']}" in saved["manager_url"]
            replay = await call("prepare_contract_amendment", args)
            assert replay["structuredContent"]["replayed"]
            assert (
                replay["structuredContent"]["result"]["document_id"]
                == saved["document_id"]
            )
            read = await call(
                "get_contract_amendment", {"document_id": saved["document_id"]}
            )
            assert (
                read["structuredContent"]["amendment_terms"] == saved["amendment_terms"]
            )
            changed = await call(
                "prepare_contract_amendment",
                {**args, "amendment_terms": terms("300").model_dump(mode="json")},
            )
            assert (
                changed["isError"]
                and changed["structuredContent"]["error"]["status"] == 409
            )
            stale = await call(
                "prepare_contract_amendment",
                {
                    **args,
                    "idempotency_key": "amendment-stale-draft-0002",
                    "expected_basis_revision": "0" * 64,
                },
            )
            assert (
                stale["isError"]
                and stale["structuredContent"]["error"]["status"] == 409
            )
            foreign = await call(
                "list_contract_amendment_bases", {"order_id": 99999999}
            )
            assert (
                foreign["isError"]
                and foreign["structuredContent"]["error"]["status"] == 404
            )

            async def unavailable(*args, **kwargs):
                raise FileNotFoundError("test-only unavailable source")

            monkeypatch.setattr(
                "services.connector_contract_amendment.check_saved_document_readiness",
                unavailable,
            )
            retry = await call("prepare_contract_amendment", args)
            assert not retry["isError"] and retry["structuredContent"]["replayed"]
            recovered = retry["structuredContent"]["result"]
            assert (
                recovered["document_id"] == saved["document_id"]
                and not recovered["readiness"]["can_issue"]
            )
            docs = list(
                (
                    await db.scalars(
                        select(OrderDocument).where(
                            OrderDocument.doc_type == "contract_amendment"
                        )
                    )
                ).all()
            )
            assert len(docs) == 1 and docs[0].base_document_id == basis.id
            assert (
                len(docs[0].render_snapshot["table_rows"]["lines"]) == 1
                and basis.status == "issued"
            )
