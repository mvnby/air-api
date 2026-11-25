"""On-demand, bounded AI drafting from selected tender documents."""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
from time import monotonic
from typing import Any

import httpx

from core.config import settings
from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import SourceObjectDraft
from services.mail_imap_service import MailImapService
from services.deepseek_connection_service import resolve_deepseek_token

MAX_TENDER_TEXT_CHARS = 180000
TenderDraft = tuple[str | None, str | None, list[SourceObjectDraft]]
AnalysisKey = tuple[int, int, int, str, str, bytes]


class TenderAnalysisBusy(RuntimeError):
    pass


class TenderAnalysisReuse:
    """Bounded reuse of automatic analyses within the active API process."""

    TTL_SECONDS = 30 * 60
    MAX_DRAFTS = 32
    MAX_DRAFT_BYTES = 64 * 1024
    MAX_RUNNING = 2
    ANALYSIS_TIMEOUT_SECONDS = 45

    def __init__(self) -> None:
        self._completed: OrderedDict[AnalysisKey, tuple[float, TenderDraft]] = OrderedDict()
        self._running: dict[AnalysisKey, asyncio.Task[TenderDraft]] = {}

    async def analyze(self, raw_text: str, *, scope: TenantScope, order_id: int) -> TenderDraft:
        _validate_text_size(raw_text)
        key = (
            scope.tenant_id, scope.storefront_id, order_id, settings.DEEPSEEK_API_URL,
            settings.DEEPSEEK_MODEL, sha256(raw_text.encode()).digest(),
        )
        cached = self._completed.get(key)
        if cached is not None:
            until, draft = cached
            if until > monotonic():
                self._completed.move_to_end(key)
                return deepcopy(draft)
            self._completed.pop(key)

        task = self._running.get(key)
        if task is None:
            if len(self._running) >= self.MAX_RUNNING:
                raise TenderAnalysisBusy("Разборы ТЗ заняты. Повторите чуть позже.")
            task = asyncio.create_task(asyncio.wait_for(
                analyze_tender_text(raw_text), timeout=self.ANALYSIS_TIMEOUT_SECONDS,
            ))
            self._running[key] = task
            task.add_done_callback(lambda finished: self._remember(key, finished))
        try:
            return deepcopy(await asyncio.shield(task))
        except TimeoutError as exc:
            raise httpx.ReadTimeout("Automatic tender analysis timed out") from exc

    def _remember(self, key: AnalysisKey, task: asyncio.Task[TenderDraft]) -> None:
        self._running.pop(key, None)
        if task.cancelled() or task.exception() is not None:
            return
        draft = task.result()
        summary, equipment, objects = draft
        size = len((summary or "").encode()) + len((equipment or "").encode())
        if size > self.MAX_DRAFT_BYTES:
            return
        for obj in objects:
            size += len(obj.model_dump_json().encode())
            if size > self.MAX_DRAFT_BYTES:
                return
        self._completed[key] = (monotonic() + self.TTL_SECONDS, draft)
        if len(self._completed) > self.MAX_DRAFTS:
            self._completed.popitem(last=False)


automatic_tender_analysis = TenderAnalysisReuse()


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("AI analysis must be a JSON object")
    return value


async def extract_missing_document_text(*, filename: str, mime_type: str, content: bytes) -> tuple[str | None, str | None]:
    """Use the existing bounded parser; never send an unparsed binary to AI."""
    if len(content) > min(int(settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES), 12 * 1024 * 1024):
        return None, "Документ слишком велик для анализа."
    result = await asyncio.to_thread(
        MailImapService._extract_attachment_text_result,
        filename, mime_type, content, max_chars=100000,
    )
    return result.text or None, result.diagnostic or None


def _validate_text_size(raw_text: str) -> None:
    if len(raw_text) > MAX_TENDER_TEXT_CHARS:
        raise ValueError("Выбранные документы превышают лимит анализа. Выберите меньше файлов; текст не будет обрезан.")


async def analyze_tender_text(raw_text: str) -> TenderDraft:
    _validate_text_size(raw_text)
    token = await resolve_deepseek_token()
    if not token:
        raise RuntimeError("AI document analysis is not configured")
    prompt = (
        "Извлеки из текста тендерного документа только подтверждённые факты для черновика CRM. "
        "Верни JSON с ключами work_summary (строка или null), equipment_details (строка или null), "
        "objects (массив объектов: address, equipment: массив brand, model, quantity). "
        "Разделяй каждый явно указанный адрес в отдельный объект. Сохраняй количество единиц по каждому адресу. "
        "Если адрес не указан, сохрани явно названное оборудование с пустым address. "
        "В equipment_details сохрани явно указанные кабинеты/помещения, длины трасс/коммуникаций, "
        "электропитание и условия монтажа. Не распределяй их между моделями или объектами, если связь не указана прямо. "
        "Не выдумывай адреса, модели, количество, цену или клиента. Если не уверен, оставь массив пустым.\n\n"
        f"Текст:\n{raw_text}"
    )
    async with httpx.AsyncClient(timeout=45.0, trust_env=False) as client:
        response = await client.post(
            settings.DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model": settings.DEEPSEEK_MODEL,
                "temperature": 0.05,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "Ты извлекаешь факты из тендерных документов. Отвечай только JSON."},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
    try:
        parsed = _parse_json(str(data["choices"][0]["message"]["content"]))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("AI returned invalid document analysis") from exc
    objects = []
    for item in parsed.get("objects") or []:
        if not isinstance(item, dict):
            continue
        try:
            obj = SourceObjectDraft.model_validate(item)
        except ValueError:
            continue
        if obj.address.strip() or obj.equipment:
            objects.append(obj)
    def clean(value: Any) -> str | None:
        text = " ".join(str(value or "").split())
        return text[:10000] or None
    return clean(parsed.get("work_summary")), clean(parsed.get("equipment_details")), objects
