import asyncio
from unittest.mock import AsyncMock, Mock, patch

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


@pytest.mark.asyncio
@pytest.mark.parametrize("returncode", [0, 1])
async def test_audio_tool_checks_exit_status_without_killing_completed_process(returncode):
    process = Mock(
        returncode=returncode,
        communicate=AsyncMock(return_value=(b"output", b"diagnostics")),
    )
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
        if returncode:
            with pytest.raises(BotVoiceAudioValidationError, match="file is invalid"):
                await BotVoiceAudioNormalizer._run_tool("ffprobe", content=b"audio")
        else:
            assert await BotVoiceAudioNormalizer._run_tool("ffprobe", content=b"audio") == (
                b"output", b"diagnostics"
            )
    process.communicate.assert_awaited_once_with(b"audio")
    process.kill.assert_not_called()


class _BlockedAudioProcess:
    def __init__(self):
        self.returncode = None
        self.started = asyncio.Event()
        self.reaping = asyncio.Event()
        self.release_reap = asyncio.Event()
        self.kill = Mock()

    async def communicate(self, content=None):
        if content is not None:
            self.started.set()
            await asyncio.Event().wait()
        self.reaping.set()
        await self.release_reap.wait()
        self.returncode = -9
        return b"", b""


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", ["cancel", "timeout"])
async def test_audio_tool_kills_and_reaps_child_before_propagating_stop(monkeypatch, stop_reason):
    process = _BlockedAudioProcess()
    monkeypatch.setattr("asyncio.create_subprocess_exec", AsyncMock(return_value=process))
    if stop_reason == "timeout":
        monkeypatch.setattr(BotVoiceAudioNormalizer, "TOOL_TIMEOUT_SECONDS", 0.01)
    task = asyncio.create_task(BotVoiceAudioNormalizer._run_tool("ffmpeg", content=b"audio"))
    try:
        await asyncio.wait_for(process.started.wait(), timeout=1)
        if stop_reason == "cancel":
            task.cancel()
        await asyncio.wait_for(process.reaping.wait(), timeout=1)
        process.kill.assert_called_once_with()
        assert not task.done()
    finally:
        process.release_reap.set()
        if not process.reaping.is_set():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    if stop_reason == "cancel":
        with pytest.raises(asyncio.CancelledError):
            task.result()
    else:
        with pytest.raises(BotVoiceAudioValidationError, match="processing timed out") as error:
            task.result()
        assert isinstance(error.value.__cause__, TimeoutError)
