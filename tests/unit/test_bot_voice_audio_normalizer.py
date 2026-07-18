from unittest.mock import AsyncMock, patch

import pytest

from services.bot_voice_audio_normalizer import (
    BotVoiceAudioNormalizer,
    BotVoiceAudioValidationError,
)


@pytest.mark.asyncio
async def test_normalizer_converts_telegram_ogg_to_mono_wav():
    converted = b"RIFF" + b"\0" * 4 + b"WAVE" + b"payload"
    with patch.object(
        BotVoiceAudioNormalizer,
        "_run_tool",
        new=AsyncMock(side_effect=[(b"12.25\n", b""), (converted, b"")]),
    ) as run_tool:
        result = await BotVoiceAudioNormalizer.normalize(
            content=b"OggSvoice",
            filename="voice.ogg",
            mime_type="audio/ogg",
        )

    assert result.content == converted
    assert result.filename == "voice.wav"
    assert result.mime_type == "audio/wav"
    assert result.detected_duration_seconds == 12.25
    assert run_tool.await_count == 2
    assert "ffprobe" in run_tool.await_args_list[0].args
    assert "ffmpeg" in run_tool.await_args_list[1].args


@pytest.mark.asyncio
async def test_normalizer_keeps_supported_non_ogg_audio_unchanged():
    with patch.object(
        BotVoiceAudioNormalizer,
        "_run_tool",
        new=AsyncMock(return_value=(b"2.0\n", b"")),
    ) as run_tool:
        result = await BotVoiceAudioNormalizer.normalize(
            content=b"RIFF0000WAVEpayload",
            filename="voice.wav",
            mime_type="audio/wav",
        )

    assert result.content == b"RIFF0000WAVEpayload"
    assert result.filename == "voice.wav"
    assert result.detected_duration_seconds == 2.0
    assert run_tool.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("reported", [b"0.75\n", b"181.0\n", b"unknown\n"])
async def test_normalizer_rejects_invalid_detected_duration(reported: bytes):
    with patch.object(
        BotVoiceAudioNormalizer,
        "_run_tool",
        new=AsyncMock(return_value=(reported, b"")),
    ):
        with pytest.raises(BotVoiceAudioValidationError):
            await BotVoiceAudioNormalizer.normalize(
                content=b"RIFF0000WAVEpayload",
                filename="voice.wav",
                mime_type="audio/wav",
            )
