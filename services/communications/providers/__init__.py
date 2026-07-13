"""Network provider contracts for durable communication deliveries."""

from services.communications.providers.base import (
    CommunicationDeliveryProvider,
    ProviderDeliveryDisposition,
    ProviderDeliveryResult,
)
from services.communications.providers.telegram import TelegramDeliveryProvider

__all__ = [
    "CommunicationDeliveryProvider",
    "ProviderDeliveryDisposition",
    "ProviderDeliveryResult",
    "TelegramDeliveryProvider",
]
