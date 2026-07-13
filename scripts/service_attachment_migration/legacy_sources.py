"""Extract and safely download service attachments from legacy order data."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import mimetypes
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from core.config import settings
from models import Order, OrderWorkStage
from services.service_attachment_presenter import legacy_attachment_source_key
from services.service_attachment_service import ServiceAttachmentService


PHOTO_RE = re.compile(r"^-\s*Фото:\s*(?P<file_id>\S+)\s*$", re.MULTILINE)
DOCUMENT_RE = re.compile(
    r"^-\s*Документ:\s*(?P<filename>.+?)\s*\((?P<file_id>[^()\s]+)\)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class LegacyAttachmentCandidate:
    order_id: int
    file_id: str | None
    filename: str
    mime_type: str
    category: str
    source: str
    captured_at: datetime | None = None
    url: str | None = None
    transcript: str | None = None
    work_stage_id: int | None = None
    equipment_id: int | None = None
    component_id: int | None = None
    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None
    telegram_user_id: int | None = None
    expected_content_hash: str | None = None
    expected_size_bytes: int | None = None
    provenance: tuple[str, ...] = ()

    @property
    def identity(self) -> tuple[int, str, str]:
        source_ref = self.file_id or self.url or self.filename
        if self.telegram_chat_id is not None and self.telegram_message_id is not None:
            source_ref = f"telegram:{self.telegram_chat_id}:{self.telegram_message_id}"
        elif self.work_stage_id is not None:
            source_ref = f"stage:{self.work_stage_id}:{source_ref}"
        return (self.order_id, source_ref, self.category)

    @property
    def legacy_source_key(self) -> str:
        if self.work_stage_id is not None:
            payload = "\x1f".join(str(value) for value in self.identity)
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return legacy_attachment_source_key(
            self.order_id,
            {
                "file_id": self.file_id,
                "url": self.url,
                "filename": self.filename,
                "purpose": self.category,
                "telegram_chat_id": self.telegram_chat_id,
                "telegram_message_id": self.telegram_message_id,
            },
        )


@dataclass
class MigrationStats:
    orders_scanned: int = 0
    attachments_found: int = 0
    attachments_existing: int = 0
    attachments_migrated: int = 0
    attachments_unavailable: int = 0
    attachments_verified: int = 0
    attachments_storage_verified: int = 0
    attachment_duplicates: int = 0
    equipment_links_found: int = 0
    equipment_links_created: int = 0
    equipment_link_conflicts: int = 0
    legacy_coverages_found: int = 0
    legacy_coverages_created: int = 0
    transient_failures: int = 0
    configuration_failures: int = 0
    issues: list[str] = field(default_factory=list)


class AttachmentDownloadError(RuntimeError):
    def __init__(self, message: str, *, transient: bool = False, configuration: bool = False) -> None:
        super().__init__(message)
        self.transient = transient
        self.configuration = configuration


class _RetryableDownload(RuntimeError):
    def __init__(self, message: str, *, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized or None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _sha256(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized.split(":", 1)[1]
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        return None
    return normalized


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _retry_seconds(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(1, min(parsed, 30))


def _role_from_event(value: Any) -> str:
    normalized = str(getattr(value, "value", value) or "").strip().lower()
    if normalized == "maintenance":
        return "maintenance"
    if normalized == "repair":
        return "repair"
    if normalized == "diagnostic":
        return "diagnostic"
    return "other"


def _prefer_text(current: str | None, incoming: str | None, *, generic: set[str] | None = None) -> str | None:
    generic = generic or set()
    if current and current not in generic:
        return current
    return incoming or current


def _merge_candidates(
    current: LegacyAttachmentCandidate,
    incoming: LegacyAttachmentCandidate,
) -> LegacyAttachmentCandidate:
    """Preserve business context when the same legacy file appears in several JSON paths."""

    return LegacyAttachmentCandidate(
        order_id=current.order_id,
        file_id=current.file_id or incoming.file_id,
        filename=_prefer_text(
            current.filename,
            incoming.filename,
            generic={"telegram-file"},
        )
        or "telegram-file",
        mime_type=_prefer_text(
            current.mime_type,
            incoming.mime_type,
            generic={"application/octet-stream"},
        )
        or "application/octet-stream",
        category=current.category,
        source=current.source or incoming.source,
        captured_at=current.captured_at or incoming.captured_at,
        url=current.url or incoming.url,
        transcript=current.transcript or incoming.transcript,
        work_stage_id=current.work_stage_id or incoming.work_stage_id,
        equipment_id=current.equipment_id or incoming.equipment_id,
        component_id=current.component_id or incoming.component_id,
        telegram_chat_id=current.telegram_chat_id or incoming.telegram_chat_id,
        telegram_message_id=current.telegram_message_id or incoming.telegram_message_id,
        telegram_user_id=current.telegram_user_id or incoming.telegram_user_id,
        expected_content_hash=current.expected_content_hash or incoming.expected_content_hash,
        expected_size_bytes=current.expected_size_bytes or incoming.expected_size_bytes,
        provenance=tuple(sorted(set(current.provenance) | set(incoming.provenance))),
    )


def _candidate_from_entry(
    order_id: int,
    entry: dict[str, Any],
    *,
    default_category: str = "other",
    default_source: str = "telegram_bot",
    provenance: str,
) -> LegacyAttachmentCandidate | None:
    file_id = _text(entry.get("file_id"))
    url = _text(entry.get("url"))
    if not file_id and not url:
        return None
    filename = _text(entry.get("filename")) or "telegram-file"
    mime_type = _text(entry.get("mime_type")) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    purpose = _text(entry.get("purpose")) or default_category
    category = "nameplate" if "nameplate" in purpose else default_category
    if purpose in ServiceAttachmentService.CATEGORIES:
        category = purpose
    return LegacyAttachmentCandidate(
        order_id=order_id,
        file_id=file_id,
        filename=filename,
        mime_type=mime_type,
        category=category,
        source=_text(entry.get("source")) or default_source,
        captured_at=_datetime(entry.get("attached_at")),
        url=url,
        transcript=_text(entry.get("raw_text")),
        equipment_id=_int(entry.get("equipment_id")),
        component_id=_int(entry.get("component_id")),
        telegram_chat_id=_int(entry.get("telegram_chat_id")),
        telegram_message_id=_int(entry.get("telegram_message_id")),
        telegram_user_id=_int(entry.get("telegram_user_id")),
        expected_content_hash=_sha256(entry.get("content_hash") or entry.get("sha256")),
        expected_size_bytes=_int(entry.get("size_bytes") or entry.get("file_size")),
        provenance=(provenance,),
    )


def extract_order_candidates(order: Order) -> list[LegacyAttachmentCandidate]:
    meta = _as_dict(order.technical_meta)
    candidates: list[LegacyAttachmentCandidate] = []
    for raw in _as_list(meta.get("telegram_attachments")):
        if isinstance(raw, dict):
            candidate = _candidate_from_entry(
                int(order.id or 0),
                raw,
                provenance="technical_meta.telegram_attachments",
            )
            if candidate:
                candidates.append(candidate)

    repair = _as_dict(meta.get("repair"))
    for raw in _as_list(repair.get("nameplate_recognitions")):
        if isinstance(raw, dict):
            candidate = _candidate_from_entry(
                int(order.id or 0),
                raw,
                default_category="nameplate",
                provenance="technical_meta.repair.nameplate_recognitions",
            )
            if candidate:
                candidates.append(candidate)

    for raw in _as_list(meta.get("warranty_nameplate_recognitions")):
        if isinstance(raw, dict):
            candidate = _candidate_from_entry(
                int(order.id or 0),
                raw,
                default_category="nameplate",
                provenance="technical_meta.warranty_nameplate_recognitions",
            )
            if candidate:
                candidates.append(candidate)

    unique: dict[tuple[int, str, str], LegacyAttachmentCandidate] = {}
    for candidate in candidates:
        current = unique.get(candidate.identity)
        unique[candidate.identity] = candidate if current is None else _merge_candidates(current, candidate)
    return list(unique.values())


def extract_stage_candidates(stage: OrderWorkStage) -> list[LegacyAttachmentCandidate]:
    report = str(stage.installer_report or "")
    result: list[LegacyAttachmentCandidate] = []
    for match in PHOTO_RE.finditer(report):
        result.append(
            LegacyAttachmentCandidate(
                order_id=int(stage.order_id),
                file_id=match.group("file_id"),
                filename=f"stage-{stage.id}-photo.jpg",
                mime_type="image/jpeg",
                category="installation_result",
                source="telegram_bot_stage_report",
                work_stage_id=int(stage.id or 0),
                provenance=(f"order_work_stage:{stage.id}:installer_report",),
            )
        )
    for match in DOCUMENT_RE.finditer(report):
        filename = _text(match.group("filename")) or f"stage-{stage.id}-document"
        result.append(
            LegacyAttachmentCandidate(
                order_id=int(stage.order_id),
                file_id=match.group("file_id"),
                filename=filename,
                mime_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
                category="document",
                source="telegram_bot_stage_report",
                work_stage_id=int(stage.id or 0),
                provenance=(f"order_work_stage:{stage.id}:installer_report",),
            )
        )
    return result


async def _telegram_file_url(client: httpx.AsyncClient, file_id: str) -> str | None:
    token = str(settings.BOT_TOKEN or "").strip()
    if not token or token == "0:disabled-bot-token":
        raise AttachmentDownloadError("BOT_TOKEN is not configured", configuration=True)
    url = f"https://api.telegram.org/bot{token}/getFile"
    for attempt in range(3):
        try:
            response = await client.get(url, params={"file_id": file_id})
        except httpx.HTTPError as exc:
            if attempt == 2:
                raise AttachmentDownloadError(
                    f"Telegram getFile network error ({type(exc).__name__})",
                    transient=True,
                ) from exc
            await asyncio.sleep(2**attempt)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == 2:
                raise AttachmentDownloadError(
                    f"Telegram getFile returned HTTP {response.status_code}",
                    transient=True,
                )
            await asyncio.sleep(_retry_seconds(response.headers.get("Retry-After"), 2**attempt))
            continue
        if response.status_code in {401, 403}:
            raise AttachmentDownloadError(
                f"Telegram getFile authorization failed with HTTP {response.status_code}",
                configuration=True,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AttachmentDownloadError(
                f"Telegram getFile rejected the file with HTTP {response.status_code}"
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise AttachmentDownloadError("Telegram getFile returned invalid JSON") from exc
        if not payload.get("ok", False):
            raise AttachmentDownloadError(
                f"Telegram getFile failed: {_text(payload.get('description')) or 'unknown error'}"
            )
        path = _text(_as_dict(payload.get("result")).get("file_path"))
        if not path:
            raise AttachmentDownloadError("Telegram getFile returned no file path")
        return f"https://api.telegram.org/file/bot{token}/{path}"
    raise AttachmentDownloadError("Telegram getFile retry limit reached", transient=True)


def _configured_legacy_hosts() -> set[str]:
    hosts: set[str] = set()
    for raw in (
        settings.PUBLIC_SITE_URL,
        settings.MEDIA_S3_PUBLIC_BASE_URL,
        settings.PRODUCT_MEDIA_S3_PUBLIC_BASE_URL,
    ):
        try:
            host = urlsplit(str(raw or "").strip()).hostname
        except ValueError:
            host = None
        if host:
            hosts.add(host.casefold())
    return hosts


def _validate_legacy_source_url(raw_url: str, *, telegram: bool = False) -> str:
    value = str(raw_url or "").strip()
    if value.startswith("/"):
        value = urljoin(str(settings.PUBLIC_SITE_URL).rstrip("/") + "/", value.lstrip("/"))
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError as exc:
        raise AttachmentDownloadError("Legacy attachment URL is malformed") from exc
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise AttachmentDownloadError("Legacy attachment URL must be a credential-free HTTPS URL")

    host = parsed.hostname.casefold()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise AttachmentDownloadError("Legacy attachment URL points to a non-public address")

    allowed_hosts = {"api.telegram.org"} if telegram else _configured_legacy_hosts()
    if host not in allowed_hosts:
        raise AttachmentDownloadError("Legacy attachment URL host is not allowlisted")
    if telegram and not parsed.path.startswith("/file/bot"):
        raise AttachmentDownloadError("Telegram attachment URL path is invalid")
    return value


async def _download_once(
    client: httpx.AsyncClient,
    url: str,
    *,
    telegram: bool,
    limit: int,
) -> bytes:
    current_url = _validate_legacy_source_url(url, telegram=telegram)
    for _redirect in range(6):
        async with client.stream("GET", current_url, follow_redirects=False) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = str(response.headers.get("Location") or "").strip()
                if not location:
                    raise AttachmentDownloadError("Attachment redirect has no destination")
                current_url = _validate_legacy_source_url(
                    urljoin(current_url, location),
                    telegram=telegram,
                )
                continue
            if response.status_code == 429 or response.status_code >= 500:
                raise _RetryableDownload(
                    f"Attachment download returned HTTP {response.status_code}",
                    retry_after=_retry_seconds(response.headers.get("Retry-After"), 1),
                )
            try:
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise AttachmentDownloadError(
                    f"Attachment is unavailable (HTTP {response.status_code})"
                ) from exc
            content_length = _int(response.headers.get("Content-Length")) or 0
            if content_length > limit:
                raise AttachmentDownloadError(
                    f"Attachment exceeds {limit} bytes (reported {content_length})"
                )
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > limit:
                    raise AttachmentDownloadError(f"Attachment exceeds {limit} bytes")
            if not content:
                raise AttachmentDownloadError("Attachment download returned an empty file")
            return bytes(content)
    raise AttachmentDownloadError("Attachment redirect limit exceeded")


async def _download_url(
    client: httpx.AsyncClient,
    url: str,
    *,
    telegram: bool,
) -> bytes:
    limit = int(settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES)
    for attempt in range(3):
        try:
            return await _download_once(client, url, telegram=telegram, limit=limit)
        except _RetryableDownload as exc:
            if attempt == 2:
                raise AttachmentDownloadError(str(exc), transient=True) from exc
            await asyncio.sleep(max(exc.retry_after, 2**attempt))
        except AttachmentDownloadError:
            raise
        except httpx.HTTPError as exc:
            if attempt == 2:
                raise AttachmentDownloadError(
                    f"Attachment download network error ({type(exc).__name__})",
                    transient=True,
                ) from exc
            await asyncio.sleep(2**attempt)
    raise AttachmentDownloadError("Attachment download retry limit reached", transient=True)


def _verify_legacy_integrity(content: bytes, candidate: LegacyAttachmentCandidate) -> None:
    if candidate.expected_size_bytes is not None and len(content) != candidate.expected_size_bytes:
        raise AttachmentDownloadError(
            "Attachment size does not match the legacy metadata"
        )
    if (
        candidate.expected_content_hash is not None
        and hashlib.sha256(content).hexdigest() != candidate.expected_content_hash
    ):
        raise AttachmentDownloadError(
            "Attachment SHA-256 does not match the legacy metadata"
        )


async def download_candidate(client: httpx.AsyncClient, candidate: LegacyAttachmentCandidate) -> bytes:
    failures: list[AttachmentDownloadError] = []
    if candidate.url:
        try:
            content = await _download_url(client, candidate.url, telegram=False)
            _verify_legacy_integrity(content, candidate)
            return content
        except AttachmentDownloadError as exc:
            failures.append(exc)

    if candidate.file_id:
        try:
            telegram_url = await _telegram_file_url(client, candidate.file_id)
            if telegram_url:
                content = await _download_url(client, telegram_url, telegram=True)
                _verify_legacy_integrity(content, candidate)
                return content
        except AttachmentDownloadError as exc:
            failures.append(exc)

    if failures:
        transient = any(item.transient for item in failures)
        configuration = any(item.configuration for item in failures)
        raise AttachmentDownloadError(
            "; fallback failed: ".join(str(item) for item in failures),
            transient=transient,
            configuration=configuration,
        )
    raise AttachmentDownloadError("Legacy entry has no downloadable URL or Telegram file_id")
