"""Authorized diagnostic draft operations for the Telegram repair workflow."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from services.bot_api_access import require_bot_staff
from services.bot_defect_act_service import BotDefectActService
from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.tenant_scope_service import SystemTenantScopeResolver, TenantScope


class BotRepairContextApiService:
    @staticmethod
    async def _require_order_access(
        session: AsyncSession, *, telegram_id: int, order_id: int
    ) -> TenantScope:
        context = await require_bot_staff(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        allowed = await BotRepairNameplateService.can_use_order(
            session,
            order_id,
            telegram_user_id=telegram_id,
            can_attach_any=context.is_manager,
            tenant_scope=tenant_scope,
        )
        if not allowed:
            raise LookupError("Repair order is not available to this staff user")
        return tenant_scope

    @classmethod
    async def build_comment_draft(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        order_id: int,
        comment: str,
    ) -> dict[str, Any]:
        tenant_scope = await cls._require_order_access(
            session, telegram_id=telegram_id, order_id=order_id
        )
        draft = await BotDefectActService.build_diagnostic_comment_draft(
            session,
            order_id=order_id,
            comment=comment,
            tenant_scope=tenant_scope,
        )
        if not draft:
            raise LookupError("Repair order not found")
        return draft

    @classmethod
    async def build_preset_draft(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        order_id: int,
        fault_type: str,
    ) -> dict[str, Any]:
        tenant_scope = await cls._require_order_access(
            session, telegram_id=telegram_id, order_id=order_id
        )
        draft = await BotDefectActService.build_diagnostic_preset_draft(
            session,
            order_id=order_id,
            fault_type=fault_type,
            tenant_scope=tenant_scope,
        )
        if not draft:
            raise LookupError("Repair order not found")
        return draft

    @classmethod
    async def apply_comment(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        order_id: int,
        repair_meta_draft: dict[str, Any],
        raw_comment: str,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> dict[str, Any]:
        context = await require_bot_staff(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        result = await BotDefectActService.apply_diagnostic_comment(
            session,
            order_id,
            repair_meta_draft=repair_meta_draft,
            raw_comment=raw_comment,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            can_attach_any=context.is_manager,
            tenant_scope=tenant_scope,
        )
        if not result:
            raise LookupError("Repair order is not available to this staff user")
        return result
