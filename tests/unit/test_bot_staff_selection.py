"""SQLite proves selection policy/HTTP; PostgreSQL separately proves concurrent locks."""

from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel
from models import (
    StaffUser,
    Tenant,
    Storefront,
    TenantMembership,
    LegacyOwnerAuthState,
    BotFsmState,
    Installer,
)
from services.bot_access_service import BotAccessService
from services.bot_staff_selection_service import BotStaffSelectionService as Selection
from core.config import settings


@pytest.fixture
async def selected_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bot.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(Installer(id=1, name="Canonical executor"))
        await session.flush()
        session.add_all(
            [
                Tenant(id=11, slug="mvn", display_name="MVN", is_system=True),
                Tenant(id=12, slug="partner", display_name="Partner"),
                Storefront(
                    id=21,
                    tenant_id=11,
                    slug="main",
                    display_name="Main",
                    status="active",
                    is_default=True,
                ),
                Storefront(
                    id=22,
                    tenant_id=11,
                    slug="second",
                    display_name="Second",
                    status="active",
                ),
                Storefront(
                    id=23,
                    tenant_id=12,
                    slug="partner",
                    display_name="Partner",
                    status="active",
                    is_default=True,
                ),
                LegacyOwnerAuthState(),
                StaffUser(
                    id=31,
                    display_name="Same person",
                    username="selection-person",
                    telegram_id=101,
                    roles=["owner", "installer"],
                    primary_role="owner",
                    legacy_installer_id=1,
                ),
                TenantMembership(tenant_id=11, staff_user_id=31, role="manager"),
                TenantMembership(tenant_id=12, staff_user_id=31, role="catalog_editor"),
            ]
        )
        await session.commit()
        yield session, engine
    await engine.dispose()


async def test_selected_membership_alone_grants_roles_and_canonical_bridge(selected_db):
    session, _ = selected_db
    initial = await BotAccessService.get_context(session, 101)
    assert initial.is_manager and initial.legacy_installer_id == 1
    assert initial.selection.can_switch_context
    await Selection.select(
        session,
        initial.selection,
        tenant_id=12,
        storefront_slug="partner",
        expected_version=0,
    )
    partner = await BotAccessService.get_context(session, 101)
    assert partner.primary_role == "catalog_editor"
    assert partner.roles == ["catalog_editor"]
    assert (
        not partner.is_manager
        and not partner.is_executor
        and partner.legacy_installer_id is None
    )
    assert partner.selection.context_version == 1


async def test_stale_invalid_selection_never_falls_back_and_can_be_reselected(
    selected_db,
):
    session, _ = selected_db
    initial = await BotAccessService.get_context(session, 101)
    await Selection.select(
        session,
        initial.selection,
        tenant_id=11,
        storefront_slug="second",
        expected_version=0,
    )
    site = await session.get(Storefront, 22)
    site.status = "disabled"
    session.add(site)
    await session.commit()
    assert not (await BotAccessService.get_context(session, 101)).is_staff
    choices_context = await BotAccessService.get_context(
        session, 101, ignore_selection=True
    )
    await Selection.select(
        session,
        choices_context.selection,
        tenant_id=11,
        storefront_slug="main",
        expected_version=1,
    )
    restored = await BotAccessService.get_context(session, 101)
    assert restored.selection.context_version == 2
    with pytest.raises(HTTPException) as error:
        await Selection.bind_request(session, restored.selection, None, mutation=True)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        await Selection.select(
            session,
            restored.selection,
            tenant_id=12,
            storefront_slug="partner",
            expected_version=1,
        )


async def test_commit_after_long_provider_rejects_intervening_switch(selected_db):
    session, engine = selected_db
    issued = (await BotAccessService.get_context(session, 101)).selection
    await Selection.bind_request(session, issued, 0, mutation=True)
    await session.commit()  # Processing audit, then slow provider releases transaction.
    async with AsyncSession(engine, expire_on_commit=False) as other:
        current = (await BotAccessService.get_context(other, 101)).selection
        await Selection.select(
            other, current, tenant_id=11, storefront_slug="second", expected_version=0
        )
    session.add(
        BotFsmState(
            storage_key="late-provider",
            bot_id=1,
            chat_id=101,
            user_id=101,
            data={"sensitive": "old scope"},
        )
    )
    with pytest.raises(HTTPException) as error:
        await session.commit()
    assert error.value.status_code == 409
    await session.rollback()
    assert await session.get(BotFsmState, "late-provider") is None


