"""HTTP-backed staff access provider for the autonomous bot runtime."""

from api_contracts.bot import BotStaffContextResponse

from .access import BotAccessContext, BotAccessUnavailableError
from .api_gateway import BotApiError, BotApiGateway


def _normalize_telegram_id(value: int | str | None) -> int:
    try:
        normalized = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0
    return normalized if normalized > 0 else 0


def _context_from_response(response: BotStaffContextResponse) -> BotAccessContext:
    return BotAccessContext(
        telegram_id=response.telegram_id,
        is_staff=response.is_staff,
        display_name=response.display_name,
        primary_role=response.primary_role,
        roles=list(response.roles),
        legacy_installer_id=response.legacy_installer_id,
        is_manager=response.is_manager,
        is_executor=response.is_executor,
    )


class ApiBotAccessProvider:
    def __init__(self, gateway: BotApiGateway) -> None:
        self._gateway = gateway

    async def health(self) -> None:
        try:
            await self._gateway.health()
        except BotApiError as exc:
            raise BotAccessUnavailableError("MVN API staff access is unavailable") from exc

    async def get_context(self, telegram_id: int | str | None) -> BotAccessContext:
        normalized_id = _normalize_telegram_id(telegram_id)
        if not normalized_id:
            return BotAccessContext(telegram_id=0)
        try:
            response = await self._gateway.get_staff_context(normalized_id)
        except BotApiError as exc:
            raise BotAccessUnavailableError("MVN API staff access is unavailable") from exc
        return _context_from_response(response)

    async def aclose(self) -> None:
        await self._gateway.aclose()
