import json

import httpx
import pytest

from core.config import settings
from services import bot_voice_transcription_provider as speech
from services.bot_voice_audio_normalizer import BotVoiceAudioNormalizer, BotVoiceAudioValidationError
from services.call_drive_provider import CallDriveError, CallDriveProviderFactory, GoogleCallDriveAdapter, MAX_CALL_BYTES
from services.call_recording_audio import normalize_call_audio
from services.call_recording_pipeline import CallRecordingPipeline


@pytest.mark.asyncio
async def test_call_speech_uses_separate_config_when_bot_disabled(monkeypatch):
    monkeypatch.setattr(settings, "BOT_VOICE_TRANSCRIPTION_ENABLED", False)
    monkeypatch.setattr(settings, "CALL_RECORDINGS_TRANSCRIPTION_API_KEY", "test-call-key")
    original = httpx.AsyncClient
    def handler(request):
        assert request.headers["authorization"] == "Bearer test-call-key"
        assert settings.CALL_RECORDINGS_TRANSCRIPTION_MODEL.encode() in request.content
        return httpx.Response(200, json={"text": "Дослать фото"})
    monkeypatch.setattr(speech.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert await CallRecordingPipeline.transcribe(content=b"RIFFaudio", filename="call.wav", mime_type="audio/wav") == "Дослать фото"


@pytest.mark.asyncio
@pytest.mark.parametrize("audio,duration,expected", [(True, 30, True), (False, 30, False), (True, 601, False)])
async def test_samsung_container_uses_audio_probe_instead_of_mime_guess(monkeypatch, audio, duration, expected):
    async def tool(*command, content):
        if command[0] == "ffprobe":
            return json.dumps({"format": {"duration": str(duration)}, "streams": [{"codec_type": "audio" if audio else "video"}]}).encode(), b""
        assert "0:a:0" in command
        return b"RIFF0000WAVEaudio", b""
    monkeypatch.setattr(BotVoiceAudioNormalizer, "_run_tool", tool)
    if expected:
        result = await normalize_call_audio(content=b"Samsung-container", filename="call.m4a", mime_type="video/3gpp")
        assert result.mime_type == "audio/wav" and result.detected_duration_seconds == duration
    else:
        with pytest.raises(BotVoiceAudioValidationError):
            await normalize_call_audio(content=b"Samsung-container", filename="call.m4a", mime_type="video/3gpp")


@pytest.mark.asyncio
async def test_streaming_download_stops_at_byte_cap_and_folder_query_is_bound():
    seen = []
    def handler(request):
        seen.append(request)
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, content=b"x" * (MAX_CALL_BYTES + 1))
        assert "'chosen-folder-000001' in parents" in request.url.params["q"]
        assert request.url.params["pageSize"] == "5"
        return httpx.Response(200, json={"files": [], "nextPageToken": "cursor"})
    adapter = GoogleCallDriveAdapter("test-token", client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.list_recordings("chosen-folder-000001") == ([], "cursor")
    with pytest.raises(CallDriveError, match="10 МБ"):
        await adapter.download_audio("safe-file-00000001")
    assert all(request.headers["authorization"] == "Bearer test-token" for request in seen)


def test_document_grant_cannot_be_reused_for_personal_recordings():
    with pytest.raises(CallDriveError):
        CallDriveProviderFactory._require_drive_file_scope({"scopes": ["https://www.googleapis.com/auth/drive.file"]})
    CallDriveProviderFactory._require_drive_file_scope({"scopes": ["https://www.googleapis.com/auth/drive.readonly"]})
