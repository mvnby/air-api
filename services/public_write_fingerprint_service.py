from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class PublicWriteAttachmentFingerprint:
    field: str
    position: int
    content_hash: str
    content_type: str
    size_bytes: int


class PublicWriteFingerprintService:
    """Build PII-free fingerprints from validated logical request content."""

    @classmethod
    def for_payload(cls, payload: BaseModel | Mapping[str, Any]) -> str:
        return cls._hash({"payload": cls._payload_data(payload)})

    @classmethod
    def for_multipart(
        cls,
        *,
        payload: BaseModel | Mapping[str, Any],
        attachments: Sequence[PublicWriteAttachmentFingerprint],
    ) -> str:
        ordered = sorted(
            attachments,
            key=lambda item: (item.field, item.position),
        )
        return cls._hash(
            {
                "payload": cls._payload_data(payload),
                "attachments": [
                    {
                        "field": item.field,
                        "position": item.position,
                        "content_hash": cls._sha256(item.content_hash),
                        "content_type": str(item.content_type or "")[:100].lower(),
                        "size_bytes": int(item.size_bytes),
                    }
                    for item in ordered
                ],
            }
        )

    @staticmethod
    def _payload_data(payload: BaseModel | Mapping[str, Any]) -> Mapping[str, Any]:
        if isinstance(payload, BaseModel):
            return payload.model_dump(mode="json")
        return dict(payload)

    @staticmethod
    def _sha256(value: str) -> str:
        digest = str(value or "").strip().lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("Attachment content hash must be SHA-256")
        return digest

    @staticmethod
    def _hash(value: Mapping[str, Any]) -> str:
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
