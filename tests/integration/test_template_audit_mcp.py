"""Real OAuth + MCP protocol + Manager read path on isolated synthetic records."""

import base64
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
import httpx
import pytest

from core.database import get_session
from core.security import AuthenticatedUser, require_owner_access
from modules.documents.api.template_audits import router as audit_router
from modules.documents.api.templates_runtime import router as templates_router
from models.connector_auth import ConnectorGrant, ConnectorToken
from sqlalchemy import select
from services.connector_auth_policy import digest
from services.connector_auth_policy import CLIENT_ID, pkce, resource
from services.connector_auth_service import ConnectorAuthService
from services.connector_mcp import ConnectorMCPApplication
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_template_audit_workflow import _seed, _save_input, _proposal


@pytest.mark.asyncio
async def test_oauth_mcp_private_source_report_proposal_and_manager_result(
    db_engine, tmp_path, monkeypatch
):
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        env = await _seed(db, tmp_path)
        local = LocalPrivateAttachmentStorage(tmp_path / "private")
        monkeypatch.setattr(
            "modules.documents.application.template_audit.get_private_attachment_storage",
            lambda: local,
        )
        monkeypatch.setattr(
            "modules.documents.application.template_audit_commands.get_private_attachment_storage",
            lambda: local,
        )
        auth = AuthenticatedUser(
            username=env.actor.username,
            auth_source="staff",
            staff_user_id=env.actor.staff_user_id,
            role="owner",
            tenant_id=1,
            storefront_id=1,
            tenant_membership_id=env.membership.id,
            is_system_tenant=True,
            auth_version=1,
        )

        async def token_for(scopes):
            verifier = "z" * 64
            redirect = "https://chatgpt.com/connector_platform_oauth_redirect"
            pending, nonce = await ConnectorAuthService.start_consent(
                db,
                auth,
                "synthetic-manager-session",
                client_id=CLIENT_ID,
                redirect_uri=redirect,
                requested_resource=resource(),
                scope=scopes,
                state="audit-state",
                code_challenge=pkce(verifier),
                code_challenge_method="S256",
                response_type="code",
            )
            callback = await ConnectorAuthService.finish_consent(
                db,
                auth,
                "synthetic-manager-session",
                consent_id=pending.id,
                nonce=nonce,
                allow=True,
            )
            return await ConnectorAuthService.exchange_code(
                db,
                code=parse_qs(urlsplit(callback).query)["code"][0],
                client_id=CLIENT_ID,
                redirect_uri=redirect,
                requested_resource=resource(),
                code_verifier=verifier,
            )

        old_token = await token_for("kitlane:read kitlane:contracts:drafts:write")
        template_token = await token_for(
            "kitlane:read kitlane:templates:read kitlane:templates:proposals:write"
        )

        @asynccontextmanager
        async def sessions():
            yield db

        adapter = ConnectorMCPApplication(session_factory=sessions)
        app = FastAPI()
        app.include_router(audit_router)
        app.include_router(templates_router)
        app.mount("/api/connector/mcp", adapter)

        async def override_session():
            yield db

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[require_owner_access] = lambda: auth
        async with adapter.lifespan():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app),
                base_url="https://api.mvn.by",
                follow_redirects=True,
                headers={
                    "Authorization": f"Bearer {template_token.access_token}",
                    "Accept": "application/json, text/event-stream",
                },
            ) as client:

                async def rpc(method, params, token=None):
                    response = await client.post(
                        "/api/connector/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": method,
                            "params": params,
                        },
                        headers={
                            "Authorization": f"Bearer {token or template_token.access_token}"
                        },
                    )
                    assert response.status_code == 200, response.text
                    return response.json()

                async def call(name, arguments, token=None):
                    return (
                        await rpc(
                            "tools/call", {"name": name, "arguments": arguments}, token
                        )
                    )["result"]

                await rpc(
                    "initialize",
                    {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "template-acceptance", "version": "1"},
                    },
                )
                tools = {
                    t["name"]: t
                    for t in (await rpc("tools/list", {}))["result"]["tools"]
                }
                assert tools["read_document_template"]["_meta"]["securitySchemes"][0][
                    "scopes"
                ] == ["kitlane:read", "kitlane:templates:read"]
                assert not any("activate_template" in name for name in tools)
                args = {
                    "legal_entity_id": env.issuer.id,
                    "template_id": env.template.id,
                    "version_id": env.version.id,
                }
                denied = await call(
                    "read_document_template", args, old_token.access_token
                )
                assert (
                    denied["isError"]
                    and denied["structuredContent"]["error"]["code"]
                    == "insufficient_scope"
                )
                listing = await call(
                    "list_document_templates",
                    {"legal_entity_id": env.issuer.id, "limit": 1},
                )
                assert listing["structuredContent"]["items"][0]["id"] == env.template.id
                source = await call(
                    "read_document_template", {**args, "include_source_file": True}
                )
                assert not source["isError"], source
                embedded = next(
                    c["resource"] for c in source["content"] if c["type"] == "resource"
                )
                assert base64.b64decode(embedded["blob"]) == env.source
                assert source["structuredContent"]["content_kind"] == "template_source"
                resource_read = await rpc(
                    "resources/read",
                    {"uri": source["structuredContent"]["source_resource_uri"]},
                )
                assert (
                    base64.b64decode(resource_read["result"]["contents"][0]["blob"])
                    == env.source
                )
                forbidden_resource = await rpc(
                    "resources/read",
                    {"uri": source["structuredContent"]["source_resource_uri"]},
                    old_token.access_token,
                )
                assert "error" in forbidden_resource
                payload = await _save_input(env)
                saved = await call(
                    "save_template_audit_report", payload.model_dump(mode="json")
                )
                assert not saved["isError"], saved
                report = saved["structuredContent"]["result"]
                from api_contracts.document_template_audits import (
                    TemplateAuditReportResult,
                )

                proposal = _proposal(TemplateAuditReportResult.model_validate(report))
                proposed = await call(
                    "prepare_template_revision", proposal.model_dump(mode="json")
                )
                assert not proposed["isError"], proposed
                assert (
                    proposed["structuredContent"]["result"]["proposals"][0]["status"]
                    == "draft"
                )
                replayed = await call(
                    "prepare_template_revision", proposal.model_dump(mode="json")
                )
                assert replayed["structuredContent"]["replayed"]
                reread = await call(
                    "get_template_audit_report", {"report_id": report["id"]}
                )
                assert reread["structuredContent"]["id"] == report["id"]
                manager = await client.get(
                    f"/api/manager/document-system/template-audits/{report['id']}"
                )
                assert (
                    manager.status_code == 200
                    and manager.json()["proposals"][0]["status"] == "draft"
                )
                assert f"auditReportId={report['id']}" in manager.json()["manager_url"]
                candidate = manager.json()["proposals"][0]
                context = await client.get(
                    f"/api/manager/document-system/template-audits/{report['id']}/proposals/{candidate['id']}/preview-context"
                )
                assert context.status_code == 200, context.text
                preview = await client.post(
                    f"/api/manager/document-system/template-audits/{report['id']}/proposals/{candidate['id']}/preview",
                    json={
                        **{
                            key: value
                            for key, value in context.json().items()
                            if not key.endswith("_labels")
                        },
                        "format": "docx",
                    },
                )
                assert preview.status_code == 200 and preview.content[:2] == b"PK"
                assert preview.headers["cache-control"] == "private, no-store"
                # A new stateless conversation knows the template, not report IDs.
                current_report = manager.json()
                finding = current_report["findings"][0]
                decision = await client.patch(
                    f"/api/manager/document-system/template-audits/{report['id']}/findings/{finding['id']}",
                    json={
                        "expected_revision": current_report["revision"],
                        "source_hash": current_report["source_hash"],
                        "context_hash": current_report["context_hash"],
                        "legal_sources_hash": current_report["legal_sources_hash"],
                        "status": "rejected",
                        "reason": "Keep the deliberate synthetic wording",
                    },
                )
                assert decision.status_code == 200, decision.text
                await rpc(
                    "initialize",
                    {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "new-chat", "version": "1"},
                    },
                )
                rediscovered = await call("read_document_template", args)
                summaries = rediscovered["structuredContent"]["audit_reports"]
                assert (
                    summaries[0]["id"] == report["id"]
                    and "findings" not in summaries[0]
                )
                resumed = (
                    await call(
                        "get_template_audit_report", {"report_id": summaries[0]["id"]}
                    )
                )["structuredContent"]
                assert resumed["findings"][0]["status"] == "rejected"
                rerun_payload = payload.model_dump(mode="json")
                rerun_payload.update(
                    idempotency_key="template-audit-new-chat-rerun-001",
                    expected_revision=resumed["revision"],
                )
                rerun_payload["findings"][0]["risk"] = (
                    "Refined risk explanation in the new conversation"
                )
                rerun = await call("save_template_audit_report", rerun_payload)
                assert not rerun["isError"], rerun
                rerun_report = rerun["structuredContent"]["result"]
                assert (
                    rerun_report["id"] == report["id"]
                    and len(rerun_report["findings"]) == 1
                )
                assert rerun_report["findings"][0]["status"] == "rejected"
                assert rerun_report["findings"][0]["decision_current"] is True
                changed_wording = {
                    **rerun_payload,
                    "idempotency_key": "template-audit-new-wording-001",
                    "expected_revision": rerun_report["revision"],
                }
                changed_wording["findings"] = [
                    dict(rerun_payload["findings"][0], proposed_text="20 рабочих дней")
                ]
                changed_result = await call(
                    "save_template_audit_report", changed_wording
                )
                assert not changed_result["isError"], changed_result
                changed_finding = changed_result["structuredContent"]["result"][
                    "findings"
                ][0]
                assert (
                    changed_finding["status"] == "rejected"
                    and changed_finding["decision_current"] is False
                )
                assert (
                    changed_finding["decision_history"][-1]["proposed_text"]
                    == "15 рабочих дней"
                )
                env.issuer.legal_name = "Changed synthetic legal profile"
                await db.commit()
                history = await call("read_document_template", args)
                assert history["structuredContent"]["audit_reports"][0]["stale"] is True
                access_row = (
                    await db.execute(
                        select(ConnectorToken).where(
                            ConnectorToken.token_hash
                            == digest(template_token.access_token)
                        )
                    )
                ).scalar_one()
                grant = await db.get(ConnectorGrant, access_row.grant_id)
                grant.revoked_at = datetime.now(timezone.utc)
                await db.commit()
                revoked_source = await client.post(
                    "/api/connector/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "resources/read",
                        "params": {
                            "uri": source["structuredContent"]["source_resource_uri"]
                        },
                    },
                )
                assert revoked_source.status_code == 401
                assert "blob" not in revoked_source.text
                env.membership.role = "manager"
                await db.commit()
                revoked = await client.post(
                    "/api/connector/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "read_document_template", "arguments": args},
                    },
                )
                assert revoked.status_code == 401
