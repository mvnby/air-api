"""Private Bot API voice quick-order endpoint."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BOT_VOICE_MAX_DURATION_SECONDS,
    BOT_VOICE_MAX_FILE_SIZE_BYTES,
    BotQuickOrderDraft,
    BotVoiceQuickOrderParseResponse,
)
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services.bot_voice_quick_order_service import (
    BotVoiceQuickOrderAccessDeniedError,
    BotVoiceQuickOrderService,
    BotVoiceQuickOrderValidationError,
)
from services.bot_voice_audio_normalizer import BotVoiceAudioToolUnavailableError
from services.bot_voice_transcription_provider import (
    BotVoiceTranscriptionDisabledError,
    BotVoiceTranscriptionInvalidAudioError,
    BotVoiceTranscriptionProviderError,
    BotVoiceTranscriptionTimeoutError,
)


router = APIRouter(
    prefix="/api/internal/bot/v1",
    tags=["internal bot v1 voice"],
    dependencies=[Depends(require_bot_api_token)],
)


@router.post(
    "/quick-orders/parse-voice",
    response_model=BotVoiceQuickOrderParseResponse,
    operation_id="parse_internal_bot_voice_quick_order_v1",
)
async def parse_internal_bot_voice_quick_order(
    telegram_id: int = Form(ge=1),
    telegram_chat_id: int = Form(),
    telegram_message_id: int = Form(ge=1),
    duration_seconds: int = Form(ge=1, le=BOT_VOICE_MAX_DURATION_SECONDS),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> BotVoiceQuickOrderParseResponse:
    """
    Transcribe a voice upload and parse an editable quick-order draft for an active Manager
    Telegram actor (403 otherwise); no order is created. Audio is limited to 180 seconds and
    8 MB; empty/invalid audio returns 422 and oversize file 413. Disabled transcription or
    unavailable audio tooling returns 503, provider failure 502 and provider timeout 504.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    content = await file.read(BOT_VOICE_MAX_FILE_SIZE_BYTES + 1)
    await file.close()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded voice file is empty",
        )
    if len(content) > BOT_VOICE_MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Uploaded voice file exceeds the 8 MB limit",
        )
    filename = " ".join(str(file.filename or "telegram-voice.ogg").split())[:160]
    try:
        result = await BotVoiceQuickOrderService.parse_for_manager(
            session,
            telegram_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            duration_seconds=duration_seconds,
            content=content,
            filename=filename,
            mime_type=file.content_type or "application/octet-stream",
        )
    except BotVoiceQuickOrderAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (BotVoiceQuickOrderValidationError, BotVoiceTranscriptionInvalidAudioError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except BotVoiceTranscriptionDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except BotVoiceAudioToolUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except BotVoiceTranscriptionTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except BotVoiceTranscriptionProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return BotVoiceQuickOrderParseResponse(
        transcript=result.transcript,
        draft=BotQuickOrderDraft.model_validate(result.draft),
    )
