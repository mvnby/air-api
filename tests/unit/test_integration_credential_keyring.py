from __future__ import annotations

import json

import pytest

from core.config import Settings, settings
from core.integration_credential_keyring import (
    InvalidIntegrationCredentialKeyring,
    build_integration_credential_keyring,
)
from services.analytics_connection_contracts import (
    AnalyticsConnectionError,
    AnalyticsCredentialCipher,
)
from services.document_drive_contracts import (
    DocumentDriveConnectionError,
    DocumentDriveCredentialCipher,
)
from services.integration_credential_rotation_token import (
    IntegrationCredentialRotationBlockedError,
    IntegrationCredentialRotationToken,
)


_ACTIVE_SECRET = "active-integration-master-key-00000001"
_RETAINED_SECRET = "retained-integration-master-key-0001"
_LEGACY_NL = "legacy-nl-secret-at-least-32-bytes"
_LEGACY_BY = "legacy-by-secret-at-least-32-bytes"


def _config(
    *,
    active_key_id: str = "current",
    write_mode: str = "active",
    keys: dict[str, str] | None = None,
    legacy: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "active_key_id": active_key_id,
            "write_mode": write_mode,
            "keys": keys or {"current": _ACTIVE_SECRET},
            "legacy_secret_keys": legacy or [],
        }
    )


def test_keyring_validation_rejects_drift_without_exposing_key_values():
    sensitive = "do-not-print-this-key-material-123456789"
    malformed = json.dumps(
        {
            "active_key_id": "missing",
            "write_mode": "active",
            "keys": {"current": sensitive},
            "legacy_secret_keys": [],
        }
    )

    with pytest.raises(InvalidIntegrationCredentialKeyring) as exc_info:
        build_integration_credential_keyring(malformed)
    assert sensitive not in str(exc_info.value)

    with pytest.raises(ValueError) as settings_error:
        Settings(
            SECRET_KEY="auth-secret-that-must-not-appear-123",
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD="password",
            INTEGRATION_CREDENTIAL_KEYRING_JSON=malformed,
        )
    assert sensitive not in str(settings_error.value)
    assert "auth-secret-that-must-not-appear-123" not in str(settings_error.value)


def test_legacy_rollout_reads_both_node_keys_and_rejects_unretained_writer(monkeypatch):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_CREDENTIAL_KEYRING_JSON",
        _config(write_mode="legacy", legacy=[_LEGACY_NL, _LEGACY_BY]),
    )
    monkeypatch.setattr(settings, "SECRET_KEY", _LEGACY_BY)
    token = AnalyticsCredentialCipher.encrypt(
        {"oauth_token": "by-token"},
        tenant_id=21,
        storefront_id=71,
        provider="yandex_metrika",
    )

    monkeypatch.setattr(settings, "SECRET_KEY", _LEGACY_NL)
    assert AnalyticsCredentialCipher.decrypt(
        token,
        tenant_id=21,
        storefront_id=71,
        provider="yandex_metrika",
    ) == {"oauth_token": "by-token"}

    monkeypatch.setattr(settings, "SECRET_KEY", "unretained-local-secret-at-least-32")
    with pytest.raises(AnalyticsConnectionError) as exc_info:
        AnalyticsCredentialCipher.encrypt(
            {"oauth_token": "must-fail"},
            tenant_id=21,
            storefront_id=71,
            provider="yandex_metrika",
        )
    assert exc_info.value.code == "credential_encryption_unavailable"


def test_active_cipher_is_scope_bound_tamper_evident_and_domain_separated(monkeypatch):
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", _config())
    analytics = AnalyticsCredentialCipher.encrypt(
        {"oauth_token": "analytics-token"},
        tenant_id=21,
        storefront_id=71,
        provider="yandex_metrika",
    )
    assert analytics.startswith("mvn-integrations-v1.current.")
    assert AnalyticsCredentialCipher.decrypt(
        analytics,
        tenant_id=21,
        storefront_id=71,
        provider="yandex_metrika",
    )["oauth_token"] == "analytics-token"

    for changed_scope in (
        {"tenant_id": 22, "storefront_id": 71, "provider": "yandex_metrika"},
        {"tenant_id": 21, "storefront_id": 72, "provider": "yandex_metrika"},
        {"tenant_id": 21, "storefront_id": 71, "provider": "yandex_direct"},
    ):
        with pytest.raises(AnalyticsConnectionError) as scope_error:
            AnalyticsCredentialCipher.decrypt(analytics, **changed_scope)
        assert scope_error.value.code == "credentials_unreadable"

    tampered = analytics[:-1] + ("A" if analytics[-1] != "A" else "B")
    with pytest.raises(AnalyticsConnectionError) as tamper_error:
        AnalyticsCredentialCipher.decrypt(
            tampered,
            tenant_id=21,
            storefront_id=71,
            provider="yandex_metrika",
        )
    assert tamper_error.value.code == "credentials_unreadable"

    with pytest.raises(DocumentDriveConnectionError) as cross_domain:
        DocumentDriveCredentialCipher.decrypt(
            analytics,
            tenant_id=21,
            provider="google_drive",
        )
    assert cross_domain.value.code == "credentials_unreadable"


