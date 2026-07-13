from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CommunicationDelivery, IntegrationOutboxEvent
from services.communications.contracts import (
    CommunicationRecipientV1,
    CommunicationTemplatePlanV1,
)


class NoEligibleCommunicationRecipients(RuntimeError):
    pass


class DeliveryMaterializationConflict(ValueError):
    pass


@dataclass(frozen=True)
class DeliveryMaterializationResult:
    delivery_count: int
    created_count: int


class CommunicationDeliveryMaterializer:
    """Persist immutable delivery snapshots without owning the transaction."""

    _DELIVERY_NAMESPACE = uuid.UUID("daebd691-4c30-4f36-8e08-4923c481d486")

    @classmethod
    def build_delivery_id(
        cls,
        *,
        event_id: str,
        channel: str,
        recipient_key: str,
        template_version: int,
    ) -> str:
        canonical_identity = json.dumps(
            [event_id, channel, recipient_key, template_version],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return uuid.uuid5(cls._DELIVERY_NAMESPACE, canonical_identity).hex

    @classmethod
    async def materialize(
        cls,
        session: AsyncSession,
        *,
        event: IntegrationOutboxEvent,
        plan: CommunicationTemplatePlanV1,
        recipients: Sequence[CommunicationRecipientV1],
        now: datetime | None = None,
    ) -> DeliveryMaterializationResult:
        if not recipients:
            raise NoEligibleCommunicationRecipients(
                "No eligible communication recipients are configured"
            )

        recipient_keys = [recipient.recipient_key for recipient in recipients]
        if len(set(recipient_keys)) != len(recipient_keys):
            raise DeliveryMaterializationConflict(
                "Recipient directory returned duplicate recipient keys"
            )

        materialized_at = now or datetime.now(timezone.utc)
        rows = [
            {
                "delivery_id": cls.build_delivery_id(
                    event_id=event.event_id,
                    channel=plan.channel,
                    recipient_key=recipient.recipient_key,
                    template_version=plan.template_version,
                ),
                "event_id": event.event_id,
                "channel": plan.channel,
                "recipient_key": recipient.recipient_key,
                "destination": recipient.destination,
                "template_key": plan.template_key,
                "template_version": plan.template_version,
                "render_context": plan.render_context,
                "status": "queued",
                "priority": max(0, int(event.priority)),
                "attempts": 0,
                "max_attempts": max(1, int(event.max_attempts)),
                "available_at": materialized_at,
                "created_at": materialized_at,
                "updated_at": materialized_at,
            }
            for recipient in recipients
        ]

        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            statement = postgresql_insert(CommunicationDelivery).values(rows)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(CommunicationDelivery).values(rows)
        else:
            raise NotImplementedError(
                f"Atomic delivery materialization is not implemented for {dialect_name!r}"
            )

        created_ids = list(
            (
                await session.execute(
                    # The deterministic primary key and the natural delivery
                    # identity can both win a concurrent race. Ignore either
                    # unique conflict, then re-read and verify the complete
                    # immutable snapshot below.
                    statement.on_conflict_do_nothing().returning(
                        CommunicationDelivery.delivery_id
                    )
                )
            ).scalars()
        )
        existing = list(
            (
                await session.execute(
                    select(CommunicationDelivery).where(
                        CommunicationDelivery.event_id == event.event_id,
                        CommunicationDelivery.channel == plan.channel,
                        CommunicationDelivery.template_version == plan.template_version,
                    )
                )
            ).scalars()
        )
        existing_by_key = {delivery.recipient_key: delivery for delivery in existing}
        if set(existing_by_key) != set(recipient_keys):
            raise DeliveryMaterializationConflict(
                "An immutable event delivery set was reused with different recipients"
            )

        expected_by_key = {row["recipient_key"]: row for row in rows}
        for recipient_key, delivery in existing_by_key.items():
            expected = expected_by_key[recipient_key]
            immutable_snapshot = (
                delivery.delivery_id,
                delivery.destination,
                delivery.template_key,
                delivery.render_context,
                delivery.priority,
                delivery.max_attempts,
            )
            expected_snapshot = (
                expected["delivery_id"],
                expected["destination"],
                expected["template_key"],
                expected["render_context"],
                expected["priority"],
                expected["max_attempts"],
            )
            if immutable_snapshot != expected_snapshot:
                raise DeliveryMaterializationConflict(
                    "An immutable delivery identity was reused with different content"
                )

        return DeliveryMaterializationResult(
            delivery_count=len(existing),
            created_count=len(created_ids),
        )
