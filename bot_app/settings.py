"""Environment-only settings owned by the autonomous Telegram runtime."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RuntimeControlDecision:
    enabled: bool
    reason: str


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_bool(name: str) -> bool | None:
    return _bool(name) if os.getenv(name) is not None else None


class BotSettings:
    def __init__(self) -> None:
        self.BOT_TOKEN = os.getenv("BOT_TOKEN", "")
        self.BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "")
        self.BOT_API_BASE_URL = os.getenv(
            "BOT_API_BASE_URL", "http://app:8000/api/internal/bot/v1"
        )
        self.BOT_API_TIMEOUT_SECONDS = float(os.getenv("BOT_API_TIMEOUT_SECONDS", "5"))
        self.BOT_ENABLED = _optional_bool("BOT_ENABLED")
        self.BOT_DROP_PENDING_UPDATES = _bool("BOT_DROP_PENDING_UPDATES")
        self.APP_ROLE = os.getenv("APP_ROLE", "primary")
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
        self.PUBLIC_SITE_URL = os.getenv("PUBLIC_SITE_URL", "https://mvn.by")
        self.BOT_RUNTIME_LEASE_SECONDS = int(os.getenv("BOT_RUNTIME_LEASE_SECONDS", "45"))
        self.BOT_RUNTIME_RENEW_SECONDS = int(os.getenv("BOT_RUNTIME_RENEW_SECONDS", "15"))
        self.BOT_RUNTIME_RETRY_SECONDS = int(os.getenv("BOT_RUNTIME_RETRY_SECONDS", "5"))
        if not 15 <= self.BOT_RUNTIME_LEASE_SECONDS <= 300:
            raise ValueError("BOT_RUNTIME_LEASE_SECONDS must be between 15 and 300")
        if not 1 <= self.BOT_RUNTIME_RENEW_SECONDS < self.BOT_RUNTIME_LEASE_SECONDS:
            raise ValueError("BOT_RUNTIME_RENEW_SECONDS must be shorter than the lease")
        if self.BOT_RUNTIME_RETRY_SECONDS < 1:
            raise ValueError("BOT_RUNTIME_RETRY_SECONDS must be positive")
        parsed_api_url = urlsplit(self.BOT_API_BASE_URL.strip())
        if self.ENVIRONMENT == "production":
            if parsed_api_url.scheme != "https":
                raise ValueError("Production bot API access requires HTTPS")
            if parsed_api_url.hostname in {"app", "app-blue", "app-green"}:
                raise ValueError("Production bot API access requires a stable host")

    @property
    def bot_control_decision(self) -> RuntimeControlDecision:
        if self.BOT_ENABLED is not None:
            state = "true" if self.BOT_ENABLED else "false"
            return RuntimeControlDecision(
                enabled=self.BOT_ENABLED,
                reason=f"BOT_ENABLED={state} explicitly controls Telegram polling",
            )
        role = (self.APP_ROLE or "primary").strip().lower()
        if role in {"primary", "active"}:
            return RuntimeControlDecision(True, f"APP_ROLE={role} allows Telegram polling")
        return RuntimeControlDecision(False, f"APP_ROLE={role} disables Telegram polling")


settings = BotSettings()
