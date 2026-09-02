from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core.config import settings
from core.security import create_access_token
from models import OutgoingEmail, StaffUser, Storefront, Tenant, TenantMembership


BASE = "/api/manager/document-system"


async def _system_headers(client) -> dict[str, str]:
    response = await client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _partner_headers(db) -> tuple[dict[str, str], int, int]:
    tenant = Tenant(
        slug="native-email-partner",
        display_name="Партнёр Климат",
        status="active",
        is_system=False,
    )
    db.add(tenant)
    await db.flush()
    storefront = Storefront(
        tenant_id=int(tenant.id),
        slug="main",
        display_name="Партнёр Климат",
        status="active",
        is_default=True,
    )
    user = StaffUser(
        display_name="Partner Manager",
        status="active",
        roles=["manager"],
        primary_role="manager",
        username="native-email-partner-manager",
    )
    db.add_all([storefront, user])
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=int(tenant.id),
            staff_user_id=int(user.id),
            role="manager",
            status="active",
        )
    )
    await db.commit()
    token = create_access_token(
        {
            "sub": user.username,
            "staff_user_id": user.id,
            "auth_version": user.auth_version,
            "auth_source": "native-document-email-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    return (
        {"Authorization": f"Bearer {token}"},
        int(tenant.id),
        int(storefront.id),
    )


def _compose_response() -> dict:
    return {
        "template_key": "contract",
        "template_options": [],
        "subject": "Договор на поставку",
        "body_text": "Добрый день!\n\nДоговор во вложении.",
        "document_ids": [7],
        "document_labels": ["Договор Д-7"],
        "missing_requisites": [],
    }


@pytest.mark.asyncio
async def test_partner_manager_can_compose_only_in_resolved_tenant(
    async_client,
    db,
    monkeypatch,
):
    headers, tenant_id, storefront_id = await _partner_headers(db)

    async def fake_compose(_session, **kwargs):
        scope = kwargs.pop("tenant_scope")
        assert (scope.tenant_id, scope.storefront_id, scope.is_system) == (
            tenant_id,
            storefront_id,
            False,
        )
        assert kwargs == {
            "order_id": 42,
            "document_ids": [7],
            "template_key": "auto",
        }
        return _compose_response()

    monkeypatch.setattr(
        "modules.documents.api.managed_document_emails.OrderEmailTemplateService.compose",
        fake_compose,
    )
    response = await async_client.post(
        f"{BASE}/orders/42/email/compose",
        headers=headers,
        json={"document_ids": [7], "template_key": "auto"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["subject"] == "Договор на поставку"


@pytest.mark.asyncio
async def test_partner_manager_cannot_send_via_global_mvn_smtp(
    async_client,
    db,
    monkeypatch,
):
    headers, _, _ = await _partner_headers(db)
    called = False

    async def unexpected_send(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "modules.documents.api.managed_document_emails.MailSmtpService.send_order_email",
        unexpected_send,
    )
    response = await async_client.post(
        f"{BASE}/orders/42/email",
        headers=headers,
        json={
            "to_email": "client@example.com",
            "subject": "Договор",
            "body_text": "Документ во вложении.",
            "document_ids": [7],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == (
        "tenant_email_sender_not_configured"
    )
    assert called is False


@pytest.mark.asyncio
async def test_system_manager_can_send_from_native_workspace(
    async_client,
    monkeypatch,
):
    async def fake_send(_session, **kwargs):
        assert kwargs["tenant_scope"].is_system is True
        assert kwargs["order_id"] == 42
        assert kwargs["document_ids"] == [7]
        return OutgoingEmail(
            id=700,
            status="sent",
            order_id=42,
            customer_id=5,
            recipient_email=kwargs["to_email"],
            subject=kwargs["subject"],
            body_text=kwargs["body_text"],
            from_email="sales@mvn.by",
            sent_at=datetime(2026, 9, 2, 12, 0),
            created_at=datetime(2026, 9, 2, 12, 0),
        )

    monkeypatch.setattr(
        "modules.documents.api.managed_document_emails.MailSmtpService.send_order_email",
        fake_send,
    )
    response = await async_client.post(
        f"{BASE}/orders/42/email",
        headers=await _system_headers(async_client),
        json={
            "to_email": "client@example.com",
            "subject": "Договор",
            "body_text": "Документ во вложении.",
            "document_ids": [7],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == 700
    assert response.json()["status"] == "sent"
