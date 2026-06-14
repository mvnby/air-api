import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from schemas import ManagerOrderCreatePayload, OrderWorkStageCreatePayload
from services.order_service import OrderService


class BotQuickOrderService:
    SERVICE_LABELS = {
        "turnkey": "Продажа + монтаж",
        "install_only": "Монтаж",
        "pre_install": "Закладка трассы",
        "maintenance": "Обслуживание",
        "repair": "Ремонт",
        "dismantling": "Демонтаж",
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
            match = re.search(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", value)
            if match:
                day_num = int(match.group(1))
                month_num = int(match.group(2))
                year_num = int(match.group(3)) if match.group(3) else now.year
                if year_num < 100:
                    year_num += 2000
                try:
                    day = now.replace(year=year_num, month=month_num, day=day_num)
                except ValueError:
                    day = None

        if day is None:
            return None

        time_match = re.search(r"\b(?:в\s*)?(\d{1,2})(?::(\d{2}))\b", value)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
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
        phone = cls._extract_phone(text)
        service_type = cls._infer_service_type(text)
        target_date = cls._parse_date(text, now=now)
        name = cls._extract_name(text, phone)
        address = cls._extract_address(text)
        return {
            "name": name,
            "phone": phone,
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
            return fallback

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
            return fallback

        merged = dict(fallback)
        for key in ("name", "phone", "address", "service_type", "target_date", "request_text"):
            value = parsed.get(key)
            if value:
                merged[key] = value
        merged["parser"] = "ai"
        return cls.normalize_draft(merged)

    @classmethod
    def normalize_draft(cls, draft: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(draft or {})
        normalized["name"] = cls._clean_optional(normalized.get("name"))
        normalized["phone"] = cls._clean_optional(normalized.get("phone"))
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
    def format_draft_preview(cls, draft: dict[str, Any]) -> str:
        target_date = draft.get("target_date")
        if target_date:
            try:
                dt = datetime.fromisoformat(str(target_date).replace("Z", "+00:00"))
                target_date = dt.strftime("%d.%m.%Y %H:%M")
            except ValueError:
                pass
        service_type = draft.get("service_type")
        lines = [
            "<b>Черновик заказа</b>",
            f"Клиент: {draft.get('name') or 'не указан'}",
            f"Телефон: {draft.get('phone') or 'не указан'}",
            f"Адрес: {draft.get('address') or 'не указан'}",
            f"Услуга: {cls.SERVICE_LABELS.get(service_type, 'не указана')}",
            f"Дата: {target_date or 'не указана'}",
            "",
            f"<i>{draft.get('request_text') or ''}</i>",
        ]
        return "\n".join(lines)

    @classmethod
    async def create_order_from_draft(
        cls,
        session: AsyncSession,
        draft: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = cls.normalize_draft(draft)
        target_date = None
        if normalized.get("target_date"):
            target_date = datetime.fromisoformat(str(normalized["target_date"]).replace("Z", "+00:00"))

        payload = ManagerOrderCreatePayload(
            source="bot",
            request_text=normalized["request_text"] or "Быстрый заказ из Telegram",
            name=normalized.get("name"),
            phone=normalized.get("phone"),
            address=normalized.get("address"),
            service_type=normalized.get("service_type"),
            target_date=target_date,
            customer_type="individual",
        )
        order = await OrderService.create_manager_order(session=session, payload=payload)
        if not order:
            raise ValueError("Не удалось создать заказ")

        service_type = normalized.get("service_type")
        if target_date and service_type != "maintenance":
            stage_payload = OrderWorkStageCreatePayload(
                name=cls.SERVICE_LABELS.get(service_type, "Рабочая задача"),
                start_time=target_date,
                manager_comment=normalized["request_text"],
            )
            updated = await OrderService.add_order_stage(session, int(order["id"]), stage_payload)
            return updated or order

        return order
