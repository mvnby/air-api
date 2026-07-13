from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.communications.canary_run_id import short_canary_run_id
from services.communications.contracts import TelegramCanaryRequestedPayloadV1


TELEGRAM_CANARY_MESSAGE_V1 = (
    "🧪 <b>ПРОВЕРКА КАНАЛА УВЕДОМЛЕНИЙ</b>\n"
    "Системное контрольное сообщение. Ответ не требуется.\n"
    "Запуск: <code>{short_run_id}</code>"
)


def render_telegram_canary_v1(
    context: TelegramCanaryRequestedPayloadV1 | Mapping[str, Any],
) -> str:
    # Validate the routing snapshot before interpolating only the bounded,
    # canonical short run identifier. Arbitrary text is impossible by contract.
    payload = (
        context
        if isinstance(context, TelegramCanaryRequestedPayloadV1)
        else TelegramCanaryRequestedPayloadV1.model_validate(context)
    )
    return TELEGRAM_CANARY_MESSAGE_V1.format(
        short_run_id=short_canary_run_id(payload.run_id)
    )
