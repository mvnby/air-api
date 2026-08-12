import asyncio
import base64

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import (
    Installer,
    Order,
    OrderAttachmentLink,
    OrderStatus,
    OrderWorkStage,
    ServiceAttachment,
    StaffUser,
    Storefront,
    Tenant,
    TenantMembership,
)
from services.bot_task_mutation_service import (
    BotTaskMutationAccessDeniedError,
    BotTaskMutationService,
)
from services.private_attachment_storage_service import StoredPrivateObject
from services.tenant_scope_service import SystemTenantScopeResolver


PNG_CONTENT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _FakePrivateStorage:
    provider_name = "test_private"
    inventory_id = "test_private"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def save(self, **kwargs) -> StoredPrivateObject:
        key = f"private/{kwargs['content_hash']}/{kwargs['variant']}.{kwargs['extension']}"
        self.objects.setdefault(key, kwargs["content"])
        return StoredPrivateObject(
            provider=self.provider_name,
            storage_key=key,
            content_hash=kwargs["content_hash"],
            size_bytes=len(kwargs["content"]),
        )

    async def exists(self, storage_key: str) -> bool:
        return storage_key in self.objects


@pytest.mark.asyncio
async def test_stage_attachment_is_authorized_tenant_scoped_and_race_idempotent(
    db_engine,
    monkeypatch,
):
    assert db_engine.dialect.name == "postgresql"
    storage = _FakePrivateStorage()
    monkeypatch.setattr(
        "services.service_attachment_service.get_private_attachment_storage",
        lambda: storage,
    )
    session_factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as setup_session:
        tenant_scope = await SystemTenantScopeResolver.resolve(setup_session)
        assigned_installer = Installer(name="Assigned stage attachment installer")
        other_installer = Installer(name="Other stage attachment installer")
        setup_session.add_all([assigned_installer, other_installer])
        await setup_session.flush()
        staff = StaffUser(
            display_name="Stage attachment staff",
            status="active",
            roles=["installer"],
            telegram_id=987654322,
            legacy_installer_id=int(assigned_installer.id),
        )
        setup_session.add(staff)
        await setup_session.flush()
        setup_session.add(
            TenantMembership(
                tenant_id=tenant_scope.tenant_id,
                staff_user_id=int(staff.id),
                role="installer",
                status="active",
            )
        )
        order = Order(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            status=OrderStatus.EXECUTION,
            title="Stage attachment order",
        )
        setup_session.add(order)
        await setup_session.flush()
        assigned_stage = OrderWorkStage(
            order_id=int(order.id),
            name="Assigned stage",
            installer_id=int(assigned_installer.id),
        )
        other_stage = OrderWorkStage(
            order_id=int(order.id),
            name="Other stage",
            installer_id=int(other_installer.id),
        )
        setup_session.add_all([assigned_stage, other_stage])

        foreign_tenant = Tenant(
            id=2,
            slug="stage-attachment-foreign",
            display_name="Stage attachment foreign tenant",
            status="active",
        )
        setup_session.add(foreign_tenant)
        await setup_session.flush()
        foreign_storefront = Storefront(
            id=2,
            tenant_id=2,
            slug="main",
            display_name="Foreign main",
            status="active",
            is_default=True,
        )
        setup_session.add(foreign_storefront)
        await setup_session.flush()
        foreign_order = Order(
            tenant_id=2,
            storefront_id=2,
            status=OrderStatus.EXECUTION,
            title="Foreign tenant order",
        )
        setup_session.add(foreign_order)
        await setup_session.flush()
        foreign_stage = OrderWorkStage(
            order_id=int(foreign_order.id),
            name="Foreign tenant stage",
            installer_id=int(assigned_installer.id),
        )
        setup_session.add(foreign_stage)
        await setup_session.commit()

        assigned_stage_id = int(assigned_stage.id)
        other_stage_id = int(other_stage.id)
        foreign_stage_id = int(foreign_stage.id)
        order_id = int(order.id)

    barrier = asyncio.Barrier(8)

    async def attach_once():
        async with session_factory() as session:
            await barrier.wait()
            return await BotTaskMutationService.attach_stage_attachment(
                session,
                telegram_id=987654322,
                stage_id=assigned_stage_id,
                file_id="telegram-stage-photo",
                filename="report.png",
                mime_type="image/png",
                content=PNG_CONTENT,
                telegram_chat_id=-100,
                telegram_message_id=77,
                tenant_scope=tenant_scope,
            )

    results = await asyncio.gather(*(attach_once() for _ in range(8)))
    assert sum(not result.already_attached for result in results) == 1
    assert {result.order_id for result in results} == {order_id}

    async with session_factory() as verification_session:
        attachments = list(
            (await verification_session.execute(select(ServiceAttachment)))
            .scalars()
            .all()
        )
        links = list(
            (await verification_session.execute(select(OrderAttachmentLink)))
            .scalars()
            .all()
        )
        assert len(attachments) == 1
        assert len(links) == 1
        assert links[0].work_stage_id == assigned_stage_id
        assert links[0].order_id == order_id
        assert links[0].category == "service"
        assert attachments[0].source == "telegram_bot"
        assert attachments[0].telegram_file_id == "telegram-stage-photo"
        assert attachments[0].telegram_chat_id == -100
        assert attachments[0].telegram_message_id == 77
        assert attachments[0].telegram_user_id == 987654322
        assert attachments[0].source_meta == {
            "purpose": "task_stage_report",
            "stage_id": assigned_stage_id,
        }

    async with session_factory() as denied_session:
        with pytest.raises(BotTaskMutationAccessDeniedError):
            await BotTaskMutationService.attach_stage_attachment(
                denied_session,
                telegram_id=987654322,
                stage_id=other_stage_id,
                file_id="other-stage-photo",
                filename="other.png",
                mime_type="image/png",
                content=PNG_CONTENT,
                telegram_chat_id=None,
                telegram_message_id=None,
                tenant_scope=tenant_scope,
            )
        with pytest.raises(BotTaskMutationAccessDeniedError):
            await BotTaskMutationService.attach_stage_attachment(
                denied_session,
                telegram_id=987654322,
                stage_id=foreign_stage_id,
                file_id="foreign-stage-photo",
                filename="foreign.png",
                mime_type="image/png",
                content=PNG_CONTENT,
                telegram_chat_id=None,
                telegram_message_id=None,
                tenant_scope=tenant_scope,
            )
