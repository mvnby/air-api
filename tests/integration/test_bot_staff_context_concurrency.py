"""Real independent PG transactions: no outer test transaction/savepoint evidence."""

import asyncio
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from models import (
    StaffUser,
    Tenant,
    Storefront,
    TenantMembership,
    LegacyOwnerAuthState,
    BotFsmState,
)
from services.bot_access_service import BotAccessService
from services.bot_staff_selection_service import BotStaffSelectionService as Selection
from sqlmodel import select


async def setup_actor(engine):
    async with AsyncSession(engine, expire_on_commit=False) as session:
        tenant = Tenant(
            slug="bot-concurrency-company", display_name="Concurrent company"
        )
        user = StaffUser(
            username="bot-context-concurrent",
            display_name="Concurrent staff",
            telegram_id=987654311,
            primary_role="manager",
            roles=["manager"],
        )
        session.add_all([tenant, user])
        await session.flush()
        session.add_all(
            [
                Storefront(
                    tenant_id=tenant.id,
                    slug="first",
                    display_name="First",
                    status="active",
                    is_default=True,
                ),
                Storefront(
                    tenant_id=tenant.id,
                    slug="second",
                    display_name="Second",
                    status="active",
                ),
                Storefront(
                    tenant_id=tenant.id,
                    slug="third",
                    display_name="Third",
                    status="active",
                ),
                TenantMembership(
                    tenant_id=tenant.id, staff_user_id=user.id, role="manager"
                ),
            ]
        )
        if (
            await session.execute(select(LegacyOwnerAuthState))
        ).scalars().first() is None:
            session.add(LegacyOwnerAuthState())
        await session.commit()
        current = (
            await BotAccessService.get_context(session, user.telegram_id)
        ).selection
        await Selection.ensure_row(session, current)
        await session.commit()
        return int(user.id), int(tenant.id)


async def test_concurrent_select_uses_expected_version_once(db_engine):
    assert db_engine.dialect.name == "postgresql"
    _, tenant_id = await setup_actor(db_engine)
    barrier = asyncio.Barrier(2)

    async def switch(site):
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            context = (await BotAccessService.get_context(session, 987654311)).selection
            await barrier.wait()
            try:
                await Selection.select(
                    session,
                    context,
                    tenant_id=tenant_id,
                    storefront_slug=site,
                    expected_version=0,
                )
                return 200
            except HTTPException as error:
                await session.rollback()
                return error.status_code

    assert sorted(
        await asyncio.wait_for(asyncio.gather(switch("second"), switch("third")), 15)
    ) == [200, 409]


@pytest.mark.parametrize("change", ["unlink", "auth_version", "switch"])
async def test_provider_gap_revalidates_identity_and_selection_before_commit(
    db_engine, change
):
    assert db_engine.dialect.name == "postgresql"
    staff_id, tenant_id = await setup_actor(db_engine)
    ready, changed = asyncio.Event(), asyncio.Event()

    async def pending_work():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            captured = (
                await BotAccessService.get_context(session, 987654311)
            ).selection
            await Selection.bind_request(session, captured, 0, mutation=True)
            await session.commit()
            ready.set()
            await changed.wait()  # External OCR/voice provider has no DB transaction.
            session.add(
                BotFsmState(
                    storage_key="late-scope-write",
                    bot_id=1,
                    chat_id=987654311,
                    user_id=987654311,
                )
            )
            with pytest.raises(HTTPException) as error:
                await session.commit()
            await session.rollback()
            assert error.value.status_code == (409 if change == "switch" else 403)

    async def mutate_identity():
        await ready.wait()
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            if change == "switch":
                context = (
                    await BotAccessService.get_context(session, 987654311)
                ).selection
                await Selection.select(
                    session,
                    context,
                    tenant_id=tenant_id,
                    storefront_slug="second",
                    expected_version=0,
                )
            else:
                user = await session.get(StaffUser, staff_id, with_for_update=True)
                if change == "unlink":
                    user.telegram_id = None
                user.auth_version += 1
                session.add(user)
                await session.commit()
        changed.set()

    await asyncio.wait_for(asyncio.gather(pending_work(), mutate_identity()), 15)
    async with AsyncSession(db_engine) as verify:
        assert await verify.get(BotFsmState, "late-scope-write") is None


async def test_first_flush_fence_prevents_state_tenant_fk_lock_inversion(db_engine):
    """Admin owns state before bot persistence: bot must wait before any child FK.

    With commit-only fencing the child flush takes Tenant KEY SHARE first; admin
    waits on Tenant while bot commit waits on state, producing a real PG deadlock.
    """
    from models import Customer

    assert db_engine.dialect.name == "postgresql"
    staff_id, tenant_id = await setup_actor(db_engine)
    state_locked, flushing, flushed, let_admin_lock = (
        asyncio.Event() for _ in range(4)
    )

    async def admin():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            await session.execute(select(LegacyOwnerAuthState).with_for_update())
            state_locked.set()
            await let_admin_lock.wait()
            await session.execute(
                select(Tenant).where(Tenant.id == tenant_id).with_for_update()
            )
            user = await session.get(StaffUser, staff_id, with_for_update=True)
            user.auth_version += 1
            session.add(user)
            await session.commit()

    async def business():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            captured = (
                await BotAccessService.get_context(session, 987654311)
            ).selection
            await Selection.bind_request(session, captured, 0, mutation=True)
            # No persistence/fence yet: allow the administrative transaction first.
            await session.rollback()
            await state_locked.wait()
            session.add(
                Customer(tenant_id=tenant_id, name="Late FK write", phone="1234567")
            )
            flushing.set()
            with pytest.raises(HTTPException) as error:
                await session.flush()
                flushed.set()  # Commit-only implementation can reach this too early.
                await let_admin_lock.wait()
                await session.commit()
            assert error.value.status_code == 403
            await session.rollback()

    async def coordinate():
        await flushing.wait()
        try:
            await asyncio.wait_for(flushed.wait(), 0.2)
        except TimeoutError:
            pass  # Correct guard waits on state before a child FK can be written.
        let_admin_lock.set()

    await asyncio.wait_for(asyncio.gather(admin(), business(), coordinate()), 15)
    async with AsyncSession(db_engine) as verify:
        assert (
            await verify.execute(
                select(Customer).where(Customer.name == "Late FK write")
            )
        ).scalars().first() is None
