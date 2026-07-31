import hashlib
import json
import re
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import String, cast, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import Customer, LeadSource, Order, OrderStatus
from services.bank_email_parser_service import BankEmailParserService
from services.order_service import OrderService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import TenantScope


@dataclass
class EmailLeadProcessResult:
    status: str
    is_candidate: bool = False
    used_ai: bool = False
    lead_id: Optional[int] = None
    order_id: Optional[int] = None
    reason: Optional[str] = None


@dataclass
class EmailLeadDecision:
    status: str
    sender_email: str
    subject: str
    reason: Optional[str] = None
    lead_id: Optional[int] = None
    order_id: Optional[int] = None


@dataclass
class EmailLeadImportResult:
    processed: int = 0
    scanned_since: Optional[str] = None
    last_import_at: Optional[str] = None
    candidates: int = 0
    ai_checked: int = 0
    would_create: int = 0
    created: int = 0
    duplicates: int = 0
    rejected: int = 0
    failed: int = 0
    lead_ids: list[int] = field(default_factory=list)
    created_lead_ids: list[int] = field(default_factory=list)
    order_ids: list[int] = field(default_factory=list)
    created_order_ids: list[int] = field(default_factory=list)
    decisions: list[EmailLeadDecision] = field(default_factory=list)


class EmailLeadIntakeService:
    """Two-stage email intake: keyword prefilter, then AI lead classification."""

    DEFAULT_KEYWORDS = (
        "кондиционер",
        "кондиционеры",
        "кондиционирование",
        "сплит",
        "сплит-система",
        "мультисплит",
        "внутренний блок",
        "наружный блок",
        "кассетный",
        "канальный",
        "чиллер",
        "тепловой насос",
        "вентиляция",
        "монтаж",
        "установка",
        "демонтаж",
        "ремонт",
        "обслуживание",
        "диагностика",
        "заправка",
        "заказ",
        "купить",
        "стоимость",
        "цена",
        "коммерческое предложение",
        "счет",
        "счёт",
    )
    HVAC_CONTEXT_STEMS = (
        "кондиц",
        "сплит",
        "вентиляц",
        "чиллер",
        "теплов",
        "климат",
        "кассетн",
        "канальн",
        "фанкойл",
        "внутренн",
        "наружн",
        "блок",
    )
    LEAD_INTENT_STEMS = (
        "цен",
        "стоим",
        "предложен",
        "коммерческ",
        "кп",
        "счет",
        "счёт",
        "заявк",
        "заказ",
        "просим",
        "подготов",
        "обслуживан",
        "ремонт",
        "монтаж",
        "установ",
        "демонтаж",
        "диагност",
        "заправ",
        "сервис",
    )

    @staticmethod
    def _configured_keywords() -> tuple[str, ...]:
        raw = str(getattr(settings, "MAIL_IMAP_LEAD_KEYWORDS", "") or "").strip()
        if not raw:
            return EmailLeadIntakeService.DEFAULT_KEYWORDS
        configured = tuple(item.strip().casefold() for item in raw.split(",") if item.strip())
        return configured or EmailLeadIntakeService.DEFAULT_KEYWORDS

    @staticmethod
    def normalize_text(raw: str, *, max_length: int = 6000) -> str:
        text = str(raw or "").replace("\xa0", " ")
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_length].strip()

    @staticmethod
    def _has_any_stem(haystack: str, stems: tuple[str, ...]) -> bool:
        return any(stem in haystack for stem in stems)

    @staticmethod
    def looks_like_lead_candidate(*, sender_email: str, subject: str, raw_body: str) -> bool:
        sender = str(sender_email or "").strip().lower()
        clean_subject = EmailLeadIntakeService.normalize_text(subject, max_length=500).casefold()
        clean_body = EmailLeadIntakeService.normalize_text(raw_body, max_length=2000).casefold()

        if BankEmailParserService.is_bank_credit_email(sender, subject):
            return False
        if sender == BankEmailParserService.BANK_SENDER:
            return False

        haystack = f"{clean_subject} {clean_body}"
        if any(keyword in haystack for keyword in EmailLeadIntakeService._configured_keywords()):
            return True

        has_hvac_context = EmailLeadIntakeService._has_any_stem(
            haystack,
            EmailLeadIntakeService.HVAC_CONTEXT_STEMS,
        )
        has_lead_intent = EmailLeadIntakeService._has_any_stem(
            haystack,
            EmailLeadIntakeService.LEAD_INTENT_STEMS,
        )
        return has_hvac_context and has_lead_intent

    @staticmethod
    def build_fingerprint(
        *,
        sender_email: str,
        subject: str,
        raw_body: str,
        message_id: Optional[str] = None,
        email_date_raw: Optional[str] = None,
    ) -> str:
        text = EmailLeadIntakeService.normalize_text(raw_body, max_length=4000).casefold()
        parts = [
            str(message_id or "").strip(),
            str(sender_email or "").strip().lower(),
            EmailLeadIntakeService.normalize_text(subject, max_length=500).casefold(),
            str(email_date_raw or "").strip(),
            text,
        ]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    async def _find_duplicate_order(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        message_id: Optional[str],
        fingerprint: str,
    ) -> Optional[Order]:
        predicates = [cast(Order.technical_meta, String).ilike(f"%{fingerprint}%")]
        if message_id:
            predicates.append(cast(Order.technical_meta, String).ilike(f"%{message_id}%"))
        result = await session.execute(
            select(Order)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                Order.lead_source == LeadSource.EMAIL,
                TenantEntityAccessService.order_clause(tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope),
                or_(*predicates),
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def build_prompt(
        *,
        sender_email: str,
        sender_name: Optional[str],
        subject: str,
        raw_body: str,
        email_date_raw: Optional[str] = None,
    ) -> str:
        inputs = {
            "sender_email": sender_email,
            "sender_name": sender_name,
            "subject": subject,
            "email_date": email_date_raw,
            "body": EmailLeadIntakeService.normalize_text(raw_body, max_length=5000),
        }
        return (
            "Ты классифицируешь входящие письма для CRM компании по продаже, монтажу, ремонту "
            "и обслуживанию систем кондиционирования.\n\n"
            "Задача: определить, является ли письмо потенциальным заказом или лидом. "
            "Потенциальный заказ: запрос цены, подбора, покупки, монтажа, ремонта, диагностики, "
            "обслуживания, коммерческого предложения или счета по климатическому оборудованию.\n\n"
            "Не считай лидом банковские уведомления, рассылки, спам, вакансии, личную переписку, "
            "автоматические отчеты и письма без намерения купить/заказать услугу.\n\n"
            "Особое правило по вложениям и документам: учитывай распознанный текст вложений как часть письма. "
            "Но если письмо содержит только договор, акт, счет, накладную или бухгалтерские документы по уже оформленной "
            "сделке, не считай это новым лидом, даже если внутри документа есть кондиционеры. Исключение: в письме или "
            "вложении явно просят подготовить коммерческое предложение, цену, ремонт, монтаж, диагностику или обслуживание.\n\n"
            "Верни только JSON-объект без markdown со структурой:\n"
            "{\n"
            '  "is_potential_order": true или false,\n'
            '  "confidence": число от 0 до 1,\n'
            '  "name": имя контактного лица или null,\n'
            '  "phone": телефон или null,\n'
            '  "email": email клиента или null,\n'
            '  "inn": УНП/ИНН компании или null,\n'
            '  "company_name": название компании или null,\n'
            '  "segment_hint": "b2b", "b2c" или "unknown",\n'
            '  "request_text": краткое описание запроса для менеджера,\n'
            '  "reason": короткая причина решения\n'
            "}\n\n"
            "Правила:\n"
            "- Не выдумывай телефон, email, УНП, компанию и имя.\n"
            "- Если письмо от формы сайта, email отправителя может быть техническим; указывай email клиента только если он есть в теле письма.\n"
            "- request_text должен быть понятным менеджеру и сохранять факты письма.\n"
            "- Если уверенность ниже 0.55, ставь is_potential_order=false.\n\n"
            "Входные данные:\n"
            f"{json.dumps(inputs, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def _extract_json_object(content: str) -> Dict[str, Any]:
        text = str(content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()
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
    async def _request_completion(prompt: str) -> str:
        token = settings.DEEPSEEK_TOKEN.strip()
        if not token:
            raise ValueError("DEEPSEEK_TOKEN is not configured")

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                settings.DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "temperature": 0.15,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты аккуратный классификатор входящих писем для CRM климатической компании.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            if response.status_code == 401:
                raise ValueError("DeepSeek отклонил API ключ. Проверьте DEEPSEEK_TOKEN в .env и перезапустите app-контейнер.")
            if response.status_code == 403:
                raise ValueError("DeepSeek запретил доступ для этого API ключа. Проверьте права ключа и баланс аккаунта.")
            if response.status_code >= 400:
                detail = EmailLeadIntakeService._deepseek_error_message(response)
                raise ValueError(f"DeepSeek вернул ошибку {response.status_code}: {detail}")
            data = response.json()

        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("AI response has unexpected format") from exc

    @staticmethod
    async def classify_email(
        *,
        sender_email: str,
        sender_name: Optional[str],
        subject: str,
        raw_body: str,
        email_date_raw: Optional[str] = None,
    ) -> Dict[str, Any]:
        prompt = EmailLeadIntakeService.build_prompt(
            sender_email=sender_email,
            sender_name=sender_name,
            subject=subject,
            raw_body=raw_body,
            email_date_raw=email_date_raw,
        )
        content = await EmailLeadIntakeService._request_completion(prompt)
        return EmailLeadIntakeService._extract_json_object(content)

    @staticmethod
    def _clean_optional(value: Any, *, max_length: int = 500) -> Optional[str]:
        text = EmailLeadIntakeService.normalize_text(str(value or ""), max_length=max_length)
        return text or None

    @staticmethod
    def _safe_segment(value: Any, *, inn: Optional[str]) -> str:
        if inn:
            return "b2b"
        raw = str(value or "").strip().lower()
        if raw in {"b2b", "b2c", "unknown"}:
            return raw
        return "unknown"

    @staticmethod
    def _looks_like_technical_sender(sender_email: str) -> bool:
        local = str(sender_email or "").split("@", 1)[0].strip().lower()
        return local in {"no-reply", "noreply", "robot", "mailer", "admin"}

    @staticmethod
    def _fallback_request_text(*, subject: str, sender_email: str, raw_body: str) -> str:
        body = EmailLeadIntakeService.normalize_text(raw_body, max_length=1200)
        subject_text = EmailLeadIntakeService.normalize_text(subject, max_length=300)
        return f"Письмо: {subject_text}\nОт: {sender_email}\n\n{body}".strip()

    @staticmethod
    def _email_date_text(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed.isoformat(timespec="minutes")

    @staticmethod
    async def process_email(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        sender_email: str,
        sender_name: Optional[str],
        subject: str,
        raw_body: str,
        message_id: Optional[str] = None,
        email_date_raw: Optional[str] = None,
        dry_run: bool = False,
    ) -> EmailLeadProcessResult:
        clean_message_id = (message_id or "").strip() or None
        fingerprint = EmailLeadIntakeService.build_fingerprint(
            sender_email=sender_email,
            subject=subject,
            raw_body=raw_body,
            message_id=clean_message_id,
            email_date_raw=email_date_raw,
        )

        duplicate = await EmailLeadIntakeService._find_duplicate_order(
            session,
            tenant_scope=tenant_scope,
            message_id=clean_message_id,
            fingerprint=fingerprint,
        )
        if duplicate:
            return EmailLeadProcessResult(
                status="duplicate",
                is_candidate=True,
                order_id=int(duplicate.id or 0),
                reason="duplicate_email",
            )

        is_candidate = EmailLeadIntakeService.looks_like_lead_candidate(
            sender_email=sender_email,
            subject=subject,
            raw_body=raw_body,
        )
        if not is_candidate:
            return EmailLeadProcessResult(status="filtered", is_candidate=False, reason="keyword_filter")

        classification = await EmailLeadIntakeService.classify_email(
            sender_email=sender_email,
            sender_name=sender_name,
            subject=subject,
            raw_body=raw_body,
            email_date_raw=email_date_raw,
        )
        if not bool(classification.get("is_potential_order")):
            return EmailLeadProcessResult(
                status="rejected",
                is_candidate=True,
                used_ai=True,
                reason=EmailLeadIntakeService._clean_optional(classification.get("reason"), max_length=300),
            )

        inn = EmailLeadIntakeService._clean_optional(classification.get("inn"), max_length=50)
        email_value = EmailLeadIntakeService._clean_optional(classification.get("email"), max_length=120)
        if not email_value and not EmailLeadIntakeService._looks_like_technical_sender(sender_email):
            email_value = EmailLeadIntakeService._clean_optional(sender_email, max_length=120)

        name = EmailLeadIntakeService._clean_optional(classification.get("name"), max_length=160)
        if not name and sender_name and not EmailLeadIntakeService._looks_like_technical_sender(sender_email):
            name = EmailLeadIntakeService._clean_optional(sender_name, max_length=160)

        request_text = EmailLeadIntakeService._clean_optional(classification.get("request_text"), max_length=1800)
        if not request_text:
            request_text = EmailLeadIntakeService._fallback_request_text(
                subject=subject,
                sender_email=sender_email,
                raw_body=raw_body,
            )
        email_date = EmailLeadIntakeService._email_date_text(email_date_raw)
        if email_date:
            request_text = f"{request_text}\n\nДата письма: {email_date}"
        request_text = f"{request_text}\n\nТема письма: {subject}".strip()

        if dry_run:
            return EmailLeadProcessResult(
                status="would_create",
                is_candidate=True,
                used_ai=True,
                reason=EmailLeadIntakeService._clean_optional(classification.get("reason"), max_length=300),
            )

        company_name = EmailLeadIntakeService._clean_optional(classification.get("company_name"), max_length=220)
        segment_hint = EmailLeadIntakeService._safe_segment(classification.get("segment_hint"), inn=inn)
        phone = EmailLeadIntakeService._clean_optional(classification.get("phone"), max_length=80)
        customer_type = "company" if segment_hint == "b2b" or inn or company_name else "individual"
        customer_name = company_name or name or email_value or "Email-лид"
        order = await OrderService.create_from_website(
            session=session,
            customer_name=customer_name,
            customer_phone=phone or "",
            customer_email=email_value,
            customer_address=None,
            items=[],
            lead_source=LeadSource.EMAIL,
            initial_status=OrderStatus.NEW_LEAD,
            comment=request_text,
            customer_type=customer_type,
            customer_inn=inn,
            customer_full_legal_name=company_name if customer_type == "company" else None,
            tenant_scope=tenant_scope,
        )

        from sqlalchemy.orm.attributes import flag_modified

        order.technical_meta = dict(order.technical_meta or {})
        order.technical_meta.update(
            {
                "email_source_message_id": clean_message_id,
                "email_source_fingerprint": fingerprint,
                "email_sender": sender_email,
                "email_subject": subject,
                "email_date": email_date,
                "email_ai_reason": EmailLeadIntakeService._clean_optional(classification.get("reason"), max_length=300),
                "lead_customer_type_known": segment_hint in {"b2b", "b2c"} or bool(inn or company_name),
                "lead_customer_type": customer_type if segment_hint in {"b2b", "b2c"} or inn or company_name else None,
            }
        )
        flag_modified(order, "technical_meta")
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return EmailLeadProcessResult(
            status="created",
            is_candidate=True,
            used_ai=True,
            order_id=int(order.id or 0),
            reason=EmailLeadIntakeService._clean_optional(classification.get("reason"), max_length=300),
        )

    @staticmethod
    def _deepseek_error_message(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text[:300]
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            if message:
                return message[:300]
        return str(data)[:300]
