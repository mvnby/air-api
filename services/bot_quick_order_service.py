import json
import logging
import re
from hashlib import sha256
from datetime import datetime, timedelta
from html import escape
from typing import Any, Optional

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.input_validation import normalize_phone_digits
from models import Lead, Order, OrderWorkStage
from schemas import LeadCreatePayload, LeadQualifyPayload, ManagerOrderUpdatePayload, OrderWorkStageCreatePayload
from services.address_suggest_service import AddressSuggestService
from services.lead_service import LeadService
from services.tenant_scope_service import (
    TenantScope,
    tenant_scope_clause,
)
from services.notification_service import NotificationService
from services.order_service import OrderService

logger = logging.getLogger(__name__)


class BotQuickOrderService:
    SERVICE_LABELS = {
        "turnkey": "Продажа + монтаж",
        "install_only": "Монтаж",
        "pre_install": "Закладка трассы",
        "maintenance": "Обслуживание",
        "repair": "Ремонт",
        "dismantling": "Демонтаж",
    }
    WEEKDAY_ALIASES = {
        "пн": 0,
        "понедельник": 0,
        "понедельника": 0,
        "вт": 1,
        "вторник": 1,
        "вторника": 1,
        "ср": 2,
        "среду": 2,
        "среда": 2,
        "четверг": 3,
        "четверга": 3,
        "чт": 3,
        "пятницу": 4,
        "пятница": 4,
        "пятницы": 4,
        "пт": 4,
        "субботу": 5,
        "суббота": 5,
        "субботы": 5,
        "сб": 5,
        "воскресенье": 6,
        "воскресенья": 6,
        "вс": 6,
    }

    @staticmethod
    def _clean_optional(value: Any) -> Optional[str]:
        cleaned = " ".join(str(value or "").split())
        return cleaned or None

    @staticmethod
    def _extract_json_object(content: str) -> dict[str, Any]:
        text = str(content or "").strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise ValueError("AI response does not contain JSON")
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("AI response JSON must be an object")
        return parsed

    @staticmethod
    def _extract_phone(text: str) -> Optional[str]:
        match = re.search(r"(\+?\d[\d\s().-]{6,}\d)", text)
        if not match:
            return None
        phone = re.sub(r"\s+", " ", match.group(1)).strip()
        return phone

    @classmethod
    def normalize_phone(cls, value: Any) -> Optional[str]:
        cleaned = cls._clean_optional(value)
        if not cleaned:
            return None
        digits = normalize_phone_digits(cleaned)
        if len(digits) == 12 and digits.startswith("375"):
            return f"+{digits}"
        return cleaned

    @staticmethod
    def _infer_service_type(text: str) -> Optional[str]:
        value = text.casefold()
        if any(marker in value for marker in ("демонтаж", "снять кондиционер")):
            return "dismantling"
        if any(marker in value for marker in ("ремонт", "не работает", "не холодит", "ошибк", "диагност")):
            return "repair"
        if any(marker in value for marker in ("обслуж", " то ", "то,", "то.", "сервис", "чистк")):
            return "maintenance"
        if any(marker in value for marker in ("заклад", "трасс")):
            return "pre_install"
        if any(marker in value for marker in ("монтаж", "установ")):
            return "install_only"
        if any(marker in value for marker in ("куп", "подбор", "кондиционер", "сплит")):
            return "turnkey"
        return None

    @staticmethod
    def _parse_date(text: str, *, now: Optional[datetime] = None) -> Optional[datetime]:
        now = now or datetime.now()
        value = text.casefold()
        day: Optional[datetime] = None
        if "послезавтра" in value:
            day = now + timedelta(days=2)
        elif "завтра" in value:
            day = now + timedelta(days=1)
        elif "сегодня" in value:
            day = now
        else:
            for match in re.finditer(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", value):
                day_num = int(match.group(1))
                month_num = int(match.group(2))
                year_num = int(match.group(3)) if match.group(3) else now.year
                if year_num < 100:
                    year_num += 2000
                try:
                    day = now.replace(year=year_num, month=month_num, day=day_num)
                except ValueError:
                    day = None
                    continue
                break
            if day is None:
                weekday_pattern = "|".join(
                    sorted((re.escape(alias) for alias in BotQuickOrderService.WEEKDAY_ALIASES), key=len, reverse=True)
                )
                weekday_match = re.search(rf"\b(?:на\s+|в\s+)?({weekday_pattern})\b", value)
                if weekday_match:
                    target_weekday = BotQuickOrderService.WEEKDAY_ALIASES[weekday_match.group(1)]
                    days_ahead = (target_weekday - now.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    day = now + timedelta(days=days_ahead)

        if day is None:
            return None

        time_match = re.search(r"\b(?:в\s*)?(\d{1,2})(?::(\d{2}))\b", value)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
        else:
            loose_time_match = re.search(
                r"\b(?:в|к)\s*(\d{1,2})(?:(?:[:.](\d{2}))|\s*(?:ч|час(?:а|ов)?)(?:\s*(\d{2}))?)?\b"
                r"|\b(\d{1,2})\s*(?:ч|час(?:а|ов)?)\b",
                value,
            )
            if loose_time_match:
                hour = int(loose_time_match.group(1) or loose_time_match.group(4))
                minute = int(loose_time_match.group(2) or loose_time_match.group(3) or 0)
            else:
                hour = 9
                minute = 0
        if hour > 23 or minute > 59:
            return day.replace(hour=9, minute=0, second=0, microsecond=0)
        return day.replace(hour=hour, minute=minute, second=0, microsecond=0)

    @staticmethod
    def _extract_name(text: str, phone: Optional[str]) -> Optional[str]:
        cleaned = text.replace(phone, " ") if phone else text
        for marker in ("клиент", "имя", "зовут"):
            match = re.search(rf"{marker}\s*[:,-]?\s*([А-ЯA-Z][а-яa-zА-ЯA-Z-]{{2,}})", cleaned)
            if match:
                return match.group(1)
        parts = [part.strip() for part in re.split(r"[,;\n]", cleaned) if part.strip()]
        for part in parts:
            if re.fullmatch(r"[А-ЯA-Z][а-яa-zА-ЯA-Z-]{2,}(?:\s+[А-ЯA-Z][а-яa-zА-ЯA-Z-]{2,})?", part):
                return part
        return None

    @staticmethod
    def _extract_address(text: str) -> Optional[str]:
        match = re.search(
            r"(?:адрес|объект)\s*[:,-]?\s*(.+?)(?:$|тел|телефон|\+?\d[\d\s().-]{6,}\d)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return BotQuickOrderService._clean_optional(match.group(1).strip(" ,.;"))

        markers = ("ул", "улица", "пр-т", "проспект", "пер", "переулок", "победы", "московский")
        parts = [part.strip(" ,.;") for part in re.split(r"[,;\n]", text) if part.strip()]
        for part in parts:
            lowered = part.casefold()
            if any(marker in lowered for marker in markers) and re.search(r"\d", part):
                return BotQuickOrderService._clean_optional(part)
        return None

    @classmethod
    def parse_text_fallback(cls, text: str, *, now: Optional[datetime] = None) -> dict[str, Any]:
        raw_phone = cls._extract_phone(text)
        service_type = cls._infer_service_type(text)
        target_date = cls._parse_date(text, now=now)
        name = cls._extract_name(text, raw_phone)
        address = cls._extract_address(text)
        return {
            "name": name,
            "phone": cls.normalize_phone(raw_phone),
            "address": address,
            "service_type": service_type,
            "target_date": target_date.isoformat() if target_date else None,
            "request_text": cls._clean_optional(text) or "",
            "parser": "fallback",
        }

    @classmethod
    def build_ai_prompt(cls, text: str) -> str:
        return (
            "Ты извлекаешь черновик CRM-заказа из сообщения менеджера Telegram. "
            "Компания занимается продажей, монтажом, ремонтом и обслуживанием кондиционеров. "
            "Верни только JSON без markdown со структурой: "
            '{"name": string|null, "phone": string|null, "address": string|null, '
            '"service_type": "turnkey"|"install_only"|"pre_install"|"maintenance"|"repair"|"dismantling"|null, '
            '"target_date": ISO datetime string|null, "request_text": string}. '
            "Не выдумывай данные. Если дата относительная, считай от текущей даты сервера. "
            f"Сообщение: {json.dumps(text, ensure_ascii=False)}"
        )

    @classmethod
    async def parse_text(cls, text: str) -> dict[str, Any]:
        fallback = cls.parse_text_fallback(text)
        token = settings.DEEPSEEK_TOKEN.strip()
        if not token:
            return await cls.enrich_draft(cls.normalize_draft(fallback))

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.post(
                    settings.DEEPSEEK_API_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "model": settings.DEEPSEEK_MODEL,
                        "messages": [
                            {"role": "system", "content": "Возвращай только валидный JSON."},
                            {"role": "user", "content": cls.build_ai_prompt(text)},
                        ],
                        "temperature": 0,
                    },
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            parsed = cls._extract_json_object(content)
        except Exception:
            return await cls.enrich_draft(cls.normalize_draft(fallback))

        merged = dict(fallback)
        for key in ("name", "phone", "address", "service_type", "target_date", "request_text"):
            value = parsed.get(key)
            if value:
                merged[key] = value
        merged["parser"] = "ai"
        return await cls.enrich_draft(cls.normalize_draft(merged))

    @classmethod
    def normalize_draft(cls, draft: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(draft or {})
        normalized["name"] = cls._clean_optional(normalized.get("name"))
        normalized["phone"] = cls.normalize_phone(normalized.get("phone"))
        normalized["address"] = cls._clean_optional(normalized.get("address"))
        normalized["request_text"] = cls._clean_optional(normalized.get("request_text")) or ""
        service_type = cls._clean_optional(normalized.get("service_type"))
        normalized["service_type"] = service_type if service_type in cls.SERVICE_LABELS else None
        target_date = normalized.get("target_date")
        if isinstance(target_date, datetime):
            normalized["target_date"] = target_date.isoformat()
        elif target_date:
            try:
                normalized["target_date"] = datetime.fromisoformat(str(target_date).replace("Z", "+00:00")).isoformat()
            except ValueError:
                normalized["target_date"] = None
        else:
            normalized["target_date"] = None
        return normalized

    @classmethod
    def _source_fingerprint(cls, normalized: dict[str, Any]) -> str:
        fingerprint_payload = {
            key: normalized.get(key)
            for key in ("name", "phone", "address", "service_type", "target_date", "request_text")
        }
        raw = json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"bot_quick_order:{sha256(raw.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _address_tokens(value: str) -> set[str]:
        return set(re.findall(r"\d+[а-яa-z]?", value.casefold().replace("ё", "е")))

    @classmethod
    async def enrich_draft(cls, draft: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(draft or {})
        address = cls._clean_optional(enriched.get("address"))
        if not address:
            enriched.pop("address_check", None)
            return enriched

        try:
            suggestions = await AddressSuggestService.suggest(address)
        except (RuntimeError, httpx.HTTPError):
            enriched["address_check"] = {
                "status": "unchecked",
                "message": "адрес не проверен, сервис подсказок временно недоступен",
            }
            return enriched
        except Exception:
            logger.exception("BOT_QUICK_ORDER_ADDRESS_CHECK_FAILED")
            enriched["address_check"] = {
                "status": "unchecked",
                "message": "адрес не проверен",
            }
            return enriched

        if not suggestions:
            enriched["address_check"] = {
                "status": "not_found",
                "message": "адрес не найден в подсказках, лучше уточнить у клиента",
            }
            return enriched

        suggestion = suggestions[0]
        suggested_value = cls._clean_optional(suggestion.get("value") or suggestion.get("title"))
        input_tokens = cls._address_tokens(address)
        suggested_tokens = cls._address_tokens(suggested_value or "")
        if input_tokens and not (input_tokens & suggested_tokens):
            enriched["address_check"] = {
                "status": "needs_review",
                "message": "адрес найден, но номер дома стоит сверить",
                "suggestion": suggested_value,
            }
            return enriched
        if not input_tokens:
            enriched["address_check"] = {
                "status": "needs_review",
                "message": "адрес найден, уточните номер дома",
                "suggestion": suggested_value,
            }
            return enriched

        enriched["address_check"] = {
            "status": "confirmed",
            "message": "адрес найден",
            "suggestion": suggested_value,
        }
        return enriched

    @classmethod
    def _display_target_date(cls, draft: dict[str, Any]) -> str | None:
        target_date = draft.get("target_date")
        if target_date:
            try:
                dt = datetime.fromisoformat(str(target_date).replace("Z", "+00:00"))
                return dt.strftime("%d.%m.%Y %H:%M")
            except ValueError:
                return str(target_date)
        return None

    @staticmethod
    def _address_check_text(draft: dict[str, Any]) -> str | None:
        check = draft.get("address_check")
        if not isinstance(check, dict):
            return None
        status = check.get("status")
        message = str(check.get("message") or "").strip()
        suggestion = str(check.get("suggestion") or "").strip()
        if status == "confirmed" and suggestion:
            return f"{message}: {suggestion}"
        if suggestion:
            return f"{message}. Вариант: {suggestion}"
        return message or None

    @classmethod
    def format_draft_preview(cls, draft: dict[str, Any]) -> str:
        target_date = cls._display_target_date(draft)
        service_type = draft.get("service_type")
        address_check_text = cls._address_check_text(draft)
        lines = [
            "<b>Черновик заказа</b>",
            f"Клиент: {escape(str(draft.get('name') or 'не указан'))}",
            f"Телефон: {escape(str(draft.get('phone') or 'не указан'))}",
            f"Адрес: {escape(str(draft.get('address') or 'не указан'))}",
            f"Услуга: {escape(cls.SERVICE_LABELS.get(service_type, 'не указана'))}",
            f"Дата: {escape(target_date or 'не указана')}",
            "",
            f"<i>{escape(str(draft.get('request_text') or ''))}</i>",
        ]
        if address_check_text:
            lines.insert(4, f"Проверка адреса: {escape(address_check_text)}")
        return "\n".join(lines)

    @classmethod
    def format_draft_preview_rich_html(cls, draft: dict[str, Any]) -> str:
        target_date = cls._display_target_date(draft)
        service_type = draft.get("service_type")
        request_text = str(draft.get("request_text") or "").strip()
        address_check_text = cls._address_check_text(draft)
        rich_html = (
            "<h3>Черновик заказа</h3>"
            "<p>"
            f"<b>Клиент:</b> {escape(str(draft.get('name') or 'не указан'))}<br/>"
            f"<b>Телефон:</b> {escape(str(draft.get('phone') or 'не указан'))}<br/>"
            f"<b>Адрес:</b> {escape(str(draft.get('address') or 'не указан'))}<br/>"
            f"{('<b>Проверка адреса:</b> ' + escape(address_check_text) + '<br/>') if address_check_text else ''}"
            f"<b>Услуга:</b> {escape(cls.SERVICE_LABELS.get(service_type, 'не указана'))}<br/>"
            f"<b>Дата:</b> {escape(target_date or 'не указана')}"
            "</p>"
        )
        if request_text:
            rich_html += f"<blockquote>{escape(request_text)}</blockquote>"
        return rich_html

    @classmethod
    async def create_order_from_draft(
        cls,
        session: AsyncSession,
        draft: dict[str, Any],
        *,
        tenant_scope: TenantScope,
        source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        normalized = cls.normalize_draft(draft)
        target_date = None
        if normalized.get("target_date"):
            target_date = datetime.fromisoformat(str(normalized["target_date"]).replace("Z", "+00:00"))

        request_text = normalized["request_text"] or "Быстрый заказ из Telegram"
        source_fingerprint = source_fingerprint or cls._source_fingerprint(normalized)
        result = await session.execute(
            select(Lead)
            .where(
                Lead.source == "bot",
                Lead.source_fingerprint == source_fingerprint,
                tenant_scope_clause(Lead, tenant_scope),
            )
            .order_by(Lead.created_at.desc())
            .with_for_update()
        )
        existing_lead = result.scalars().first()
        if existing_lead and existing_lead.converted_order_id:
            converted_order = (
                await session.execute(
                    select(Order).where(
                        Order.id == int(existing_lead.converted_order_id),
                        tenant_scope_clause(
                            Order,
                            tenant_scope,
                        ),
                    )
                )
            ).scalars().first()
            if not converted_order:
                raise ValueError("Связанный заказ для лида не найден")
            qualification = {
                "lead": LeadService._map_lead(existing_lead),
                "customer_id": int(converted_order.customer_id or 0),
                "order_id": int(converted_order.id or 0),
                "order_created": False,
            }
        else:
            if existing_lead:
                lead_id = int(existing_lead.id or 0)
            else:
                try:
                    lead = await LeadService.create_lead(
                        session,
                        LeadCreatePayload(
                            source="bot",
                            request_text=request_text,
                            name=normalized.get("name"),
                            phone=normalized.get("phone"),
                            segment_hint="b2c",
                            source_fingerprint=source_fingerprint,
                            next_followup_date=target_date,
                        ),
                        tenant_scope=tenant_scope,
                    )
                    lead_id = int(lead["id"])
                except IntegrityError:
                    await session.rollback()
                    concurrent_lead = (
                        await session.execute(
                            select(Lead).where(
                                Lead.source == "bot",
                                Lead.source_fingerprint == source_fingerprint,
                                tenant_scope_clause(
                                    Lead,
                                    tenant_scope,
                                ),
                            )
                        )
                    ).scalars().first()
                    if not concurrent_lead:
                        raise
                    lead_id = int(concurrent_lead.id or 0)
            qualification = await LeadService.qualify_lead(
                session,
                lead_id,
                LeadQualifyPayload(
                    name=normalized.get("name"),
                    phone=normalized.get("phone"),
                    delivery_address=normalized.get("address"),
                    customer_type="individual",
                    order_comment=request_text,
                ),
                tenant_scope=tenant_scope,
            )
        if not qualification:
            raise ValueError("Не удалось квалифицировать лид")

        order_id = int(qualification["order_id"])
        service_type = normalized.get("service_type")
        update_fields: dict[str, Any] = {}
        default_title = OrderService._build_default_order_title(
            service_type=service_type,
            comment=request_text,
        )
        if default_title:
            update_fields["title"] = default_title
        if service_type:
            update_fields["service_type"] = service_type
        if target_date and service_type == "maintenance":
            update_fields["installation_date"] = target_date
            update_fields["status"] = "negotiation"

        order = await OrderService.update_order_for_manager(
            session,
            order_id,
            ManagerOrderUpdatePayload(**update_fields),
            tenant_scope=tenant_scope,
        ) if update_fields else await OrderService.get_order_detail_for_manager(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if not order:
            raise ValueError("Не удалось создать заказ")

        order_created = bool(qualification.get("order_created", True))
        if order_created:
            try:
                await NotificationService.notify_admins_staff_order_created(
                    session,
                    order_id,
                    source_label="Telegram-бот",
                    tenant_scope=tenant_scope,
                )
            except Exception:
                logger.exception("BOT_QUICK_ORDER_NOTIFY_FAILED order_id=%s", order_id)

        if target_date and service_type != "maintenance":
            stage_payload = OrderWorkStageCreatePayload(
                name=cls.SERVICE_LABELS.get(service_type, "Рабочая задача"),
                start_time=target_date,
                manager_comment=request_text,
            )
            existing_stage = (
                await session.execute(
                    select(OrderWorkStage).where(
                        OrderWorkStage.order_id == order_id,
                        OrderWorkStage.name == stage_payload.name,
                        OrderWorkStage.start_time == stage_payload.start_time,
                    )
                )
            ).scalars().first()
            if existing_stage:
                order = await OrderService.get_order_detail_for_manager(
                    session,
                    order_id,
                    tenant_scope=tenant_scope,
                ) or order
            else:
                try:
                    updated = await OrderService.add_order_stage(
                        session,
                        order_id,
                        stage_payload,
                        tenant_scope=tenant_scope,
                    )
                    order = updated or order
                except IntegrityError:
                    await session.rollback()
                    concurrent_stage = (
                        await session.execute(
                            select(OrderWorkStage).where(
                                OrderWorkStage.order_id == order_id,
                                OrderWorkStage.name == stage_payload.name,
                                OrderWorkStage.start_time == stage_payload.start_time,
                                OrderWorkStage.installer_id.is_(None),
                            )
                        )
                    ).scalars().first()
                    if not concurrent_stage:
                        raise
                    order = await OrderService.get_order_detail_for_manager(
                        session,
                        order_id,
                        tenant_scope=tenant_scope,
                    ) or order

        # This orchestrator is the outer command boundary. Nested Order/Lead
        # commands deliberately use SAVEPOINTs when earlier authorization or
        # idempotency reads have already opened the session transaction.
        await session.commit()
        order["_bot_order_created"] = order_created
        return order
