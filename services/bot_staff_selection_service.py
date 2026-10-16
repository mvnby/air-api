"""Real membership selections, with no implicit operator or executor grants."""

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import StaffUser
from models.bot_staff_selection import BotStaffSelection
from models.tenancy import Storefront, Tenant, TenantMembership, TenantScope


@dataclass(frozen=True)
class BotSelection:
    staff_user_id: int
    tenant_id: int
    storefront_id: int
    tenant_slug: str
    tenant_name: str
    storefront_slug: str
    storefront_name: str
    role: str
    permissions: tuple[str, ...]
    context_version: int
    can_switch_context: bool
    is_system: bool
    demo_read_only: bool
    telegram_id: int
    auth_version: int

    @property
    def canonical(self) -> bool:
        return (
            self.is_system
            and self.tenant_slug == "mvn"
            and self.storefront_slug == "main"
        )

    @property
    def scope(self) -> TenantScope:
        return TenantScope(
            tenant_id=self.tenant_id,
            storefront_id=self.storefront_id,
            is_system=self.is_system,
            is_canonical_storefront=self.canonical,
            demo_read_only=self.demo_read_only,
        )


def context_changed() -> HTTPException:
    return HTTPException(
        409,
        detail={
            "code": "bot_context_changed",
            "message": "Компания или витрина изменилась. Откройте меню заново.",
        },
    )