async def test_commit_rechecks_role_and_telegram_mapping(selected_db):
    session, engine = selected_db
    issued = (await BotAccessService.get_context(session, 101)).selection
    await Selection.bind_request(session, issued, 0, mutation=True)
    await session.commit()
    async with AsyncSession(engine, expire_on_commit=False) as other:
        user = await other.get(StaffUser, 31)
        user.telegram_id = 202
        user.auth_version += 1
        other.add(user)
        await other.commit()
    session.add(
        BotFsmState(storage_key="late-unlinked", bot_id=1, chat_id=101, user_id=101)
    )
    with pytest.raises(HTTPException) as error:
        await session.commit()
    assert error.value.status_code == 403
    await session.rollback()
    assert await session.get(BotFsmState, "late-unlinked") is None


async def test_unknown_admin_settings_cannot_grant_business_owner(
    selected_db, monkeypatch
):
    session, _ = selected_db
    monkeypatch.setattr(type(settings), "is_admin_user", lambda self, value: True)
    unknown = await BotAccessService.get_context(session, 999)
    assert (
        not unknown.is_staff
        and not unknown.is_manager
        and not unknown.is_platform_owner
    )
    from services.bot_api_access import (
        require_bot_manager,
        require_bot_catalog_editor,
        BotUseCaseAccessDeniedError,
    )

    with pytest.raises(BotUseCaseAccessDeniedError):
        await require_bot_manager(session, 999)
    with pytest.raises(BotUseCaseAccessDeniedError):
        await require_bot_catalog_editor(session, 999)


async def test_http_choices_selection_and_missing_version_after_switch(selected_db):
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from core.database import get_session
    from core.bot_api_security import require_bot_api_token
    from routers.internal_bot_context import router
    from routers.internal_bot import router as business_router

    session, _ = selected_db
    app = FastAPI()
    app.include_router(router)
    app.include_router(business_router)

    async def db():
        yield session

    app.dependency_overrides[get_session] = db
    app.dependency_overrides[require_bot_api_token] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        choices = await client.get(
            "/api/internal/bot/v1/staff/context/101/choices?limit=1"
        )
        assert choices.status_code == 200
        assert (
            choices.json()["total"] == 3
            and len(choices.json()["choices"][0]["storefronts"]) == 1
        )
        response = await client.post(
            "/api/internal/bot/v1/staff/context/select",
            json=dict(
                telegram_id=101,
                tenant_id=12,
                storefront_slug="partner",
                expected_context_version=0,
            ),
        )
        assert response.status_code == 200, response.text
        assert response.json()["roles"] == ["catalog_editor"]
        assert response.json()["context_version"] == 1
        assert response.json()["legacy_installer_id"] is None
        stale = await client.post(
            "/api/internal/bot/v1/tasks/my", json={"telegram_id": 101}
        )
        assert stale.status_code == 403, stale.text
        denied = await client.post(
            "/api/internal/bot/v1/tasks/my",
            json={"telegram_id": 101, "expected_context_version": 1},
        )
        assert denied.status_code == 403, denied.text


async def test_partner_empty_catalog_never_reads_global_catalog(
    selected_db, monkeypatch
):
    from services.bot_catalog_service import BotCatalogService
    from services.product_service import ProductService

    session, _ = selected_db
    issued = (await BotAccessService.get_context(session, 101)).selection
    await Selection.select(
        session, issued, tenant_id=12, storefront_slug="partner", expected_version=0
    )
    global_read = AsyncMock(
        side_effect=AssertionError("Partner must not read global catalog")
    )
    monkeypatch.setattr(ProductService, "search_products", global_read)
    assert (
        await BotCatalogService.search_for_staff(
            session, telegram_id=101, query="Midea", limit=5
        )
        == []
    )
    global_read.assert_not_awaited()


async def test_notification_acl_uses_event_membership_not_selected_company(selected_db):
    from models import Order, OrderWorkStage
    from services.communications.staff_task_contracts import (
        StaffTaskNotificationPayloadV1,
    )
    from services.bot_notification_access import task_notification_allowed

    session, _ = selected_db
    session.add_all(
        [
            Order(id=71, tenant_id=11, storefront_id=21),
            Order(id=72, tenant_id=12, storefront_id=23),
            OrderWorkStage(id=81, order_id=71, name="Main task", installer_id=1),
            OrderWorkStage(id=82, order_id=72, name="Partner task", installer_id=1),
        ]
    )
    await session.commit()
    from models import TenantWorkerProfile, OrderWorkAssignment
    from services.installer_work_urls import installer_work_url
    session.add(TenantWorkerProfile(id=31, tenant_id=11, staff_user_id=31))
    await session.flush()
    session.add(OrderWorkAssignment(id=71, tenant_id=11, storefront_id=21, order_id=71,
        work_stage_id=81, worker_profile_id=31, title="Work"))
    await session.commit()
    issued = (await BotAccessService.get_context(session, 101)).selection
    await Selection.select(
        session, issued, tenant_id=12, storefront_slug="partner", expected_version=0
    )
    user = await session.get(StaffUser, 31)

    def payload(order_id, stage_id, tenant_id, site):
        return StaffTaskNotificationPayloadV1(
            event_kind="assigned",
            staff_user_id=31,
            assignment_id=71,
            stage_id=stage_id,
            order_id=order_id,
            tenant_id=tenant_id,
            storefront_id=site,
            stage_name="Work",
            status="planned",
            manager_url=installer_work_url(71, tenant_id=tenant_id, storefront_slug="main"),
        )

    assert await task_notification_allowed(session, user, payload(71, 81, 11, 21))
    assert not await task_notification_allowed(
        session, user, payload(72, 82, 12, 23)
    )  # Selected catalog editor.
    assert not await task_notification_allowed(
        session, user, payload(71, 81, 11, 22)
    )  # Wrong site.


