import hashlib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import BotVoiceTranscriptionAudit
from services.bot_voice_audio_normalizer import BotNormalizedVoiceAudio
from services.bot_voice_quick_order_service import (
    BotVoiceQuickOrderService,
    BotVoiceQuickOrderValidationError,
)


@pytest.fixture
async def voice_audit_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'voice.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(BotVoiceTranscriptionAudit.__table__.create)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def test_voice_service_rejects_mime_and_content_mismatch():
    with pytest.raises(BotVoiceQuickOrderValidationError):
        BotVoiceQuickOrderService.validate_audio(
            content=b"not-audio",
            mime_type="audio/ogg",
        )

    with pytest.raises(BotVoiceQuickOrderValidationError):
        BotVoiceQuickOrderService.validate_audio(
            content=b"OggSvoice",
            mime_type="image/png",
        )


@pytest.mark.asyncio
async def test_voice_service_audits_success_without_storing_audio_or_transcript(
    monkeypatch,
    voice_audit_session,
):
    monkeypatch.setattr(
        BotVoiceQuickOrderService,
        "_require_manager",
        AsyncMock(return_value=None),
    )
    transcribe = AsyncMock(return_value="Монтаж завтра в 10")
    normalize = AsyncMock(
        return_value=BotNormalizedVoiceAudio(
            content=b"RIFFnormalizedWAVE",
            filename="voice.wav",
            mime_type="audio/wav",
            detected_duration_seconds=12.25,
        )
    )
    parse = AsyncMock(
        return_value={
            "name": None,
            "phone": None,
            "address": None,
            "service_type": "install_only",
            "service_label": "Монтаж",
            "target_date": None,
            "request_text": "Монтаж завтра в 10",
            "parser": "fallback",
            "address_check": None,
        }
    )
    monkeypatch.setattr(
        "services.bot_voice_quick_order_service.BotVoiceAudioNormalizer.normalize",
        normalize,
    )
    monkeypatch.setattr(
        "services.bot_voice_quick_order_service.BotVoiceTranscriptionProvider.transcribe",
        transcribe,
    )
    monkeypatch.setattr(
        "services.bot_voice_quick_order_service.BotQuickOrderApiService.parse_for_manager",
        parse,
    )

    result = await BotVoiceQuickOrderService.parse_for_manager(
        voice_audit_session,
        telegram_id=123,
        telegram_chat_id=-456,
        telegram_message_id=789,
        duration_seconds=12,
        content=b"OggSvoice-bytes",
        filename="voice.ogg",
        mime_type="audio/ogg",
    )

    assert result.transcript == "Монтаж завтра в 10"
    assert result.draft["service_type"] == "install_only"
    audit = (
        await voice_audit_session.execute(select(BotVoiceTranscriptionAudit))
    ).scalar_one()
    assert audit.status == "completed"
    assert audit.request_sha256 == hashlib.sha256(b"OggSvoice-bytes").hexdigest()
    assert audit.transcript_sha256 == hashlib.sha256(
        result.transcript.encode("utf-8")
    ).hexdigest()
    assert audit.transcript_length == len(result.transcript)
    assert audit.detected_duration_ms == 12_250
    assert not hasattr(audit, "raw_audio")
    assert not hasattr(audit, "transcript")


@pytest.mark.asyncio
async def test_voice_service_validates_declared_duration_before_provider(
    monkeypatch,
    voice_audit_session,
):
    monkeypatch.setattr(
        BotVoiceQuickOrderService,
        "_require_manager",
        AsyncMock(return_value=None),
    )
    transcribe = AsyncMock()
    monkeypatch.setattr(
        "services.bot_voice_quick_order_service.BotVoiceTranscriptionProvider.transcribe",
        transcribe,
    )

    with pytest.raises(BotVoiceQuickOrderValidationError):
        await BotVoiceQuickOrderService.parse_for_manager(
            voice_audit_session,
            telegram_id=123,
            telegram_chat_id=-456,
            telegram_message_id=789,
            duration_seconds=181,
            content=b"OggSvoice-bytes",
            filename="voice.ogg",
            mime_type="audio/ogg",
        )

    transcribe.assert_not_awaited()
