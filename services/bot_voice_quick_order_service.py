"""Manager-authorized voice transcription and quick-order parsing."""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BOT_VOICE_MAX_DURATION_SECONDS,
    BOT_VOICE_MAX_FILE_SIZE_BYTES,
)
from core.config import settings
from models import BotVoiceTranscriptionAudit
from services.bot_access_service import BotAccessService
from services.bot_quick_order_api_service import BotQuickOrderApiService
from services.bot_voice_audio_normalizer import (
    BotVoiceAudioValidationError,
    BotVoiceAudioNormalizer,
)
from services.bot_voice_transcription_provider import (
    BotVoiceTranscriptionDisabledError,
    BotVoiceTranscriptionInvalidAudioError,
    BotVoiceTranscriptionProvider,
    BotVoiceTranscriptionProviderError,
    BotVoiceTranscriptionTimeoutError,
)

logger = logging.getLogger(__name__)


class BotVoiceQuickOrderAccessDeniedError(PermissionError):
    pass


class BotVoiceQuickOrderValidationError(ValueError):
    pass


@dataclass(frozen=True)
class BotVoiceQuickOrderResult:
    transcript: str
    draft: dict[str, Any]


class BotVoiceQuickOrderService:
    ALLOWED_MIME_TYPES = {
        "application/ogg",
        "audio/m4a",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/opus",
        "audio/wav",
        "audio/webm",
        "audio/x-m4a",
        "audio/x-wav",
    }

    @classmethod
    def validate_audio(cls, *, content: bytes, mime_type: str) -> str:
        if not content:
            raise BotVoiceQuickOrderValidationError("Uploaded voice file is empty")
        if len(content) > BOT_VOICE_MAX_FILE_SIZE_BYTES:
            raise BotVoiceQuickOrderValidationError("Uploaded voice file is too large")
        normalized_mime = str(mime_type or "").split(";", 1)[0].strip().lower()
        if normalized_mime not in cls.ALLOWED_MIME_TYPES:
            raise BotVoiceQuickOrderValidationError("Unsupported voice MIME type")
        signatures = (
            content.startswith(b"OggS"),
            content.startswith(b"RIFF") and content[8:12] == b"WAVE",
            content.startswith(b"\x1aE\xdf\xa3"),
            content.startswith(b"ID3"),
            len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0,
            len(content) >= 12 and content[4:8] == b"ftyp",
        )
        if not any(signatures):
            raise BotVoiceQuickOrderValidationError(
                "Uploaded file does not match a supported audio format"
            )
        return normalized_mime

    @staticmethod
    async def _require_manager(session: AsyncSession, telegram_id: int) -> None:
        context = await BotAccessService.get_context(session, telegram_id)
        if not context.is_staff or not context.is_manager:
            raise BotVoiceQuickOrderAccessDeniedError(
                "Manager voice quick-order access is required"
            )

    @staticmethod
    async def _mark_failed(
        session: AsyncSession,
        audit: BotVoiceTranscriptionAudit,
        *,
        error_code: str,
    ) -> None:
        audit.status = "failed"
        audit.error_code = error_code[:80]
        audit.completed_at = datetime.now(timezone.utc)
        session.add(audit)
        await session.commit()

    @classmethod
    async def parse_for_manager(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        telegram_chat_id: int,
        telegram_message_id: int,
        duration_seconds: int,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> BotVoiceQuickOrderResult:
        await cls._require_manager(session, telegram_id)
        if duration_seconds < 1 or duration_seconds > BOT_VOICE_MAX_DURATION_SECONDS:
            raise BotVoiceQuickOrderValidationError(
                "Voice duration must be between 1 and 180 seconds"
            )
        normalized_mime = cls.validate_audio(content=content, mime_type=mime_type)
        try:
            normalized_audio = await BotVoiceAudioNormalizer.normalize(
                content=content,
                filename=filename,
                mime_type=normalized_mime,
            )
        except BotVoiceAudioValidationError as exc:
            raise BotVoiceQuickOrderValidationError(str(exc)) from exc
        audit = BotVoiceTranscriptionAudit(
            audit_id=uuid.uuid4().hex,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            status="processing",
            filename=filename[:160],
            mime_type=normalized_mime,
            size_bytes=len(content),
            duration_seconds=duration_seconds,
            detected_duration_ms=round(
                normalized_audio.detected_duration_seconds * 1000
            ),
            request_sha256=hashlib.sha256(content).hexdigest(),
            provider="groq_openai_compatible",
            model=str(settings.BOT_VOICE_TRANSCRIPTION_MODEL or "unknown")[:120],
        )
        session.add(audit)
        await session.commit()

        try:
            transcript = await BotVoiceTranscriptionProvider.transcribe(
                content=normalized_audio.content,
                filename=normalized_audio.filename,
                mime_type=normalized_audio.mime_type,
            )
            draft = await BotQuickOrderApiService.parse_for_manager(
                session,
                telegram_id=telegram_id,
                text=transcript,
            )
        except BotVoiceTranscriptionDisabledError:
            await cls._mark_failed(session, audit, error_code="provider_disabled")
            raise
        except BotVoiceTranscriptionTimeoutError:
            await cls._mark_failed(session, audit, error_code="provider_timeout")
            raise
        except BotVoiceTranscriptionInvalidAudioError:
            await cls._mark_failed(session, audit, error_code="invalid_audio")
            raise
        except BotVoiceTranscriptionProviderError:
            await cls._mark_failed(session, audit, error_code="provider_error")
            raise
        except Exception as exc:
            await cls._mark_failed(session, audit, error_code="quick_order_parse_error")
            logger.exception("Voice quick-order parse failed audit_id=%s", audit.audit_id)
            raise BotVoiceTranscriptionProviderError(
                "Voice quick-order parsing failed"
            ) from exc

        audit.status = "completed"
        audit.transcript_length = len(transcript)
        audit.transcript_sha256 = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
        audit.completed_at = datetime.now(timezone.utc)
        session.add(audit)
        await session.commit()
        return BotVoiceQuickOrderResult(transcript=transcript, draft=draft)
