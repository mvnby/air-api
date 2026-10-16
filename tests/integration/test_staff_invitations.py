"""Committed PostgreSQL fixtures prove invitation consumption and rollback."""
import asyncio
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select

from api_contracts.manager_invitations import StaffInvitationAcceptNew
from core.security import AuthenticatedUser
from models import StaffUser, Tenant, Storefront, TenantMembership
from models.staff_invitation import StaffInvitation
from services.staff_invitation_service import StaffInvitationService as Service, StaffInvitationError


async def seed(factory):
    async with factory() as session:
        session.add(Tenant(id=801, slug="invite-race", display_name="Invite Race"))
        session.add(StaffUser(id=801, display_name="Inviter", username="invite-race-owner", primary_role="owner", roles=["owner"]))
        await session.flush()
        session.add(Storefront(id=801, tenant_id=801, slug="main", display_name="Main", status="active", is_default=True))
        session.add(TenantMembership(tenant_id=801, staff_user_id=801, role="owner"))
        await session.commit()
        result = await Service.create(session, auth=AuthenticatedUser(
            username="invite-race-owner", auth_source="staff_password", staff_user_id=801,
            auth_version=1, role="owner", tenant_id=801, storefront_id=801,
        ), role="manager")
        return result["invite_url"].split("#token=")[1], result["id"]


def payload(token, username):
    return StaffInvitationAcceptNew(token=token, mode="new", username=username, password="new-password-123", display_name=username)


@pytest.mark.asyncio
async def test_two_connections_consume_invitation_once(db_engine):
    # No outer db-fixture transaction: independent connections need committed seeds.
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    raw, invitation_id = await seed(factory)
    async def accept(username):
        async with factory() as session:
            try:
                return await Service.accept(session, payload=payload(raw, username))
            except Exception:
                await session.rollback()
                raise
    outcomes = await asyncio.wait_for(asyncio.gather(accept("invite-first"), accept("invite-second"), return_exceptions=True), timeout=15)
    assert sum(isinstance(item, tuple) for item in outcomes) == 1
    assert sum(isinstance(item, StaffInvitationError) for item in outcomes) == 1
    async with factory() as session:
        row = await session.get(StaffInvitation, invitation_id)
        assert row.accepted_at is not None
        members = list((await session.execute(select(TenantMembership).where(TenantMembership.tenant_id == 801))).scalars())
        assert len(members) == 2 and all(not member.permissions for member in members)


@pytest.mark.asyncio
async def test_failed_accept_has_no_partial_account_or_membership(db_engine, monkeypatch):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    raw, invitation_id = await seed(factory)
    def fail(*args, **kwargs):
        raise RuntimeError("injected audit failure")
    monkeypatch.setattr(Service, "_audit", fail)
    async with factory() as writer:
        with pytest.raises(RuntimeError, match="audit"):
            await asyncio.wait_for(Service.accept(writer, payload=payload(raw, "invite-rollback")), timeout=15)
        await writer.rollback()
    async with factory() as reader:
        row = await reader.get(StaffInvitation, invitation_id)
        assert row.accepted_at is None and row.accepted_by_staff_user_id is None
        assert await reader.scalar(select(StaffUser.id).where(StaffUser.username == "invite-rollback")) is None
