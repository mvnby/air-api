"""Authorized file and nameplate operations exposed to the Telegram bot."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from services.bot_api_access import require_bot_manager, require_bot_staff
from services.bot_order_attachment_service import BotOrderAttachmentService
from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.bot_warranty_nameplate_service import BotWarrantyNameplateService
from services.tenant_scope_service import SystemTenantScopeResolver


class BotMediaApiService:
    @staticmethod
    async def list_recent_orders(
        session: AsyncSession, *, telegram_id: int, limit: int
    ) -> list[dict[str, Any]]:
        await require_bot_manager(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        return await BotOrderAttachmentService.list_recent_orders(
            session,
            limit=limit,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def attach_to_order(
        session: AsyncSession,
        *,
        telegram_id: int,
        order_id: int,
        content: bytes,
        file_id: str,
        filename: str,
        mime_type: str,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> dict[str, Any] | None:
        context = await require_bot_staff(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        allowed = await BotOrderAttachmentService.can_attach_to_order(
            session,
            order_id,
            telegram_user_id=telegram_id,
            can_attach_any=context.is_manager,
            tenant_scope=tenant_scope,
        )
        if not allowed:
            return None
        return await BotOrderAttachmentService.attach_to_order(
            session,
            order_id,
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            content=content,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def list_repair_orders(
        session: AsyncSession, *, telegram_id: int, limit: int
    ) -> list[dict[str, Any]]:
        context = await require_bot_staff(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        return await BotRepairNameplateService.list_repair_orders(
            session,
            telegram_user_id=telegram_id,
            can_attach_any=context.is_manager,
            limit=limit,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def recognize_repair_nameplate(
        session: AsyncSession,
        *,
        telegram_id: int,
        order_id: int,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> dict[str, Any] | None:
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
            return None
        recognized = await BotRepairNameplateService.recognize_bytes(
            content=content,
            filename=filename,
            mime_type=mime_type,
        )
        preview = await BotRepairNameplateService.build_merge_preview(
            session,
            order_id=order_id,
            extracted=recognized.get("extracted") or {},
            tenant_scope=tenant_scope,
        )
        return {**recognized, "order_id": order_id, "merge_preview": preview or {}}

    @staticmethod
    async def apply_repair_nameplate(
        session: AsyncSession,
        *,
        telegram_id: int,
        order_id: int,
        content: bytes,
        file_id: str,
        filename: str,
        mime_type: str,
        raw_text: str,
        extracted: dict[str, Any],
        validation_flags: dict[str, Any],
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> dict[str, Any] | None:
        context = await require_bot_staff(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        return await BotRepairNameplateService.apply_to_order(
            session,
            order_id,
            extracted=extracted,
            raw_text=raw_text,
            validation_flags=validation_flags,
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            can_attach_any=context.is_manager,
            file_content=content,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def list_warranty_orders(
        session: AsyncSession, *, telegram_id: int, limit: int
    ) -> dict[str, Any]:
        context = await require_bot_staff(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        return await BotWarrantyNameplateService.list_installation_orders(
            session,
            telegram_user_id=telegram_id,
            can_attach_any=context.is_manager,
            limit=limit,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def recognize_warranty_nameplate(
        session: AsyncSession,
        *,
        telegram_id: int,
        order_id: int,
        unit_type: str,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> dict[str, Any] | None:
        context = await require_bot_staff(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        allowed = await BotWarrantyNameplateService.can_use_order(
            session,
            order_id,
            telegram_user_id=telegram_id,
            can_attach_any=context.is_manager,
            tenant_scope=tenant_scope,
        )
        if not allowed:
            return None
        recognized = await BotRepairNameplateService.recognize_bytes(
            content=content,
            filename=filename,
            mime_type=mime_type,
        )
        preview = await BotWarrantyNameplateService.build_merge_preview(
            session,
            order_id=order_id,
            unit_type=unit_type,
            extracted=recognized.get("extracted") or {},
            tenant_scope=tenant_scope,
        )
        return {
            **recognized,
            "order_id": order_id,
            "unit_type": unit_type,
            "merge_preview": preview or {},
        }

    @staticmethod
    async def apply_warranty_nameplate(
        session: AsyncSession,
        *,
        telegram_id: int,
        order_id: int,
        unit_type: str,
        content: bytes,
        file_id: str,
        filename: str,
        mime_type: str,
        raw_text: str,
        extracted: dict[str, Any],
        validation_flags: dict[str, Any],
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> dict[str, Any] | None:
        context = await require_bot_staff(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        return await BotWarrantyNameplateService.apply_to_order(
            session,
            order_id,
            unit_type=unit_type,
            extracted=extracted,
            raw_text=raw_text,
            validation_flags=validation_flags,
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            can_attach_any=context.is_manager,
            file_content=content,
            tenant_scope=tenant_scope,
        )
