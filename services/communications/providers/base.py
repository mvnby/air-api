from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class ProviderDeliveryDisposition(str, Enum):
    SENT = "sent"
    TRANSIENT_FAILURE = "transient_failure"
    PERMANENT_FAILURE = "permanent_failure"
    AMBIGUOUS_FAILURE = "ambiguous_failure"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


@dataclass(frozen=True)
class ProviderDeliveryResult:
    disposition: ProviderDeliveryDisposition
    provider_message_id: str | None = None
    error_category: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_after_seconds: int | None = None

    @classmethod
    def sent(cls, provider_message_id: int | str) -> "ProviderDeliveryResult":
        normalized_message_id = str(provider_message_id or "").strip()
        if not normalized_message_id:
            raise ValueError("Provider message ID is required for a sent delivery")
        return cls(
            disposition=ProviderDeliveryDisposition.SENT,
            provider_message_id=normalized_message_id,
        )

    @classmethod
    def transient_failure(
        cls,
        *,
        category: str,
        code: str,
        message: str,
        retry_after_seconds: int | None = None,
    ) -> "ProviderDeliveryResult":
        return cls(
            disposition=ProviderDeliveryDisposition.TRANSIENT_FAILURE,
            error_category=category,
            error_code=code,
            error_message=message,
            retry_after_seconds=retry_after_seconds,
        )

    @classmethod
    def permanent_failure(
        cls,
        *,
        category: str,
        code: str,
        message: str,
    ) -> "ProviderDeliveryResult":
        return cls(
            disposition=ProviderDeliveryDisposition.PERMANENT_FAILURE,
            error_category=category,
            error_code=code,
            error_message=message,
        )

    @classmethod
    def ambiguous_failure(
        cls,
        *,
        category: str,
        code: str,
        message: str,
    ) -> "ProviderDeliveryResult":
        """Record an outcome that may have crossed the provider boundary."""

        return cls(
            disposition=ProviderDeliveryDisposition.AMBIGUOUS_FAILURE,
            error_category=category,
            error_code=code,
            error_message=message,
        )

    @classmethod
    def provider_unavailable(
        cls,
        *,
        code: str,
        message: str,
        retry_after_seconds: int | None = None,
    ) -> "ProviderDeliveryResult":
        return cls(
            disposition=ProviderDeliveryDisposition.PROVIDER_UNAVAILABLE,
            error_category="provider",
            error_code=code,
            error_message=message,
            retry_after_seconds=retry_after_seconds,
        )


class CommunicationDeliveryProvider(Protocol):
    channel: str

    async def send(
        self,
        *,
        destination: str,
        text: str,
        delivery_id: str,
    ) -> ProviderDeliveryResult: ...

    async def close(self) -> None: ...
