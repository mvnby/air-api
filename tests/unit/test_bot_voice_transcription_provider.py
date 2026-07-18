import httpx
import pytest

from core.config import settings
from services import bot_voice_transcription_provider as provider_module
from services.bot_voice_transcription_provider import (
    BotVoiceTranscriptionDisabledError,
    BotVoiceTranscriptionInvalidAudioError,
    BotVoiceTranscriptionProvider,
)


@pytest.mark.asyncio
async def test_voice_provider_posts_multipart_and_returns_clean_text(monkeypatch):
    monkeypatch.setattr(settings, "BOT_VOICE_TRANSCRIPTION_ENABLED", True)
    monkeypatch.setattr(settings, "BOT_VOICE_TRANSCRIPTION_API_KEY", "secret")
    monkeypatch.setattr(settings, "BOT_VOICE_TRANSCRIPTION_MODEL", "whisper-1")
    monkeypatch.setattr(
        settings,
        "BOT_VOICE_TRANSCRIPTION_API_URL",
        "https://speech.example.test/v1/audio/transcriptions",
    )
    original_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        assert b'name="model"' in request.content
        assert b"whisper-1" in request.content
        assert b'name="file"; filename="voice.ogg"' in request.content
        return httpx.Response(200, json={"text": "  Монтаж   завтра в 10  "})

    monkeypatch.setattr(
        provider_module.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )

    transcript = await BotVoiceTranscriptionProvider.transcribe(
        content=b"OggSvoice",
        filename="voice.ogg",
        mime_type="audio/ogg",
    )

    assert transcript == "Монтаж завтра в 10"


@pytest.mark.asyncio
async def test_voice_provider_fails_closed_without_configuration(monkeypatch):
    monkeypatch.setattr(settings, "BOT_VOICE_TRANSCRIPTION_ENABLED", False)

    with pytest.raises(BotVoiceTranscriptionDisabledError):
        await BotVoiceTranscriptionProvider.transcribe(
            content=b"OggSvoice",
            filename="voice.ogg",
            mime_type="audio/ogg",
        )


@pytest.mark.asyncio
async def test_voice_provider_maps_rejected_audio_to_safe_error(monkeypatch):
    monkeypatch.setattr(settings, "BOT_VOICE_TRANSCRIPTION_ENABLED", True)
    monkeypatch.setattr(settings, "BOT_VOICE_TRANSCRIPTION_API_KEY", "secret")
    original_client = httpx.AsyncClient

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(415, text="provider-private-error")

    monkeypatch.setattr(
        provider_module.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )

    with pytest.raises(BotVoiceTranscriptionInvalidAudioError) as error:
        await BotVoiceTranscriptionProvider.transcribe(
            content=b"OggSvoice",
            filename="voice.ogg",
            mime_type="audio/ogg",
        )

    assert "provider-private-error" not in str(error.value)