def test_retained_integration_key_can_read_then_rewrap_to_active(monkeypatch):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_CREDENTIAL_KEYRING_JSON",
        _config(
            active_key_id="old",
            keys={"old": _RETAINED_SECRET},
        ),
    )
    old_token = DocumentDriveCredentialCipher.encrypt(
        {"refresh_token": "drive-token"},
        tenant_id=21,
        provider="google_drive",
    )
    monkeypatch.setattr(
        settings,
        "INTEGRATION_CREDENTIAL_KEYRING_JSON",
        _config(
            active_key_id="current",
            keys={
                "current": _ACTIVE_SECRET,
                "old": _RETAINED_SECRET,
            },
        ),
    )

    payload, decrypted = DocumentDriveCredentialCipher.decrypt_with_source(
        old_token,
        tenant_id=21,
        provider="google_drive",
    )
    assert decrypted.source == "retained"
    current_token = DocumentDriveCredentialCipher.encrypt(
        payload,
        tenant_id=21,
        provider="google_drive",
    )
    _, current = DocumentDriveCredentialCipher.decrypt_with_source(
        current_token,
        tenant_id=21,
        provider="google_drive",
    )
    assert current.source == "active"


def test_contract_mode_does_not_fall_back_to_auth_secret(monkeypatch):
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", "")
    monkeypatch.setattr(settings, "SECRET_KEY", _LEGACY_NL)
    legacy = AnalyticsCredentialCipher.encrypt(
        {"oauth_token": "legacy"},
        tenant_id=21,
        storefront_id=71,
        provider="yandex_metrika",
    )
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", _config())

    with pytest.raises(AnalyticsConnectionError) as exc_info:
        AnalyticsCredentialCipher.decrypt(
            legacy,
            tenant_id=21,
            storefront_id=71,
            provider="yandex_metrika",
        )
    assert exc_info.value.code == "credentials_unreadable"


def test_wrong_active_key_is_unreadable_without_key_material(monkeypatch):
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", _config())
    token = AnalyticsCredentialCipher.encrypt(
        {"oauth_token": "secret-payload"},
        tenant_id=21,
        storefront_id=71,
        provider="yandex_metrika",
    )
    wrong = "wrong-integration-master-key-0000000001"
    monkeypatch.setattr(
        settings,
        "INTEGRATION_CREDENTIAL_KEYRING_JSON",
        _config(keys={"current": wrong}),
    )
    with pytest.raises(AnalyticsConnectionError) as exc_info:
        AnalyticsCredentialCipher.decrypt(
            token,
            tenant_id=21,
            storefront_id=71,
            provider="yandex_metrika",
        )
    assert wrong not in str(exc_info.value)
    assert exc_info.value.code == "credentials_unreadable"


def test_rotation_plan_token_is_bounded_and_key_bound(monkeypatch):
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", _config())
    token = IntegrationCredentialRotationToken.issue(
        plan_digest="a" * 64,
        now=1_000,
        nonce="b" * 32,
    )
    assert IntegrationCredentialRotationToken.verify(
        token,
        now=1_899,
    ).plan_digest == "a" * 64
    with pytest.raises(IntegrationCredentialRotationBlockedError):
        IntegrationCredentialRotationToken.verify(token, now=1_901)

    monkeypatch.setattr(
        settings,
        "INTEGRATION_CREDENTIAL_KEYRING_JSON",
        _config(keys={"current": "different-active-master-key-000000001"}),
    )
    with pytest.raises(IntegrationCredentialRotationBlockedError):
        IntegrationCredentialRotationToken.verify(token, now=1_100)
