"""Durable communications contracts and persistence primitives."""

from services.communications.outbox_service import (
    IntegrationOutboxService,
    OutboxEventConflictError,
)

__all__ = ["IntegrationOutboxService", "OutboxEventConflictError"]
