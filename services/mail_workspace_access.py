"""Live mail account permissions and company-owned identity."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.config import settings
from models import StaffUser, Storefront, Tenant, TenantMembership
from schemas_mail import MailAccountListResponse, MailAccountResponse
from services.storefront_settings_service import StorefrontSettingsService
from services.tenant_entity_access_service import TenantEntityAccessService


class MailNotFoundError(LookupError):
    pass


class MailVersionConflictError(RuntimeError):
    def __init__(self, current_version: int):
        super().__init__("Письмо уже изменилось. Откройте актуальную версию")
        self.current_version = current_version


class MailStateConflictError(RuntimeError):
    pass


class MailWorkspaceAccess:
    @staticmethod
    async def require_actor(session: AsyncSession, actor: CommandActor, *, write: bool = False):
        scope = actor.tenant_scope
        if write and scope.demo_read_only:
            raise PermissionError("Демонстрационная компания доступна только для чтения")
        row = (await session.execute(select(Tenant.is_system, Tenant.demo_read_only).join(
            TenantMembership, TenantMembership.tenant_id == Tenant.id
        ).join(StaffUser, StaffUser.id == TenantMembership.staff_user_id).join(
            Storefront, Storefront.tenant_id == Tenant.id
        ).where(
            Tenant.id == scope.tenant_id, Tenant.status == "active",
            Storefront.id == scope.storefront_id, Storefront.status == "active",
            TenantMembership.staff_user_id == actor.staff_user_id,
            TenantMembership.status == "active",
            TenantMembership.role.in_(["owner", "admin", "manager"]),
            StaffUser.status == "active", StaffUser.must_change_password.is_(False),
        ))).one_or_none()
        if row is None or bool(row.is_system) != scope.is_system:
            raise PermissionError("Активный доступ сотрудника к компании обязателен")
        if write and row.demo_read_only:
            raise PermissionError("Демонстрационная компания доступна только для чтения")
        return bool(row.is_system)

    @classmethod
    async def accounts(cls, session: AsyncSession, actor: CommandActor) -> MailAccountListResponse:
        system = await cls.require_actor(session, actor)
        email = settings.MAIL_FROM_EMAIL or settings.MAIL_SMTP_USERNAME
        if not system or not email or not settings.MAIL_SMTP_USERNAME or not settings.MAIL_SMTP_PASSWORD:
            return MailAccountListResponse(items=[])
        company = (await StorefrontSettingsService.get_settings(session, tenant_scope=actor.tenant_scope)).site
        signature = "\n".join(str(value).strip() for value in (
            company.display_name, company.phone, company.email, company.address
        ) if value and str(value).strip())
        return MailAccountListResponse(items=[MailAccountResponse(
            id="system", email=email, name=settings.MAIL_FROM_NAME or company.display_name,
            signature=signature,
        )])

    @classmethod
    async def require_account(cls, session: AsyncSession, actor: CommandActor, account_id: str):
        accounts = await cls.accounts(session, actor)
        account = next((item for item in accounts.items if item.id == account_id), None)
        if account is None:
            raise PermissionError("Для этой компании почтовый аккаунт не настроен")
        return account

    @staticmethod
    async def validate_links(session: AsyncSession, actor: CommandActor, *, order_id: int | None, customer_id: int | None):
        if order_id is not None and await TenantEntityAccessService.get_order(
            session, order_id, tenant_scope=actor.tenant_scope
        ) is None:
            raise MailNotFoundError("Связанный заказ недоступен")
        if customer_id is not None and await TenantEntityAccessService.get_customer(
            session, customer_id, tenant_scope=actor.tenant_scope
        ) is None:
            raise MailNotFoundError("Связанный клиент недоступен")
