"""External speech-to-text adapter used only by the API service."""

import asyncio

import httpx

from core.config import settings


class BotVoiceTranscriptionDisabledError(RuntimeError):
    pass


class BotVoiceTranscriptionTimeoutError(TimeoutError):
    pass


class BotVoiceTranscriptionProviderError(RuntimeError):
    pass


class BotVoiceTranscriptionInvalidAudioError(ValueError):
    pass


class BotVoiceTranscriptionProvider:
    @staticmethod
    def _configuration() -> tuple[str, str, str, float]:
        if not settings.BOT_VOICE_TRANSCRIPTION_ENABLED:
            raise BotVoiceTranscriptionDisabledError(
                "Voice transcription is not enabled"
            )
        api_url = str(settings.BOT_VOICE_TRANSCRIPTION_API_URL or "").strip()
        api_key = str(settings.BOT_VOICE_TRANSCRIPTION_API_KEY or "").strip()
        model = str(settings.BOT_VOICE_TRANSCRIPTION_MODEL or "").strip()
        timeout_seconds = float(settings.BOT_VOICE_TRANSCRIPTION_TIMEOUT_SECONDS)
        if not api_url or not api_key or not model:
            raise BotVoiceTranscriptionDisabledError(
                "Voice transcription is not configured"
            )
        if timeout_seconds < 1 or timeout_seconds > 60:
            raise BotVoiceTranscriptionDisabledError(
                "Voice transcription timeout is invalid"
            )
        return api_url, api_key, model, timeout_seconds

    @classmethod
    async def transcribe(
        cls,
        *,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> str:
        api_url, api_key, model, timeout_seconds = cls._configuration()
        try:
            async with asyncio.timeout(timeout_seconds):
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    response = await client.post(
                        api_url,
                        headers={"Authorization": f"Bearer {api_key}"},
                        data={
                            "model": model,
                            "language": "ru",
                            "response_format": "json",
                        },
                        files={"file": (filename, content, mime_type)},
                    )
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise BotVoiceTranscriptionTimeoutError(
                "Voice transcription timed out"
            ) from exc
        except httpx.RequestError as exc:
            raise BotVoiceTranscriptionProviderError(
                "Voice transcription provider is unavailable"
            ) from exc

        if response.status_code in {400, 413, 415, 422}:
            raise BotVoiceTranscriptionInvalidAudioError(
                "Voice transcription provider rejected the audio"
            )
        if response.status_code >= 400:
            raise BotVoiceTranscriptionProviderError(
                "Voice transcription provider is unavailable"
            )
        try:
            transcript = " ".join(str(response.json()["text"]).split())
        except (KeyError, TypeError, ValueError) as exc:
            raise BotVoiceTranscriptionProviderError(
                "Voice transcription provider returned an invalid response"
            ) from exc
        if not transcript:
            raise BotVoiceTranscriptionInvalidAudioError(
                "Voice message does not contain recognizable speech"
            )
        if len(transcript) > 12_000:
            raise BotVoiceTranscriptionProviderError(
                "Voice transcription exceeds the supported length"
            )
        return transcript
