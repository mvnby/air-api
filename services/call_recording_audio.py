"""Probe actual Samsung containers and extract only their audio track."""

import asyncio
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from services.bot_voice_audio_normalizer import BotNormalizedVoiceAudio, BotVoiceAudioNormalizer, BotVoiceAudioValidationError
from services.call_drive_provider import MAX_CALL_BYTES

MAX_CALL_DURATION_SECONDS = 600
MAX_NORMALIZED_BYTES = 20 * 1024 * 1024


async def normalize_call_audio(*, content: bytes, filename: str, mime_type: str) -> BotNormalizedVoiceAudio:
    if not content or len(content) > MAX_CALL_BYTES:
        raise BotVoiceAudioValidationError("Запись должна быть не больше 10 МБ")
    # A path allows seeking in Samsung MP4/3GPP containers with a trailing moov.
    with TemporaryDirectory(prefix="kitlane-call-") as directory:
        path = Path(directory) / "recording"
        await asyncio.to_thread(path.write_bytes, content)
        raw, _ = await BotVoiceAudioNormalizer._run_tool("ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path), content=b"")
        try:
            data = json.loads(raw)
            duration = float(data["format"]["duration"])
            has_audio = any(stream.get("codec_type") == "audio" for stream in data["streams"])
        except (ValueError, TypeError, KeyError) as exc:
            raise BotVoiceAudioValidationError("Не удалось прочитать аудиодорожку") from exc
        if not has_audio or not math.isfinite(duration) or not 1 <= duration <= MAX_CALL_DURATION_SECONDS:
            raise BotVoiceAudioValidationError("Нужна аудиозапись длительностью от 1 до 600 секунд")
        audio, _ = await BotVoiceAudioNormalizer._run_tool("ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-map", "0:a:0", "-t", str(MAX_CALL_DURATION_SECONDS), "-f", "wav", "-ac", "1", "-ar", "16000", "pipe:1", content=b"")
        if len(audio) > MAX_NORMALIZED_BYTES or not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
            raise BotVoiceAudioValidationError("Не удалось подготовить аудиозапись")
        return BotNormalizedVoiceAudio(audio, "recording.wav", "audio/wav", duration)
