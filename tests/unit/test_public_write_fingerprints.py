import hashlib

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from core.public_write_idempotency import get_public_write_idempotency_key
from core.tenant_scope import VerifiedPublicStorefrontRequest
from services.public_write_fingerprint_service import (
    PublicWriteAttachmentFingerprint,
    PublicWriteFingerprintService,
)
from services.public_write_idempotency_service import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    PublicWriteIdempotencyService,
)


class _Payload(BaseModel):
    name: str
    count: int
    tags: list[str]


def _attachment(*, field: str, position: int, content: bytes):
    return PublicWriteAttachmentFingerprint(
        field=field,
        position=position,
        content_hash=hashlib.sha256(content).hexdigest(),
        content_type="image/png",
        size_bytes=len(content),
    )


def test_json_fingerprint_uses_validated_logical_payload() -> None:
    payload = _Payload(name="Анна", count=2, tags=["a", "b"])

    model_digest = PublicWriteFingerprintService.for_payload(payload)
    mapping_digest = PublicWriteFingerprintService.for_payload(
        {"tags": ["a", "b"], "count": 2, "name": "Анна"}
    )

    assert model_digest == mapping_digest
    assert len(model_digest) == 64
    assert "Анна" not in model_digest


def test_multipart_fingerprint_is_boundary_independent_and_order_explicit() -> None:
    payload = _Payload(name="Анна", count=1, tags=[])
    first = _attachment(field="indoor_unit", position=0, content=b"first")
    second = _attachment(field="indoor_unit", position=1, content=b"second")

    digest = PublicWriteFingerprintService.for_multipart(
        payload=payload,
        attachments=[second, first],
    )
    regenerated_boundary_digest = PublicWriteFingerprintService.for_multipart(
        payload=payload,
        attachments=[first, second],
    )
    reordered_files_digest = PublicWriteFingerprintService.for_multipart(
        payload=payload,
        attachments=[
            _attachment(field="indoor_unit", position=0, content=b"second"),
            _attachment(field="indoor_unit", position=1, content=b"first"),
        ],
    )

    assert digest == regenerated_boundary_digest
    assert reordered_files_digest != digest


def test_key_is_bounded_and_only_its_digest_is_persistable() -> None:
    key = "browser-checkout-request-0001"

    assert PublicWriteIdempotencyService.normalize_key(key) == key
    assert PublicWriteIdempotencyService.key_hash(key) == hashlib.sha256(
        key.encode()
    ).hexdigest()

    for invalid in ("short", "x" * (IDEMPOTENCY_KEY_MAX_LENGTH + 1), "bad key value"):
        try:
            PublicWriteIdempotencyService.normalize_key(invalid)
        except ValueError:
            pass
        else:  # pragma: no cover - assertion branch
            raise AssertionError(f"invalid key accepted: {invalid!r}")


@pytest.mark.asyncio
async def test_signed_write_requires_client_idempotency_key() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_public_write_idempotency_key(
            idempotency_key=None,
            verified=VerifiedPublicStorefrontRequest(signed=True),
        )

    assert exc_info.value.status_code == 428


@pytest.mark.asyncio
async def test_unsigned_canonical_transition_uses_non_pii_ephemeral_key() -> None:
    key = await get_public_write_idempotency_key(
        idempotency_key=None,
        verified=VerifiedPublicStorefrontRequest(signed=False),
    )

    assert key.startswith("legacy:")
    assert len(key) == 39