async def test_legacy_management_events_never_route_partner_data_to_global_owner(
    selected_db, monkeypatch
):
    from models import Order
    from services.communications.audience_resolver import CommunicationAudienceResolver
    from services.communications.contracts import CommunicationTemplatePlanV1
    from services.communications.recipient_directory import ManagementRecipientDirectory
    from services.staff_user_service import StaffUserService

    session, _ = selected_db
    # Global owner role in company A must not override editor membership in B.
    session.add(
        StaffUser(
            id=32,
            display_name="Other company owner",
            primary_role="owner",
            roles=["owner"],
            telegram_id=202,
        )
    )
    session.add(TenantMembership(tenant_id=12, staff_user_id=32, role="owner"))
    session.add_all(
        [
            Order(id=91, tenant_id=11, storefront_id=21),
            Order(id=92, tenant_id=12, storefront_id=23),
        ]
    )
    await session.commit()
    monkeypatch.setattr(settings, "ADMIN_IDS", "999", raising=False)
    canonical = await ManagementRecipientDirectory.list_telegram(session)
    assert [r.destination for r in canonical] == ["101"]

    def plan(order_id):
        return CommunicationTemplatePlanV1(
            audience="management",
            template_key="telegram.website_order_created",
            render_context={"order_id": order_id},
        )

    own = await CommunicationAudienceResolver.list_telegram(session, plan=plan(91))
    assert [r.destination for r in own] == ["101"]
    assert (
        await CommunicationAudienceResolver.list_telegram(session, plan=plan(92)) == []
    )
    # Direct business notification helper similarly uses only the event company.
    from models.tenancy import TenantScope

    assert await StaffUserService.get_active_owner_admin_telegram_recipient_ids(
        session, tenant_scope=TenantScope(tenant_id=12, storefront_id=23)
    ) == [202]


async def test_core_dml_and_first_flush_are_fenced_before_persistence(selected_db):
    from sqlalchemy import insert

    session, engine = selected_db
    issued = (await BotAccessService.get_context(session, 101)).selection
    await Selection.bind_request(session, issued, 0, mutation=True)
    await session.commit()
    async with AsyncSession(engine, expire_on_commit=False) as other:
        user = await other.get(StaffUser, 31)
        user.auth_version += 1
        other.add(user)
        await other.commit()
    with pytest.raises(HTTPException) as error:
        await session.execute(
            insert(BotFsmState).values(
                storage_key="late-core", bot_id=1, chat_id=101, user_id=101, data={}
            )
        )
    assert error.value.status_code == 403
    await session.rollback()
    session.add(
        BotFsmState(storage_key="late-flush", bot_id=1, chat_id=101, user_id=101)
    )
    with pytest.raises(HTTPException) as error:
        await session.flush()
    assert error.value.status_code == 403
    await session.rollback()
    assert await session.get(BotFsmState, "late-core") is None
    assert await session.get(BotFsmState, "late-flush") is None


