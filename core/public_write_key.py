from __future__ import annotations

import hashlib
import re


IDEMPOTENCY_KEY_MIN_LENGTH = 16
IDEMPOTENCY_KEY_MAX_LENGTH = 128
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")


def normalize_public_write_idempotency_key(value: str) -> str:
    key = str(value or "").strip()
    if not IDEMPOTENCY_KEY_MIN_LENGTH <= len(key) <= IDEMPOTENCY_KEY_MAX_LENGTH:
        raise ValueError(
            "Idempotency-Key must contain between "
            f"{IDEMPOTENCY_KEY_MIN_LENGTH} and "
            f"{IDEMPOTENCY_KEY_MAX_LENGTH} characters"
        )
    if not _KEY_PATTERN.fullmatch(key):
        raise ValueError("Idempotency-Key contains unsupported characters")
    return key


def public_write_idempotency_key_sha256(value: str) -> str:
    normalized = normalize_public_write_idempotency_key(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
