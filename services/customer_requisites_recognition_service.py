import asyncio
import base64
import json
import logging
import re
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import httpx
from google.oauth2 import service_account
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.input_validation import (
    validate_optional_bic,
    validate_optional_email,
    validate_optional_iban,
    validate_optional_unp,
    validate_optional_phone,
)
from models import Customer, CustomerRequisitesRecognition, CustomerType
from services.customer_service import CustomerService

logger = logging.getLogger(__name__)


class CustomerRequisitesRecognitionService:
    STATUS_RECOGNIZED = "recognized"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"

    MEDIA_DIR = Path("media/customer-requisites")
    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
    MAX_PDF_PAGES = 5

    IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
    PDF_MIME_TYPES = {"application/pdf"}

    CITY_PHONE_CODES = {
        "витебск": "212",
        "минск": "17",
        "гомель": "232",
        "гродно": "152",
        "брест": "162",
        "могилев": "222",
        "могилёв": "222",
    }

    @staticmethod
    def _clean_text(value: Any, *, max_length: int = 2000) -> Optional[str]:
        text = str(value or "").strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_length].strip() or None

    @classmethod
    def _safe_filename(cls, filename: Optional[str], mime_type: Optional[str]) -> str:
        suffix = Path(filename or "").suffix.lower()
        if not suffix:
            suffix = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
                "application/pdf": ".pdf",
            }.get(mime_type or "", ".bin")
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(filename or "requisites").stem).strip(".-") or "requisites"
        return f"{uuid.uuid4().hex}_{stem[:80]}{suffix}"

    @classmethod
    def _store_file(cls, content: bytes, filename: Optional[str], mime_type: Optional[str]) -> tuple[str, str]:
        now = datetime.now()
        directory = cls.MEDIA_DIR / f"{now:%Y}" / f"{now:%m}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / cls._safe_filename(filename, mime_type)
        path.write_bytes(content)
        return str(path), f"/{path.as_posix()}"

    @classmethod
    def _get_vision_client(cls):
        credentials_file = str(settings.GOOGLE_VISION_CREDENTIALS_FILE or "").strip()
        if not credentials_file:
            raise ValueError("GOOGLE_VISION_CREDENTIALS_FILE is not configured")
        creds = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=["https://www.googleapis.com/auth/cloud-vision"],
        )
        return build("vision", "v1", credentials=creds, cache_discovery=False)

    @classmethod
    def _vision_text_from_image_bytes_sync(cls, content: bytes) -> str:
        vision = cls._get_vision_client()
        encoded = base64.b64encode(content).decode("ascii")
        body = {
            "requests": [
                {
                    "image": {"content": encoded},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                    "imageContext": {"languageHints": ["ru", "be", "en"]},
                }
            ]
        }
        response = vision.images().annotate(body=body).execute()
        item = (response.get("responses") or [{}])[0]
        if item.get("error"):
            raise ValueError(f"Google Vision error: {item['error'].get('message') or item['error']}")
        return str((item.get("fullTextAnnotation") or {}).get("text") or "").strip()

    @classmethod
    async def extract_ocr_text(cls, content: bytes, *, mime_type: Optional[str], filename: Optional[str] = None) -> str:
        effective_mime = str(mime_type or "").split(";")[0].strip().lower()
        lower_name = str(filename or "").lower()
        is_pdf = effective_mime in cls.PDF_MIME_TYPES or lower_name.endswith(".pdf")
        if is_pdf:
            text = await asyncio.to_thread(cls._extract_pdf_text, content)
            if len(text.strip()) >= 30:
                return text
            return await asyncio.to_thread(cls._ocr_pdf_pages, content)

        if effective_mime and effective_mime not in cls.IMAGE_MIME_TYPES:
            raise ValueError("Поддерживаются только JPG, PNG, WEBP и PDF")
        return await asyncio.to_thread(cls._vision_text_from_image_bytes_sync, content)

    @staticmethod
    def _extract_pdf_text(content: bytes) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            chunks = []
            for page in reader.pages[: CustomerRequisitesRecognitionService.MAX_PDF_PAGES]:
                chunks.append(page.extract_text() or "")
            return "\n".join(chunks).strip()
        except Exception:
            logger.debug("PDF_TEXT_EXTRACTION_FAILED", exc_info=True)
            return ""

    @classmethod
    def _ocr_pdf_pages(cls, content: bytes) -> str:
        try:
            from pdf2image import convert_from_bytes
        except ImportError as exc:
            raise ValueError("PDF OCR requires pdf2image dependency") from exc

        images = convert_from_bytes(
            content,
            first_page=1,
            last_page=cls.MAX_PDF_PAGES,
            fmt="png",
        )
        chunks: list[str] = []
        for image in images:
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            text = cls._vision_text_from_image_bytes_sync(buffer.getvalue())
            if text:
                chunks.append(text)
        return "\n\n".join(chunks).strip()

    @staticmethod
    def _extract_json_object(content: str) -> dict[str, Any]:
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

    @classmethod
    def build_extraction_prompt(cls, raw_text: str) -> str:
        return (
            "Ты извлекаешь реквизиты белорусской организации/ИП из OCR-текста для CRM.\n"
            "Верни только JSON-объект без markdown. Не выдумывай данные.\n\n"
            "Ключи JSON:\n"
            "name, full_legal_name, inn, legal_address, bank_name, bic, iban, email, phone_raw, "
            "phone, signer_position, signer_name, acting_basis, extra.\n\n"
            "Правила:\n"
            "- inn: только УНП 9 цифр или null.\n"
            "- iban: BY-счет без пробелов или null.\n"
            "- bic: латиница/цифры верхним регистром или null.\n"
            "- signer_position: должность подписанта в родительном падеже: директора, генерального директора, заместителя директора.\n"
            "- signer_name: ФИО подписанта строго в родительном падеже, например Дмитриенко Сергея Александровича.\n"
            "- acting_basis: только основание без слов 'действующий на основании', например Устава, доверенности.\n"
            "- phone_raw: как в документе. phone: нормализованный международный номер только если уверен, иначе null.\n"
            "- extra: положи okpo, bank_address и любые полезные реквизиты, которых нет в основных ключах.\n\n"
            "OCR-текст:\n"
            f"{raw_text[:12000]}"
        )

    @classmethod
    async def extract_requisites(cls, raw_text: str) -> dict[str, Any]:
        token = settings.DEEPSEEK_TOKEN.strip()
        if not token:
            raise ValueError("DEEPSEEK_TOKEN is not configured")

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                settings.DEEPSEEK_API_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "temperature": 0.05,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты аккуратно извлекаешь реквизиты клиентов для CRM и возвращаешь строгий JSON.",
                        },
                        {"role": "user", "content": cls.build_extraction_prompt(raw_text)},
                    ],
                },
            )
            if response.status_code >= 400:
                raise ValueError(f"DeepSeek вернул ошибку {response.status_code}: {response.text[:300]}")
            data = response.json()

        try:
            content = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("AI response has unexpected format") from exc
        return cls._extract_json_object(content)

    @classmethod
    def _normalize_signer_position(cls, value: Optional[str]) -> Optional[str]:
        text = cls._clean_text(value, max_length=120)
        if not text:
            return None
        lowered = text.strip().lower()
        mapping = {
            "директор": "директора",
            "директора": "директора",
            "генеральный директор": "генерального директора",
            "генерального директора": "генерального директора",
            "заместитель директора": "заместителя директора",
            "заместителя директора": "заместителя директора",
        }
        return mapping.get(lowered, lowered)

    @classmethod
    def _normalize_acting_basis(cls, value: Optional[str]) -> Optional[str]:
        text = cls._clean_text(value, max_length=160)
        if not text:
            return "Устава"
        text = re.sub(r"(?i)\bдействующ(ий|ая|его|егося)\b", "", text)
        text = re.sub(r"(?i)\bна\s+основании\b", "", text)
        text = re.sub(r"[.,]+$", "", text).strip()
        return text[:1].upper() + text[1:] if text else "Устава"

    @classmethod
    def normalize_phone(cls, phone_raw: Optional[str], context: str = "") -> Optional[str]:
        raw = cls._clean_text(phone_raw, max_length=80)
        if not raw:
            return None
        digits = re.sub(r"\D", "", raw)
        if not digits:
            return None

        if digits.startswith("375") or digits.startswith("80") or digits.startswith("0") or len(digits) == 9:
            try:
                return validate_optional_phone(raw)
            except ValueError:
                pass

        context_lower = context.casefold()
        for city, code in cls.CITY_PHONE_CODES.items():
            if city in context_lower and len(digits) in {5, 6, 7}:
                candidate = f"+375{code}{digits}"
                try:
                    return validate_optional_phone(candidate)
                except ValueError:
                    return None
        return None

    @classmethod
    def _normalize_extracted(cls, raw: dict[str, Any], raw_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
        extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
        data = {
            "name": cls._clean_text(raw.get("name") or raw.get("full_legal_name"), max_length=500),
            "full_legal_name": cls._clean_text(raw.get("full_legal_name") or raw.get("name"), max_length=500),
            "inn": cls._clean_text(raw.get("inn"), max_length=32),
            "legal_address": cls._clean_text(raw.get("legal_address"), max_length=1000),
            "bank_name": cls._clean_text(raw.get("bank_name"), max_length=500),
            "bic": cls._clean_text(raw.get("bic"), max_length=32),
            "iban": cls._clean_text(raw.get("iban"), max_length=64),
            "email": cls._clean_text(raw.get("email"), max_length=255),
            "phone_raw": cls._clean_text(raw.get("phone_raw") or raw.get("phone"), max_length=120),
            "signer_position": cls._normalize_signer_position(raw.get("signer_position")) or "директора",
            "signer_name": cls._clean_text(raw.get("signer_name"), max_length=255),
            "acting_basis": cls._normalize_acting_basis(raw.get("acting_basis")),
            "extra": extra,
        }
        data["phone"] = cls.normalize_phone(
            cls._clean_text(raw.get("phone") or data.get("phone_raw"), max_length=120),
            context=" ".join(filter(None, [raw_text, str(data.get("legal_address") or "")])),
        )

        field_errors: dict[str, str] = {}
        warnings: dict[str, str] = {}

        if not data["name"]:
            field_errors["name"] = "Название клиента не распознано"

        for field, validator in (
            ("inn", validate_optional_unp),
            ("iban", validate_optional_iban),
            ("bic", validate_optional_bic),
            ("email", validate_optional_email),
        ):
            value = data.get(field)
            if not value:
                continue
            try:
                data[field] = validator(value)
            except ValueError as exc:
                field_errors[field] = str(exc)

        if data.get("phone_raw") and not data.get("phone"):
            warnings["phone"] = "Телефон сохранен только в OCR JSON: не удалось уверенно нормализовать"

        return data, {"field_errors": field_errors, "warnings": warnings, "is_valid": not field_errors}

    @staticmethod
    async def _find_duplicate(session: AsyncSession, inn: Optional[str]) -> Optional[Customer]:
        if not inn:
            return None
        result = await session.execute(select(Customer).where(Customer.inn == inn).order_by(Customer.id.asc()).limit(1))
        return result.scalars().first()

    @staticmethod
    def _duplicate_brief(customer: Optional[Customer]) -> Optional[dict[str, Any]]:
        if not customer:
            return None
        return {
            "id": int(customer.id or 0),
            "name": customer.name,
            "inn": customer.inn,
            "phone": customer.phone,
            "email": customer.email,
        }

    @classmethod
    def _recognition_response(cls, recognition: CustomerRequisitesRecognition, duplicate: Optional[Customer]) -> dict[str, Any]:
        return {
            "id": int(recognition.id or 0),
            "status": recognition.status,
            "source": recognition.source,
            "raw_text": recognition.raw_text,
            "extracted": recognition.extracted_json or {},
            "validation_flags": recognition.validation_flags or {},
            "duplicate_customer": cls._duplicate_brief(duplicate),
            "confirmed_customer_id": recognition.confirmed_customer_id,
            "confirmed_action": recognition.confirmed_action,
            "local_file_url": recognition.local_file_url,
            "created_at": recognition.created_at,
        }

    @classmethod
    async def recognize_bytes(
        cls,
        session: AsyncSession,
        *,
        content: bytes,
        filename: Optional[str],
        mime_type: Optional[str],
        source: str,
        telegram_user_id: Optional[int] = None,
        telegram_chat_id: Optional[int] = None,
        telegram_message_id: Optional[int] = None,
    ) -> dict[str, Any]:
        if not content:
            raise ValueError("Файл пустой")
        if len(content) > cls.MAX_FILE_SIZE_BYTES:
            raise ValueError("Файл слишком большой. Максимальный размер: 10 МБ")

        raw_text = await cls.extract_ocr_text(content, mime_type=mime_type, filename=filename)
        if not raw_text.strip():
            raise ValueError("Не удалось распознать текст в файле")
        extracted_raw = await cls.extract_requisites(raw_text)
        extracted, validation_flags = cls._normalize_extracted(extracted_raw, raw_text)
        duplicate = await cls._find_duplicate(session, extracted.get("inn"))
        local_path, local_url = cls._store_file(content, filename, mime_type)

        recognition = CustomerRequisitesRecognition(
            source=source,
            status=cls.STATUS_RECOGNIZED,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            original_filename=filename,
            mime_type=mime_type,
            local_file_path=local_path,
            local_file_url=local_url,
            raw_text=raw_text,
            extracted_json=extracted,
            validation_flags=validation_flags,
            duplicate_customer_id=duplicate.id if duplicate else None,
        )
        session.add(recognition)
        await session.commit()
        await session.refresh(recognition)
        return cls._recognition_response(recognition, duplicate)

    @classmethod
    def _customer_payload(cls, extracted: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": extracted.get("name") or extracted.get("full_legal_name") or "Новый клиент",
            "phone": extracted.get("phone") or "",
            "email": extracted.get("email"),
            "type": CustomerType.company,
            "inn": extracted.get("inn"),
            "full_legal_name": extracted.get("full_legal_name") or extracted.get("name"),
            "legal_address": extracted.get("legal_address"),
            "bank_name": extracted.get("bank_name"),
            "bic": extracted.get("bic"),
            "iban": extracted.get("iban"),
            "signer_position": extracted.get("signer_position") or "директора",
            "signer_name": extracted.get("signer_name"),
            "acting_basis": extracted.get("acting_basis") or "Устава",
        }

    @classmethod
    async def confirm(
        cls,
        session: AsyncSession,
        *,
        recognition_id: int,
        action: str,
        customer_id: Optional[int] = None,
    ) -> dict[str, Any]:
        recognition = await session.get(CustomerRequisitesRecognition, recognition_id)
        if not recognition:
            raise LookupError("Recognition not found")
        if recognition.status == cls.STATUS_CONFIRMED:
            raise ValueError("Распознавание уже подтверждено")

        validation_flags = recognition.validation_flags or {}
        field_errors = validation_flags.get("field_errors") if isinstance(validation_flags, dict) else {}
        if field_errors:
            raise ValueError("Нельзя создать клиента: исправьте ошибки распознавания")

        extracted = recognition.extracted_json or {}
        payload = cls._customer_payload(extracted)
        normalized_action = str(action or "").strip().lower()

        if normalized_action == "update":
            target_id = customer_id or recognition.duplicate_customer_id
            if not target_id:
                raise ValueError("Не выбран клиент для обновления")
            customer = await session.get(Customer, int(target_id))
            if not customer:
                raise LookupError("Customer not found")
            for key, value in payload.items():
                if key == "type":
                    setattr(customer, key, CustomerType.company)
                    continue
                if value is not None and value != "":
                    setattr(customer, key, value)
            session.add(customer)
            await session.flush()
        elif normalized_action == "create":
            customer = Customer(**payload)
            session.add(customer)
            await session.flush()
        else:
            raise ValueError("action must be create or update")

        recognition.status = cls.STATUS_CONFIRMED
        recognition.confirmed_action = normalized_action
        recognition.confirmed_customer_id = customer.id
        recognition.confirmed_at = datetime.now()
        session.add(recognition)
        await session.commit()
        await session.refresh(recognition)

        duplicate = await cls._find_duplicate(session, extracted.get("inn"))
        customer_data = await CustomerService.get_for_manager(session=session, customer_id=int(customer.id or 0))
        return {"recognition": cls._recognition_response(recognition, duplicate), "customer": customer_data}

    @classmethod
    async def cancel(cls, session: AsyncSession, *, recognition_id: int) -> dict[str, Any]:
        recognition = await session.get(CustomerRequisitesRecognition, recognition_id)
        if not recognition:
            raise LookupError("Recognition not found")
        if recognition.status == cls.STATUS_CONFIRMED:
            raise ValueError("Подтвержденное распознавание нельзя отменить")
        recognition.status = cls.STATUS_CANCELLED
        session.add(recognition)
        await session.commit()
        await session.refresh(recognition)
        duplicate = await cls._find_duplicate(session, (recognition.extracted_json or {}).get("inn"))
        return cls._recognition_response(recognition, duplicate)
