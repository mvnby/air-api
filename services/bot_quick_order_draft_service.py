"""Versioned, staff-owned quick-order drafts in the existing durable bot state store."""

import re
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api_contracts.bot import BotQuickOrderDraft
from models import BotFsmState, Customer
from services.bot_quick_order_api_service import BotQuickOrderApiService
from services.bot_quick_order_service import BotQuickOrderService
from services.order_scenarios import SCENARIOS
from services.tenant_scope_service import SystemTenantScopeResolver, tenant_scope_clause
from core.input_validation import normalize_phone_digits


class BotQuickOrderDraftConflictError(ValueError):
    pass


class BotQuickOrderDraftNotFoundError(LookupError):
    pass


class BotQuickOrderDraftService:
    TTL = timedelta(hours=24)
    EDITABLE_FIELDS = frozenset({
        "customer_id", "customer_type", "name", "contact_name", "contact_phone", "contact_email", "phone", "email", "inn",
        "customer_branch_id", "address", "legal_address", "workflow_type",
        "service_type", "target_date", "target_date_precision", "equipment_summary",
        "equipment_count", "equipment_type",
    })

    @staticmethod
    def _key(draft_id: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", draft_id):
            raise BotQuickOrderDraftNotFoundError("Черновик не найден")
        return f"quick-order:{draft_id}"

    @classmethod
    async def _row(cls, session: AsyncSession, *, draft_id: str, telegram_id: int, lock: bool = False) -> BotFsmState:
        stmt = select(BotFsmState).where(
            BotFsmState.storage_key == cls._key(draft_id),
            BotFsmState.user_id == telegram_id,
            BotFsmState.destiny == "quick_order",
        )
        if lock:
            stmt = stmt.with_for_update()
        row = (await session.execute(stmt)).scalars().first()
        if row is None:
            raise BotQuickOrderDraftNotFoundError("Черновик не найден")
        return row

    @staticmethod
    def _response(row: BotFsmState) -> dict:
        data = dict(row.data or {})
        return {
            "draft_id": row.storage_key.removeprefix("quick-order:"),
            "version": data["version"],
            "status": data["status"],
            "draft": data["draft"],
            "order_id": data.get("order_id"),
            "expires_at": data["expires_at"],
            "scenarios": [
                {"label": item.label, "workflow_type": item.workflow_type,
                 "service_type": item.service_type} for item in SCENARIOS
            ],
        }

    @classmethod
    def _check_active(cls, row: BotFsmState, expected_version: int) -> dict:
        data = dict(row.data or {})
        if data.get("status") != "active":
            raise BotQuickOrderDraftConflictError("Черновик уже закрыт")
        if datetime.fromisoformat(data["expires_at"]) <= datetime.now():
            raise BotQuickOrderDraftConflictError("Срок действия черновика истёк")
        if data.get("version") != expected_version:
            raise BotQuickOrderDraftConflictError("Черновик уже изменился. Откройте актуальную карточку")
        return data

    @classmethod
    async def start(
        cls, session: AsyncSession, *, telegram_id: int, text: str, customer_id: int | None = None
    ) -> dict:
        await BotQuickOrderApiService._require_manager(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        customer = None
        if customer_id is not None:
            customer = (
                await session.execute(select(Customer).where(
                    Customer.id == customer_id, tenant_scope_clause(Customer, tenant_scope)
                ))
            ).scalars().first()
            if customer is None:
                raise ValueError("Выбранный клиент не найден")
        parsed = await BotQuickOrderService.parse_text(text) if text.strip() else {}
        parsed = BotQuickOrderApiService._draft_projection(parsed)
        if customer is not None:
            parsed.update({
                "customer_id": int(customer.id),
                "customer_type": customer.type.value if hasattr(customer.type, "value") else str(customer.type),
                "name": customer.name,
                "phone": customer.phone or None,
                "email": customer.email,
                "inn": customer.inn,
                "request_text": text.strip() or "Заказ для существующего клиента",
            })
            parsed["field_sources"] = {
                **parsed.get("field_sources", {}),
                **{key: "customer" for key in ("customer_id", "customer_type", "name", "phone", "email", "inn") if parsed.get(key) is not None},
            }
        draft = BotQuickOrderDraft.model_validate(parsed)
        draft_id = uuid4().hex
        expires_at = datetime.now() + cls.TTL
        row = BotFsmState(
            storage_key=cls._key(draft_id),
            bot_id=0,
            chat_id=0,
            user_id=telegram_id,
            destiny="quick_order",
            state="active",
            data={
                "version": 1, "status": "active",
                "draft": draft.model_dump(mode="json"),
                "expires_at": expires_at.isoformat(),
            },
        )
        session.add(row)
        await session.commit()
        return cls._response(row)

    @classmethod
    async def get(cls, session: AsyncSession, *, telegram_id: int, draft_id: str) -> dict:
        await BotQuickOrderApiService._require_manager(session, telegram_id)
        return cls._response(await cls._row(session, draft_id=draft_id, telegram_id=telegram_id))

    @classmethod
    async def search_customers(cls, session: AsyncSession, *, telegram_id: int, query: str) -> dict:
        await BotQuickOrderApiService._require_manager(session, telegram_id)
        scope = await SystemTenantScopeResolver.resolve(session)
        value = query.strip()
        if len(value) < 3:
            raise ValueError("Введите не менее трёх символов")
        name_query = value.replace("%", "").replace("_", "").strip()
        if not name_query and not value.isdigit():
            raise ValueError("Уточните УНП, телефон или имя клиента")
        digits = normalize_phone_digits(value)
        predicates = [Customer.name.ilike(f"%{name_query}%")] if name_query else []
        if len(digits) >= 7:
            predicates.append(
                func.regexp_replace(func.coalesce(Customer.phone, ""), r"\D", "", "g") == digits
            )
        if value.isdigit() and len(value) == 9:
            predicates.append(Customer.inn == value)
        rows = (
            await session.execute(
                select(Customer).where(
                    tenant_scope_clause(Customer, scope), or_(*predicates)
                ).order_by(Customer.id.desc()).limit(5)
            )
        ).scalars().all()
        return {"items": [{
            "id": int(item.id), "name": item.name,
            "customer_type": item.type.value if hasattr(item.type, "value") else str(item.type),
            "phone": item.phone, "inn": item.inn,
        } for item in rows]}

    @classmethod
    async def patch(
        cls, session: AsyncSession, *, telegram_id: int, draft_id: str,
        expected_version: int, text: str | None, changes: dict
    ) -> dict:
        await BotQuickOrderApiService._require_manager(session, telegram_id)
        unknown = set(changes) - cls.EDITABLE_FIELDS
        if unknown:
            raise ValueError("Недопустимые поля правки: " + ", ".join(sorted(unknown)))
        parsed_changes: dict = {}
        if text and text.strip():
            current_row = await cls._row(session, draft_id=draft_id, telegram_id=telegram_id)
            current_data = cls._check_active(current_row, expected_version)
            parsed = await BotQuickOrderService.parse_text(
                text, current_draft=current_data["draft"]
            )
            for key in cls.EDITABLE_FIELDS:
                if key in {"customer_branch_id", "legal_address"}:
                    continue
                if parsed.get(key) is not None:
                    parsed_changes[key] = parsed[key]
            if re.search(r"\bдат[уы]?\b.*\b(?:убери|удали|отмени|не надо)\b", text, re.IGNORECASE):
                parsed_changes["target_date"] = None
                parsed_changes["target_date_precision"] = None
            if re.search(r"\bадрес\b.*\b(?:убери|удали|не надо)\b", text, re.IGNORECASE):
                parsed_changes["address"] = None
            # A correction to one field must not replace an established client.
            if not re.search(r"\b(?:клиент|заказчик|физлицо|ип|ооо)\b", text, re.IGNORECASE):
                for key in ("name", "customer_type", "phone", "email"):
                    parsed_changes.pop(key, None)
        parsed_changes.update(changes)
        if "customer_id" in parsed_changes and parsed_changes["customer_id"] is None:
            raise ValueError("Для нового клиента начните новый черновик")
        if "customer_id" in parsed_changes and parsed_changes["customer_id"] is not None:
            scope = await SystemTenantScopeResolver.resolve(session)
            customer = (
                await session.execute(select(Customer).where(
                    Customer.id == int(parsed_changes["customer_id"]),
                    tenant_scope_clause(Customer, scope),
                ))
            ).scalars().first()
            if customer is None:
                raise ValueError("Выбранный клиент не найден")
            parsed_changes.update({
                "customer_id": int(customer.id),
                "customer_type": customer.type.value if hasattr(customer.type, "value") else str(customer.type),
                "name": customer.name, "phone": customer.phone or None, "email": customer.email,
                "inn": customer.inn,
            })
        row = await cls._row(session, draft_id=draft_id, telegram_id=telegram_id, lock=True)
        data = cls._check_active(row, expected_version)
        explicit_correction = bool(text and re.search(
            r"\b(?:исправь|замени|убери|удали|не\s+\w+[\w\s,]*\s+а\s+\w+)\b",
            text, re.IGNORECASE,
        ))
        if not explicit_correction:
            existing_sources = data["draft"].get("field_sources") or {}
            for key in list(parsed_changes):
                if key not in changes and existing_sources.get(key) == "user":
                    parsed_changes.pop(key)
        if data["draft"].get("customer_id") and "customer_id" not in parsed_changes:
            for key in ("name", "customer_type", "inn"):
                if key in parsed_changes and parsed_changes[key] != data["draft"].get(key):
                    raise BotQuickOrderDraftConflictError(
                        "Выбранный клиент не изменён. Для смены используйте кнопку «Клиент»"
                    )
        next_draft = dict(data["draft"])
        if "service_type" in parsed_changes and "workflow_type" not in parsed_changes:
            next_draft["workflow_type"] = None
        if "workflow_type" in parsed_changes and "service_type" not in parsed_changes:
            next_draft["service_type"] = None
        next_draft.update(parsed_changes)
        next_sources = dict(next_draft.get("field_sources") or {})
        source = "user" if changes or explicit_correction else (parsed.get("parser") or "fallback") if text else "user"
        for key in parsed_changes:
            next_sources[key] = source
        next_draft["field_sources"] = next_sources
        if text and text.strip():
            next_draft["request_text"] = (next_draft["request_text"] + "\nПравка: " + text.strip())[:12_000]
        next_draft = BotQuickOrderApiService._draft_projection(next_draft)
        next_draft = BotQuickOrderDraft.model_validate(next_draft)
        data["draft"] = next_draft.model_dump(mode="json")
        data["version"] += 1
        row.data = data
        row.updated_at = datetime.now()
        session.add(row)
        await session.commit()
        return cls._response(row)

    @classmethod
    async def cancel(cls, session: AsyncSession, *, telegram_id: int, draft_id: str, expected_version: int) -> dict:
        await BotQuickOrderApiService._require_manager(session, telegram_id)
        row = await cls._row(session, draft_id=draft_id, telegram_id=telegram_id, lock=True)
        data = cls._check_active(row, expected_version)
        data["status"] = "cancelled"
        data["version"] += 1
        row.data = data
        row.state = "cancelled"
        session.add(row)
        await session.commit()
        return cls._response(row)

    @classmethod
    async def create(cls, session: AsyncSession, *, telegram_id: int, draft_id: str, expected_version: int) -> dict:
        await BotQuickOrderApiService._require_manager(session, telegram_id)
        row = await cls._row(session, draft_id=draft_id, telegram_id=telegram_id, lock=True)
        data = dict(row.data or {})
        if data.get("status") == "created":
            return {"order_id": data["order_id"], "customer_id": data["customer_id"], "created": False}
        cls._check_active(row, expected_version)
        result = await BotQuickOrderApiService.create_for_manager(
            session,
            telegram_id=telegram_id,
            idempotency_key=f"draft:{draft_id}",
            draft=BotQuickOrderDraft.model_validate(data["draft"]),
        )
        data["status"] = "created"
        data["version"] += 1
        data["order_id"] = result.order_id
        data["customer_id"] = result.customer_id
        row.data = data
        row.state = "created"
        session.add(row)
        await session.commit()
        return {"order_id": result.order_id, "customer_id": result.customer_id, "created": result.created}
