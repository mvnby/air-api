from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken


_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_CIPHERTEXT_PREFIX = "mvn-integrations-v1"
_MAX_CONFIG_BYTES = 16 * 1024
_MAX_KEYS = 8
_MAX_LEGACY_KEYS = 8


class InvalidIntegrationCredentialKeyring(ValueError):
    """Raised for invalid secret-bearing configuration without echoing input."""


class IntegrationCredentialUnavailable(ValueError):
    """Raised when no safe integration credential encryption key is configured."""


class IntegrationCredentialUnreadable(ValueError):
    """Raised when authenticated credential ciphertext cannot be decrypted."""


class _DuplicateJsonKey(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IntegrationCredentialKey:
    key_id: str
    secret: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class DecryptedIntegrationCredential:
    plaintext: bytes = field(repr=False)
    source: Literal["active", "retained", "legacy"]
    key_id: str | None


@dataclass(frozen=True, slots=True)
class IntegrationCredentialKeyring:
    active_key_id: str = ""
    write_mode: Literal["legacy", "active"] = "legacy"
    keys: tuple[IntegrationCredentialKey, ...] = ()
    legacy_secret_keys: tuple[bytes, ...] = field(default=(), repr=False)

    @property
    def enabled(self) -> bool:
        return bool(self.keys)

    @property
    def active_key(self) -> IntegrationCredentialKey:
        for key in self.keys:
            if key.key_id == self.active_key_id:
                return key
        raise IntegrationCredentialUnavailable(
            "Integration credential keyring is unavailable"
        )

    def encrypt(self, plaintext: bytes, *, context: bytes) -> str:
        if not self.enabled or self.write_mode != "active":
            raise IntegrationCredentialUnavailable(
                "Integration credential active writes are unavailable"
            )
        active = self.active_key
        token = self._fernet(active.secret, context).encrypt(plaintext).decode("ascii")
        return f"{_CIPHERTEXT_PREFIX}.{active.key_id}.{token}"

    def encrypt_legacy(
        self,
        plaintext: bytes,
        *,
        context: bytes,
        local_legacy_secret: str,
    ) -> str:
        if self.enabled and self.write_mode != "legacy":
            raise IntegrationCredentialUnavailable(
                "Legacy integration credential writes are disabled"
            )
        secret = _normalize_legacy_secret(local_legacy_secret)
        self._require_retained_legacy_write_key(secret)
        return self._fernet(secret, context).encrypt(plaintext).decode("ascii")

    def decrypt(
        self,
        ciphertext: str,
        *,
        context: bytes,
        local_legacy_secret: str | None = None,
    ) -> DecryptedIntegrationCredential:
        normalized = str(ciphertext or "")
        if normalized.startswith(f"{_CIPHERTEXT_PREFIX}."):
            return self._decrypt_versioned(normalized, context=context)

        candidates = list(self.legacy_secret_keys)
        if not self.enabled and local_legacy_secret:
            candidates.append(_normalize_legacy_secret(local_legacy_secret))
        for secret in _unique_secrets(candidates):
            try:
                plaintext = self._fernet(secret, context).decrypt(
                    normalized.encode("ascii")
                )
            except (InvalidToken, UnicodeError, ValueError):
                continue
            return DecryptedIntegrationCredential(
                plaintext=plaintext,
                source="legacy",
                key_id=None,
            )
        raise IntegrationCredentialUnreadable(
            "Integration credential ciphertext is unreadable"
        )

    def fingerprint(self, value: bytes, *, context: bytes) -> str:
        if not self.enabled or self.write_mode != "active":
            raise IntegrationCredentialUnavailable(
                "Integration credential active fingerprinting is unavailable"
            )
        return hmac.new(
            self.active_key.secret,
            context + b"\0" + value,
            hashlib.sha256,
        ).hexdigest()

    def fingerprint_legacy(
        self,
        value: bytes,
        *,
        context: bytes,
        local_legacy_secret: str,
    ) -> str:
        if self.enabled and self.write_mode != "legacy":
            raise IntegrationCredentialUnavailable(
                "Legacy integration credential fingerprinting is disabled"
            )
        secret = _normalize_legacy_secret(local_legacy_secret)
        self._require_retained_legacy_write_key(secret)
        return hmac.new(
            secret,
            context + value,
            hashlib.sha256,
        ).hexdigest()

    def _require_retained_legacy_write_key(self, secret: bytes) -> None:
        if self.enabled and not any(
            hmac.compare_digest(secret, retained)
            for retained in self.legacy_secret_keys
        ):
            raise IntegrationCredentialUnavailable(
                "Local legacy integration credential key is not retained"
            )

    def _decrypt_versioned(
        self,
        ciphertext: str,
        *,
        context: bytes,
    ) -> DecryptedIntegrationCredential:
        if not self.enabled:
            raise IntegrationCredentialUnavailable(
                "Integration credential keyring is unavailable"
            )
        parts = ciphertext.split(".", 2)
        if len(parts) != 3 or not _KEY_ID_PATTERN.fullmatch(parts[1]):
            raise IntegrationCredentialUnreadable(
                "Integration credential ciphertext is unreadable"
            )
        key_id, token = parts[1], parts[2]
        key = next((item for item in self.keys if item.key_id == key_id), None)
        if key is None:
            raise IntegrationCredentialUnreadable(
                "Integration credential ciphertext is unreadable"
            )
        try:
            plaintext = self._fernet(key.secret, context).decrypt(token.encode("ascii"))
        except (InvalidToken, UnicodeError, ValueError) as exc:
            raise IntegrationCredentialUnreadable(
                "Integration credential ciphertext is unreadable"
            ) from exc
        return DecryptedIntegrationCredential(
            plaintext=plaintext,
            source="active" if key_id == self.active_key_id else "retained",
            key_id=key_id,
        )

    @staticmethod
    def _fernet(secret: bytes, context: bytes) -> Fernet:
        derived = hmac.new(secret, context, hashlib.sha256).digest()
        return Fernet(base64.urlsafe_b64encode(derived))


def build_integration_credential_keyring(
    raw_json: str,
) -> IntegrationCredentialKeyring:
    if not raw_json:
        return IntegrationCredentialKeyring()
    if len(raw_json.encode("utf-8")) > _MAX_CONFIG_BYTES:
        raise InvalidIntegrationCredentialKeyring("keyring JSON is too large")
    try:
        payload = json.loads(
            raw_json,
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (json.JSONDecodeError, _DuplicateJsonKey, UnicodeError) as exc:
        raise InvalidIntegrationCredentialKeyring("keyring JSON is invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "active_key_id",
        "write_mode",
        "keys",
        "legacy_secret_keys",
    }:
        raise InvalidIntegrationCredentialKeyring(
            "keyring JSON fields are invalid"
        )
    active_key_id = _normalize_key_id(payload["active_key_id"])
    write_mode = payload["write_mode"]
    if not isinstance(write_mode, str) or write_mode not in {"legacy", "active"}:
        raise InvalidIntegrationCredentialKeyring("write mode is invalid")
    raw_keys = payload["keys"]
    if not isinstance(raw_keys, dict) or not raw_keys or len(raw_keys) > _MAX_KEYS:
        raise InvalidIntegrationCredentialKeyring("integration keys are invalid")
    keys = tuple(
        IntegrationCredentialKey(
            key_id=_normalize_key_id(key_id),
            secret=_normalize_master_secret(secret),
        )
        for key_id, secret in raw_keys.items()
    )
    if active_key_id not in {key.key_id for key in keys}:
        raise InvalidIntegrationCredentialKeyring("active key is missing")
    raw_legacy = payload["legacy_secret_keys"]
    if not isinstance(raw_legacy, list) or len(raw_legacy) > _MAX_LEGACY_KEYS:
        raise InvalidIntegrationCredentialKeyring("legacy keys are invalid")
    legacy = tuple(_normalize_legacy_secret(item) for item in raw_legacy)
    all_secrets = [key.secret for key in keys] + list(legacy)
    if len(_unique_secrets(all_secrets)) != len(all_secrets):
        raise InvalidIntegrationCredentialKeyring("key material must be unique")
    if write_mode == "legacy" and not legacy:
        raise InvalidIntegrationCredentialKeyring(
            "legacy write mode requires legacy read keys"
        )
    return IntegrationCredentialKeyring(
        active_key_id=active_key_id,
        write_mode=write_mode,
        keys=keys,
        legacy_secret_keys=legacy,
    )


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def _normalize_key_id(value: object) -> str:
    if not isinstance(value, str) or not _KEY_ID_PATTERN.fullmatch(value):
        raise InvalidIntegrationCredentialKeyring("key ID is invalid")
    return value


def _normalize_master_secret(value: object) -> bytes:
    if not isinstance(value, str):
        raise InvalidIntegrationCredentialKeyring("integration key is invalid")
    encoded = value.encode("utf-8")
    if len(encoded) < 32 or len(encoded) > 256 or value.strip() != value:
        raise InvalidIntegrationCredentialKeyring("integration key is invalid")
    return encoded


def _normalize_legacy_secret(value: object) -> bytes:
    if not isinstance(value, str):
        raise InvalidIntegrationCredentialKeyring("legacy key is invalid")
    encoded = value.encode("utf-8")
    if len(encoded) < 16 or len(encoded) > 4096:
        raise InvalidIntegrationCredentialKeyring("legacy key is invalid")
    return encoded


def _unique_secrets(values: list[bytes]) -> list[bytes]:
    unique: list[bytes] = []
    for candidate in values:
        if not any(hmac.compare_digest(candidate, existing) for existing in unique):
            unique.append(candidate)
    return unique


__all__ = [
    "DecryptedIntegrationCredential",
    "IntegrationCredentialKeyring",
    "IntegrationCredentialUnavailable",
    "IntegrationCredentialUnreadable",
    "InvalidIntegrationCredentialKeyring",
    "build_integration_credential_keyring",
]
