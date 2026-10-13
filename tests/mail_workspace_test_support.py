"""Shared acceptance setup; SMTP is always substituted, SQLite is only local logic proof."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel
from core.command_actor import CommandActor
from core.config import settings
from models import StaffUser, TenantMembership, Tenant, Storefront
from models.tenancy import TenantScope
from schemas_mail import MailDraftCreatePayload, MailConfirmPayload
from services.mail_workspace_service import MailWorkspaceService as Mail
from services.mail_smtp_service import MailSmtpService

@pytest.fixture(autouse=True)
def smtp_settings(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_FROM_EMAIL", "sales@example.test")
    monkeypatch.setattr(settings, "MAIL_FROM_NAME", "Kitlane Company")
    monkeypatch.setattr(settings, "MAIL_SMTP_USERNAME", "sales@example.test")
    monkeypatch.setattr(settings, "MAIL_SMTP_PASSWORD", "fake-test-password")
    monkeypatch.setattr(MailSmtpService, "send_message", staticmethod(lambda _: pytest.fail("Unexpected real or unmocked send")))

async def _actor(db, username="mail-owner", *, tenant_id=1, storefront_id=1, is_system=True):
    user = StaffUser(display_name="Mail manager", username=username, roles=["manager"], primary_role="manager")
    db.add(user)
    await db.flush()
    db.add(TenantMembership(tenant_id=tenant_id, staff_user_id=user.id, role="manager"))
    await db.commit()
    return CommandActor(user.id, username, TenantScope(tenant_id, storefront_id, is_system=is_system))

async def _ready(session, actor, key="ready", attachment=True):
    created = await Mail.create_draft(session, actor=actor, payload=MailDraftCreatePayload(
        to=["supplier@example.test"], subject="ebm-papst A2E200-AI38-01",
        body_text="Просим сообщить цену и срок поставки вентилятора ebm-papst A2E200-AI38-01.",
    ), idempotency_key=f"mail-create-{key}-001")
    message = created.value
    if attachment:
        message = (await Mail.upload_attachment(session, actor=actor, draft_id=message.id,
            expected_version=message.version, idempotency_key=f"mail-file-{key}-001",
            filename="fan.pdf", mime_type="application/pdf", content=b"%PDF-1.4 fixed attachment")).value
    confirmed = await Mail.confirm(session, actor=actor, draft_id=message.id,
        payload=MailConfirmPayload(expected_version=message.version, content_hash=message.content_hash),
        idempotency_key=f"mail-confirm-{key}-001")
    return confirmed.value

@pytest.fixture
async def mail_db_engine(tmp_path):
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "mail.db"}')
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all([Tenant(id=1, slug='mvn', display_name='MVN', is_system=True),
            Storefront(id=1, tenant_id=1, slug='main', display_name='MVN', status='active', is_default=True)])
        await session.commit()
    yield engine
    await engine.dispose()

@pytest.fixture
async def mail_db(mail_db_engine):
    async with AsyncSession(mail_db_engine, expire_on_commit=False) as session:
        yield session
