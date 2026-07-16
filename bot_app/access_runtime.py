"""Select and own the staff-access provider used by Telegram handlers."""

from core.config import settings

from .access import BotAccessContext, BotAccessProvider
from .access_api import ApiBotAccessProvider
from .api_gateway import BotApiGateway, BotApiGatewayConfig


_provider: BotAccessProvider | None = None


def _build_provider() -> BotAccessProvider:
    if settings.BOT_ACCESS_BACKEND == "api":
        return ApiBotAccessProvider(
            BotApiGateway(
                BotApiGatewayConfig(
                    base_url=settings.BOT_API_BASE_URL,
                    token=settings.BOT_API_TOKEN,
                    timeout_seconds=settings.BOT_API_TIMEOUT_SECONDS,
                )
            )
        )

    if settings.BOT_ACCESS_BACKEND == "database":
        # Import the temporary adapter only when explicit rollback mode is selected.
        from .access_database import DatabaseBotAccessProvider

        return DatabaseBotAccessProvider()

    raise RuntimeError(f"Unsupported bot access backend: {settings.BOT_ACCESS_BACKEND}")


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
