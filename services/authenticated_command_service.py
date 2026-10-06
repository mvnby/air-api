"""Actor-scoped retries and audit without duplicating domain commands."""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from models.command_audit import CommandAuditEvent
from services.public_write_idempotency_service import (
    PublicWriteCommandOutcome,
    PublicWriteCommandResponse,
    PublicWriteIdempotencyService,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)
logger = logging.getLogger(__name__)


class AuthenticatedCommandService:
    @staticmethod
    async def execute(
        session: AsyncSession,
        *,
        actor: CommandActor,
        command_name: str,
        idempotency_key: str,
        payload: BaseModel | dict[str, Any],
        response_model: type[ResponseT],
        operation: Callable[[], Awaitable[PublicWriteCommandResponse[ResponseT]]],
    ) -> PublicWriteCommandOutcome[ResponseT]:
        if actor.tenant_scope.demo_read_only:
            raise PermissionError("Demo access is read-only")
        client_key = PublicWriteIdempotencyService.normalize_key(idempotency_key)
        # Namespace public receipts by the authenticated actor. Never trust an
        # actor, company or namespace supplied in tool arguments.
        scoped_key = hashlib.sha256(
            f"{actor.staff_user_id}:{client_key}".encode()
        ).hexdigest()
        request = (
            payload.model_dump(mode="json", exclude_unset=True)
            if isinstance(payload, BaseModel)
            else payload
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                request,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        ).hexdigest()

        async def audited_operation() -> PublicWriteCommandResponse[ResponseT]:
            response = await operation()
            session.add(
                CommandAuditEvent(
                    tenant_id=actor.tenant_scope.tenant_id,
                    storefront_id=actor.tenant_scope.storefront_id,
                    staff_user_id=actor.staff_user_id,
                    channel=actor.channel,
                    operation=command_name,
                    request_id=scoped_key,
                    resource_type=response.resource_type,
                    resource_id=response.resource_id,
                )
            )
            await session.flush()
            return response

        try:
            outcome = await PublicWriteIdempotencyService.execute(
                session,
                tenant_scope=actor.tenant_scope,
                command_name=f"authenticated:{command_name}",
                idempotency_key=scoped_key,
                request_fingerprint=fingerprint,
                response_model=response_model,
                operation=audited_operation,
            )
        except Exception as exc:
            logger.info(
                "APPLICATION_COMMAND actor=%s channel=%s tenant=%s storefront=%s operation=%s request=%s result=%s",
                actor.staff_user_id,
                actor.channel,
                actor.tenant_scope.tenant_id,
                actor.tenant_scope.storefront_id,
                command_name,
                scoped_key,
                type(exc).__name__,
            )
            raise
        logger.info(
            "APPLICATION_COMMAND actor=%s channel=%s tenant=%s storefront=%s operation=%s request=%s result=%s",
            actor.staff_user_id,
            actor.channel,
            actor.tenant_scope.tenant_id,
            actor.tenant_scope.storefront_id,
            command_name,
            scoped_key,
            "replayed" if outcome.replayed else "committed",
        )
        return outcome
