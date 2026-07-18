"""Validate audio duration and normalize Telegram OGG/Opus for transcription."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from api_contracts.bot import BOT_VOICE_MAX_DURATION_SECONDS


class BotVoiceAudioValidationError(ValueError):
    pass


class BotVoiceAudioToolUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class BotNormalizedVoiceAudio:
    content: bytes
    filename: str
    mime_type: str
    detected_duration_seconds: float


class BotVoiceAudioNormalizer:
    TOOL_TIMEOUT_SECONDS = 12
    CONVERT_MIME_TYPES = {"application/ogg", "audio/ogg", "audio/opus"}

    @classmethod
    async def _run_tool(
        cls,
        *command: str,
        content: bytes,
    ) -> tuple[bytes, bytes]:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise BotVoiceAudioToolUnavailableError(
                "Voice audio processing is unavailable"
            ) from exc
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(content),
                timeout=cls.TOOL_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise BotVoiceAudioValidationError("Voice audio processing timed out") from exc
        if process.returncode != 0:
            raise BotVoiceAudioValidationError("Voice audio file is invalid")
        return stdout, stderr

    @classmethod
    async def _duration_seconds(cls, content: bytes) -> float:
        stdout, _ = await cls._run_tool(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            "pipe:0",
            content=content,
        )
        try:
            duration = float(stdout.decode("ascii").strip())
        except (UnicodeDecodeError, ValueError) as exc:
            raise BotVoiceAudioValidationError(
                "Voice audio duration could not be determined"
            ) from exc
        if duration < 1 or duration > BOT_VOICE_MAX_DURATION_SECONDS + 0.5:
            raise BotVoiceAudioValidationError(
                "Voice duration must be between 1 and 180 seconds"
            )
        return duration

    @classmethod
    async def normalize(
        cls,
        *,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> BotNormalizedVoiceAudio:
        duration = await cls._duration_seconds(content)
        if mime_type not in cls.CONVERT_MIME_TYPES:
            return BotNormalizedVoiceAudio(
                content=content,
                filename=filename,
                mime_type=mime_type,
                detected_duration_seconds=duration,
            )

        converted, _ = await cls._run_tool(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "wav",
            "-ac",
            "1",
            "-ar",
            "16000",
            "pipe:1",
            content=content,
        )
        if not converted.startswith(b"RIFF") or converted[8:12] != b"WAVE":
            raise BotVoiceAudioValidationError("Voice audio conversion failed")
        normalized_name = f"{Path(filename).stem or 'telegram-voice'}.wav"[:160]
        return BotNormalizedVoiceAudio(
            content=converted,
            filename=normalized_name,
            mime_type="audio/wav",
            detected_duration_seconds=duration,
        )
