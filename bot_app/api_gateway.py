"""Typed HTTP gateway from the Telegram runtime to the MVN internal API."""

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from api_contracts.bot import BotApiHealthResponse, BotStaffContextResponse


class BotApiError(RuntimeError):
    """Base error raised by the bot HTTP gateway."""


class BotApiAuthenticationError(BotApiError):
    """The API rejected the bot service credential."""


class BotApiUnavailableError(BotApiError):
    """The API could not be reached or returned a transient server failure."""


class BotApiResponseError(BotApiError):
    """The API returned an unexpected response."""


@dataclass(frozen=True)
class BotApiGatewayConfig:
    base_url: str
    token: str
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        normalized_url = self.base_url.strip().rstrip("/")
        parsed = urlsplit(normalized_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Bot API base URL must be a credential-free HTTP(S) URL")
        if not self.token.strip():
            raise ValueError("Bot API token is required")
        if self.timeout_seconds <= 0:
            raise ValueError("Bot API timeout must be positive")
        object.__setattr__(self, "base_url", normalized_url)
        object.__setattr__(self, "token", self.token.strip())


class BotApiGateway:
    """Small use-case client; bot handlers must not know API transport details."""

    def __init__(
        self,
        config: BotApiGatewayConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient(timeout=config.timeout_seconds)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def health(self) -> BotApiHealthResponse:
        payload = await self._get("health")
        try:
            return BotApiHealthResponse.model_validate(payload)
        except ValueError as exc:
            raise BotApiResponseError("MVN API returned an invalid health contract") from exc

    async def get_staff_context(self, telegram_id: int) -> BotStaffContextResponse:
        if telegram_id <= 0:
            raise ValueError("Telegram ID must be positive")
        payload = await self._get(f"staff/context/{telegram_id}")
        try:
            return BotStaffContextResponse.model_validate(payload)
        except ValueError as exc:
            raise BotApiResponseError("MVN API returned an invalid staff context contract") from exc

    async def _get(self, path: str) -> dict:
        url = f"{self._config.base_url}/{path.lstrip('/')}"
        try:
            response = await self._client.get(
                url,
                headers={"Authorization": f"Bearer {self._config.token}"},
                timeout=self._config.timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise BotApiUnavailableError("MVN API is temporarily unavailable") from exc

        if response.status_code in {401, 403}:
            raise BotApiAuthenticationError("MVN API rejected the bot credential")
        if response.status_code >= 500:
            raise BotApiUnavailableError(f"MVN API returned HTTP {response.status_code}")
        if response.status_code >= 400:
            raise BotApiResponseError(f"MVN API returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise BotApiResponseError("MVN API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise BotApiResponseError("MVN API returned an invalid response body")
        return payload