async def test_http_invalid_company_recovers_through_control_plane_without_business_fallback(
    selected_db,
):
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from core.database import get_session
    from core.bot_api_security import require_bot_api_token
    from routers.internal_bot_context import router
    from routers.internal_bot import router as business_router
    from routers.internal_bot_runtime import router as runtime_router

    session, _ = selected_db
    initial = (await BotAccessService.get_context(session, 101)).selection
    await Selection.select(
        session, initial, tenant_id=12, storefront_slug="partner", expected_version=0
    )
    tenant = await session.get(Tenant, 12)
    tenant.status = "disabled"
    session.add(tenant)
    await session.commit()
    app = FastAPI()
    app.include_router(router)
    app.include_router(business_router)
    app.include_router(runtime_router)

    async def db():
        yield session

    app.dependency_overrides[get_session] = db
    app.dependency_overrides[require_bot_api_token] = lambda: None
    prefix = "/api/internal/bot/v1"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        context = await client.get(prefix + "/staff/context/101")
        assert context.status_code == 200
        assert not context.json()["is_staff"] and context.json()["context_version"] == 1
        assert (
            context.json()["tenant_id"] is None
            and context.json()["storefront_id"] is None
        )
        choices = await client.get(prefix + "/staff/context/101/choices")
        assert choices.status_code == 200 and {
            c["tenant_id"] for c in choices.json()["choices"]
        } == {11}
        denied = await client.post(
            prefix + "/quick-orders/parse",
            json={"telegram_id": 101, "text": "Work", "expected_context_version": 1},
        )
        assert denied.status_code == 403
        callback = dict(
            storage_key="ctxcb:recovery",
            telegram_id=101,
            expected_context_version=1,
            bot_id=1,
            chat_id=101,
            user_id=101,
            destiny="context_callbacks",
            write_data=True,
            data={
                "telegram_id": 101,
                "tenant_id": 0,
                "site": "",
                "version": 1,
                "callbacks": ["company_pick:11:main"],
            },
        )
        saved = await client.post(prefix + "/fsm/update", json=callback)
        assert saved.status_code == 200, saved.text
        read = await client.post(
            prefix + "/fsm/get",
            json={
                "storage_key": "ctxcb:recovery",
                "telegram_id": 101,
                "expected_context_version": 1,
            },
        )
        assert read.status_code == 200 and read.json()["data"]["version"] == 1
        selected = await client.post(
            prefix + "/staff/context/select",
            json=dict(
                telegram_id=101,
                tenant_id=11,
                storefront_slug="main",
                expected_context_version=1,
            ),
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["is_manager"] and selected.json()["context_version"] == 2
        tasks = await client.post(
            prefix + "/tasks/my",
            json={"telegram_id": 101, "expected_context_version": 2},
        )
        assert tasks.status_code == 200, tasks.text
        stale = await client.post(
            prefix + "/tasks/my",
            json={"telegram_id": 101, "expected_context_version": 1},
        )
        assert stale.status_code == 409


async def test_explicit_bound_platform_owner_keeps_canonical_bot_access(
    selected_db, monkeypatch
):
    from datetime import datetime, timezone
    from services.bot_api_access import require_bot_manager, require_bot_catalog_editor

    session, _ = selected_db
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "root-bot-proof")
    owner = StaffUser(
        id=4,
        display_name="Platform owner",
        username="root-bot-proof",
        primary_role="owner",
        roles=["owner"],
        telegram_id=404,
        telegram_verified_at=datetime.now(timezone.utc),
    )
    session.add(owner)
    await session.flush()
    session.add(TenantMembership(tenant_id=11, staff_user_id=4, role="owner"))
    state = await session.get(LegacyOwnerAuthState, 1)
    state.mode = "staff"
    state.owner_staff_user_id = 4
    session.add(state)
    await session.commit()
    context = await require_bot_manager(session, 404)
    assert context.is_platform_owner and context.staff_user_id == 4
    assert context.selection.canonical and context.roles == ["owner"]
    assert (await require_bot_catalog_editor(session, 404)).is_platform_owner
    await Selection.bind_request(session, context.selection, 0, mutation=True)
    session.add(
        BotFsmState(storage_key="real-owner-action", bot_id=1, chat_id=404, user_id=404)
    )
    await session.commit()


async def test_partner_catalog_uses_only_selected_published_offer_and_price(
    selected_db,
):
    from models import Product, TenantOffer
    from services.bot_catalog_service import BotCatalogService

    session, _ = selected_db
    session.add_all(
        [
            Product(
                id=91,
                title="Midea visible",
                slug="visible",
                price=9999,
                is_published=True,
                specs={"area_m2": 25},
            ),
            Product(
                id=92,
                title="Midea hidden",
                slug="hidden",
                price=9998,
                is_published=False,
                specs={"area_m2": 25},
            ),
            Product(
                id=93,
                title="Midea unoffered",
                slug="unoffered",
                price=9997,
                is_published=True,
                specs={"area_m2": 25},
            ),
        ]
    )
    await session.flush()
    for product_id, site, price in [(91, 23, 1234), (92, 23, 4321), (93, 21, 6789)]:
        session.add(
            TenantOffer(
                tenant_id=12 if site == 23 else 11,
                storefront_id=site,
                product_id=product_id,
                price=price,
                is_published=True,
                created_by_username="test",
                updated_by_username="test",
            )
        )
    await session.commit()
    current = (await BotAccessService.get_context(session, 101)).selection
    await Selection.select(
        session, current, tenant_id=12, storefront_slug="partner", expected_version=0
    )
    result = await BotCatalogService.search_for_staff(
        session, telegram_id=101, query="Midea", limit=5
    )
    assert [(r["id"], r["price"]) for r in result] == [(91, 1234)]
    assert (
        await BotCatalogService.get_product_for_staff(
            session, telegram_id=101, product_id=93
        )
        is None
    )
