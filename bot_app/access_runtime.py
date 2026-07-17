"""Select and own the staff-access provider used by Telegram handlers."""

from .access import BotAccessContext, BotAccessProvider
from .access_api import ApiBotAccessProvider
from .api_runtime import get_bot_api_gateway


_provider: BotAccessProvider | None = None


def _build_provider() -> BotAccessProvider:
    return ApiBotAccessProvider(
        get_bot_api_gateway(),
        owns_gateway=False,
    )


def get_bot_access_provider() -> BotAccessProvider:
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider


async def get_bot_access_context(telegram_id: int | str | None) -> BotAccessContext:
    return await get_bot_access_provider().get_context(telegram_id)


async def verify_bot_access_startup() -> None:
    await get_bot_access_provider().health()


async def close_bot_access_provider() -> None:
    global _provider
    provider = _provider
    _provider = None
    if provider is not None:
        await provider.aclose()
