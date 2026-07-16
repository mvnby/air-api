"""Process-wide MVN API gateway shared by autonomous bot use cases."""

from core.config import settings

from .api_gateway import BotApiGateway, BotApiGatewayConfig


_gateway: BotApiGateway | None = None


def get_bot_api_gateway() -> BotApiGateway:
    global _gateway
    if _gateway is None:
        _gateway = BotApiGateway(
            BotApiGatewayConfig(
                base_url=settings.BOT_API_BASE_URL,
                token=settings.BOT_API_TOKEN,
                timeout_seconds=settings.BOT_API_TIMEOUT_SECONDS,
            )
        )
    return _gateway


async def close_bot_api_gateway() -> None:
    global _gateway
    gateway = _gateway
    _gateway = None
    if gateway is not None:
        await gateway.aclose()