class BotStaffSelectionService:
    @staticmethod
    async def rows(session: AsyncSession, staff_user_id: int):
        return list(
            (
                await session.execute(
                    select(TenantMembership, Tenant, Storefront)
                    .join(Tenant, Tenant.id == TenantMembership.tenant_id)
                    .join(Storefront, Storefront.tenant_id == Tenant.id)
                    .where(
                        TenantMembership.staff_user_id == staff_user_id,
                        TenantMembership.status == "active",
                        Tenant.status == "active",
                        Storefront.status == "active",
                    )
                    .order_by(Tenant.id, Storefront.is_default.desc(), Storefront.id)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )

    @classmethod
    async def resolve(
        cls,
        session: AsyncSession,
        staff_user_id: int,
        *,
        ignore_selection: bool = False,
    ) -> BotSelection | None:
        rows = await cls.rows(session, staff_user_id)
        if not rows:
            return None
        stored = (
            (
                await session.execute(
                    select(BotStaffSelection)
                    .where(BotStaffSelection.staff_user_id == staff_user_id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .first()
        )
        if stored is not None and not ignore_selection:
            row = next(
                (
                    r
                    for r in rows
                    if r.Tenant.id == stored.tenant_id
                    and r.Storefront.id == stored.storefront_id
                ),
                None,
            )
            if row is None:
                return None  # Explicit invalid selections never fall back.
        else:
            row = next(
                (
                    r
                    for r in rows
                    if r.Tenant.is_system
                    and r.Tenant.slug == "mvn"
                    and r.Storefront.slug == "main"
                ),
                rows[0],
            )
        membership, tenant, site = row
        user = (
            (
                await session.execute(
                    select(StaffUser)
                    .where(StaffUser.id == staff_user_id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .one()
        )
        return BotSelection(
            staff_user_id,
            int(tenant.id),
            int(site.id),
            tenant.slug,
            tenant.display_name,
            site.slug,
            site.display_name,
            membership.role,
            tuple(membership.permissions or ()),
            stored.context_version if stored else 0,
            len(rows) > 1,
            tenant.is_system,
            tenant.demo_read_only,
            int(user.telegram_id or 0),
            user.auth_version,
        )

    @classmethod
    async def ensure_row(cls, session: AsyncSession, selection: BotSelection) -> None:
        await session.run_sync(
            lambda sync: cls.verify_sync(
                sync, selection, mutation=False, allow_missing_selection=True
            )
        )
        dialect = session.get_bind().dialect.name
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        await session.execute(
            insert(BotStaffSelection)
            .values(
                staff_user_id=selection.staff_user_id,
                tenant_id=selection.tenant_id,
                storefront_id=selection.storefront_id,
                context_version=selection.context_version,
            )
            .on_conflict_do_nothing(index_elements=["staff_user_id"])
        )

    @staticmethod
    def verify_sync(
        session,
        selection: BotSelection,
        *,
        mutation: bool = True,
        allow_missing_selection: bool = False,
    ) -> None:
        """Runs inside AsyncSession's greenlet, before flush/commit, including after I/O.

        Parent locks precede identity and selection. Switches and writes serialize on
        the selection row; live role checks cannot use cached ORM memberships.
        """
        from models.legacy_owner_auth import LegacyOwnerAuthState
        from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard

        state = (
            session.execute(
                select(LegacyOwnerAuthState)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .first()
        )
        tenant = (
            session.execute(
                select(Tenant)
                .where(Tenant.id == selection.tenant_id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .first()
        )
        staff = (
            session.execute(
                select(StaffUser)
                .where(StaffUser.id == selection.staff_user_id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .first()
        )
        member = (
            session.execute(
                select(TenantMembership)
                .where(
                    TenantMembership.staff_user_id == selection.staff_user_id,
                    TenantMembership.tenant_id == selection.tenant_id,
                )
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .first()
        )
        site = (
            session.execute(
                select(Storefront)
                .where(
                    Storefront.id == selection.storefront_id,
                    Storefront.tenant_id == selection.tenant_id,
                )
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .first()
        )
        if (
            state is not None
            and state.owner_staff_user_id == selection.staff_user_id
            and staff is not None
        ):
            from models import Installer
            from services.legacy_owner_profile_policy import LegacyOwnerProfilePolicy

            installer = (
                session.execute(
                    select(Installer)
                    .where(Installer.id == staff.legacy_installer_id)
                    .with_for_update(read=True)
                )
                .scalars()
                .first()
                if staff.legacy_installer_id
                else None
            )
            if not LegacyOwnerProfilePolicy.allows(staff, installer=installer):
                raise HTTPException(403, "Platform owner identity is unavailable")
        row = (
            session.execute(
                select(BotStaffSelection)
                .where(
                    BotStaffSelection.staff_user_id == selection.staff_user_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            .scalars()
            .first()
        )
        if (
            row is None
            and not (allow_missing_selection and selection.context_version == 0)
        ) or (
            row is not None
            and (
                row.context_version != selection.context_version
                or row.tenant_id != selection.tenant_id
                or row.storefront_id != selection.storefront_id
            )
        ):
            raise context_changed()
        from services.staff_user_service import StaffUserService

        if (
            staff is None
            or not StaffUserService.is_active(staff)
            or staff.telegram_id != selection.telegram_id
            or staff.auth_version != selection.auth_version
            or state is None
            or not LegacyOwnerAuthGuard.allows_staff_identity(
                state,
                staff_user_id=selection.staff_user_id,
                username=str(staff.username or ""),
            )
            or tenant is None
            or tenant.status != "active"
            or site is None
            or site.status != "active"
            or member is None
            or member.status != "active"
            or member.role != selection.role
            or tuple(member.permissions or ()) != selection.permissions
            or (mutation and tenant.demo_read_only)
        ):
            raise HTTPException(403, "Выбранная компания или витрина недоступна")

    @classmethod
    async def bind_request(
        cls,
        session: AsyncSession,
        selection: BotSelection,
        expected_version: int | None,
        *,
        mutation: bool,
    ) -> None:
        if expected_version is None:
            if mutation and not (
                selection.canonical and selection.context_version == 0
            ):
                raise context_changed()
        elif expected_version != selection.context_version:
            raise context_changed()
        existing = await session.get(BotStaffSelection, selection.staff_user_id)
        if existing is None:
            # Initialization precedes business work and must be visible to the
            # separate quick-order idempotency session, not an uncommitted insert.
            await cls.ensure_row(session, selection)
            await session.commit()
        session.info["bot_selection"] = selection
        session.info["bot_context_mutation"] = mutation
        if mutation and selection.demo_read_only:
            raise HTTPException(
                403, "Демонстрационная компания доступна только для чтения"
            )
        cls.install_commit_guard(session)

    @classmethod
    def install_commit_guard(cls, session: AsyncSession) -> None:
        if session.info.get("bot_commit_guard"):
            return
        session.info["bot_commit_guard"] = True

        def verify(sync_session, *args):
            selection = sync_session.info.get("bot_selection")
            if selection is None or sync_session.info.get("bot_verifying"):
                return
            sync_session.info["bot_verifying"] = True
            try:
                with sync_session.no_autoflush:
                    cls.verify_sync(
                        sync_session,
                        selection,
                        mutation=sync_session.info.get("bot_context_mutation", True),
                    )
            finally:
                sync_session.info.pop("bot_verifying", None)

        def before_execute(execution):
            statement = execution.statement
            # Flush has its own fence. Session.execute Core/ORM DML bypasses flush.
            textual_write = isinstance(statement, TextClause) and str(
                statement
            ).lstrip().lower().startswith(("insert ", "update ", "delete "))
            if getattr(statement, "is_dml", False) or textual_write:
                verify(execution.session)

        event.listen(session.sync_session, "before_flush", verify)
        event.listen(session.sync_session, "do_orm_execute", before_execute)
        event.listen(session.sync_session, "before_commit", verify)

    @classmethod
    async def revalidate(cls, session: AsyncSession) -> None:
        selection = session.info.get("bot_selection")
        if selection is not None:
            await session.run_sync(
                lambda sync: cls.verify_sync(sync, selection, mutation=False)
            )

    @classmethod
    async def select(
        cls,
        session: AsyncSession,
        current: BotSelection,
        *,
        tenant_id: int,
        storefront_slug: str,
        expected_version: int,
    ):
        existing = await session.get(BotStaffSelection, current.staff_user_id)
        if existing is None:
            # Initialize current scope before locking the target scope; otherwise
            # a FK check for the old tenant would follow the target Staff lock.
            await cls.ensure_row(session, current)
            await session.commit()
        # Match the same parent→identity→membership/site→selection hierarchy as
        # final writes. Validate target again under locks, not a stale choices list.
        from models.legacy_owner_auth import LegacyOwnerAuthState
        from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard

        state = (
            (
                await session.execute(
                    select(LegacyOwnerAuthState)
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .first()
        )
        tenant = (
            (
                await session.execute(
                    select(Tenant)
                    .where(Tenant.id == tenant_id)
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .first()
        )
        staff = (
            (
                await session.execute(
                    select(StaffUser)
                    .where(StaffUser.id == current.staff_user_id)
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .first()
        )
        member = (
            (
                await session.execute(
                    select(TenantMembership)
                    .where(
                        TenantMembership.tenant_id == tenant_id,
                        TenantMembership.staff_user_id == current.staff_user_id,
                    )
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .first()
        )
        site = (
            (
                await session.execute(
                    select(Storefront)
                    .where(
                        Storefront.tenant_id == tenant_id,
                        Storefront.slug == storefront_slug,
                    )
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .first()
        )
        from services.staff_user_service import StaffUserService

        if (
            tenant is None
            or tenant.status != "active"
            or staff is None
            or not StaffUserService.is_active(staff)
            or staff.telegram_id != current.telegram_id
            or staff.auth_version != current.auth_version
            or member is None
            or member.status != "active"
            or site is None
            or site.status != "active"
            or state is None
            or not LegacyOwnerAuthGuard.allows_staff_identity(
                state,
                staff_user_id=current.staff_user_id,
                username=str(staff.username or ""),
            )
        ):
            raise HTTPException(403, "Компания или витрина недоступна")
        row = (
            (
                await session.execute(
                    select(BotStaffSelection)
                    .where(BotStaffSelection.staff_user_id == current.staff_user_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .one()
        )
        if row.context_version != expected_version:
            raise context_changed()
        if row.tenant_id != tenant_id or row.storefront_id != site.id:
            row.tenant_id = tenant_id
            row.storefront_id = int(site.id)
            row.context_version += 1
            session.add(row)
        await session.commit()
