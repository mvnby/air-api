from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from crud.public_write_idempotency import PublicWriteIdempotencyDAO
from models import PublicWriteIdempotency
from services.tenant_scope_service import TenantScope


ResponseT = TypeVar("ResponseT", bound=BaseModel)

IDEMPOTENCY_KEY_MIN_LENGTH = 16
IDEMPOTENCY_KEY_MAX_LENGTH = 128
IDEMPOTENCY_RESPONSE_MAX_BYTES = 16 * 1024
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")


class PublicWriteIdempotencyConflict(ValueError):
    pass


class PublicWriteIdempotencyUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicWriteCommandResponse(Generic[ResponseT]):
    value: ResponseT
    status_code: int = 200
    resource_type: str | None = None
    resource_id: int | None = None


@dataclass(frozen=True)
class PublicWriteCommandOutcome(Generic[ResponseT]):
    value: ResponseT
    status_code: int
    replayed: bool


class PublicWriteIdempotencyService:
    @staticmethod
    def normalize_key(value: str) -> str:
        key = str(value or "").strip()
        if not (
            IDEMPOTENCY_KEY_MIN_LENGTH <= len(key) <= IDEMPOTENCY_KEY_MAX_LENGTH
        ):
            raise ValueError(
                "Idempotency-Key must contain between "
                f"{IDEMPOTENCY_KEY_MIN_LENGTH} and "
                f"{IDEMPOTENCY_KEY_MAX_LENGTH} characters"
            )
        if not _KEY_PATTERN.fullmatch(key):
            raise ValueError("Idempotency-Key contains unsupported characters")
        return key

    @staticmethod
    def key_hash(value: str) -> str:
        return hashlib.sha256(
            PublicWriteIdempotencyService.normalize_key(value).encode("utf-8")
        ).hexdigest()

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        command_name: str,
        idempotency_key: str,
        request_fingerprint: str,
        response_model: type[ResponseT],
        operation: Callable[[], Awaitable[PublicWriteCommandResponse[ResponseT]]],
    ) -> PublicWriteCommandOutcome[ResponseT]:
        normalized_command = cls._normalize_command(command_name)
        normalized_fingerprint = cls._normalize_fingerprint(request_fingerprint)
        key_hash = cls.key_hash(idempotency_key)

        try:
            claimed = await PublicWriteIdempotencyDAO.claim(
                session,
                tenant_scope=tenant_scope,
                command_name=normalized_command,
                key_hash=key_hash,
                request_fingerprint=normalized_fingerprint,
            )
            if claimed is None:
                existing = await PublicWriteIdempotencyDAO.get_by_scope_key(
                    session,
                    tenant_scope=tenant_scope,
                    command_name=normalized_command,
                    key_hash=key_hash,
                )
                outcome = cls._replay(
                    existing,
                    request_fingerprint=normalized_fingerprint,
                    response_model=response_model,
                )
                await session.commit()
                return outcome

            result = await operation()
            cls._complete_receipt(claimed, result)
            session.add(claimed)
            await session.flush()
            await session.commit()
            return PublicWriteCommandOutcome(
                value=result.value,
                status_code=result.status_code,
                replayed=False,
            )
        except Exception:
            await session.rollback()
            raise

    @staticmethod
    def _complete_receipt(
        receipt: PublicWriteIdempotency,
        result: PublicWriteCommandResponse[ResponseT],
    ) -> None:
        body = result.value.model_dump(mode="json")
        encoded = json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > IDEMPOTENCY_RESPONSE_MAX_BYTES:
            raise ValueError("Idempotency response exceeds durable receipt limit")
        status_code = int(result.status_code)
        if not 200 <= status_code < 300:
            raise ValueError("Only successful command responses can be persisted")
        resource_type = str(result.resource_type or "").strip() or None
        if resource_type is not None and len(resource_type) > 40:
            raise ValueError("Idempotency resource type is too long")

        receipt.response_status = status_code
        receipt.response_body = body
        receipt.resource_type = resource_type
        receipt.resource_id = result.resource_id
        receipt.completed_at = datetime.now(timezone.utc)

    @staticmethod
    def _replay(
        receipt: PublicWriteIdempotency | None,
        *,
        request_fingerprint: str,
        response_model: type[ResponseT],
    ) -> PublicWriteCommandOutcome[ResponseT]:
        if receipt is None or receipt.completed_at is None:
            raise PublicWriteIdempotencyUnavailable(
                "Idempotency receipt is temporarily unavailable"
            )
        if receipt.request_fingerprint != request_fingerprint:
            raise PublicWriteIdempotencyConflict(
                "Idempotency-Key was already used with different request content"
            )
        if receipt.response_status is None or receipt.response_body is None:
            raise PublicWriteIdempotencyUnavailable(
                "Idempotency receipt is incomplete"
            )
        return PublicWriteCommandOutcome(
            value=response_model.model_validate(receipt.response_body),
            status_code=receipt.response_status,
            replayed=True,
        )

    @staticmethod
    def _normalize_command(value: str) -> str:
        command = str(value or "").strip()
        if not command or len(command) > 80:
            raise ValueError("Invalid public write command name")
        return command

    @staticmethod
    def _normalize_fingerprint(value: str) -> str:
        digest = str(value or "").strip().lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("Request fingerprint must be SHA-256")
        return digest
