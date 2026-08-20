from __future__ import annotations

from services.legacy_owner_runtime_credential import LegacyOwnerRuntimeCredential


def test_cross_node_binding_depends_on_challenge_and_credential_not_secret_key(
    monkeypatch,
) -> None:
    challenge = "c" * 64
    monkeypatch.setattr("core.config.settings.ADMIN_USERNAME", "admin")
    monkeypatch.setattr("core.config.settings.ADMIN_PASSWORD", "same-password")
    monkeypatch.setattr("core.config.settings.SECRET_KEY", "node-a-secret")
    node_a = LegacyOwnerRuntimeCredential.load()
    monkeypatch.setattr("core.config.settings.SECRET_KEY", "node-b-secret")
    node_b = LegacyOwnerRuntimeCredential.load()

    assert node_a.binding != node_b.binding
    assert LegacyOwnerRuntimeCredential.bind(
        node_a, challenge=challenge
    ) == LegacyOwnerRuntimeCredential.bind(node_b, challenge=challenge)
    assert LegacyOwnerRuntimeCredential.bind(
        node_a, challenge=challenge
    ) != LegacyOwnerRuntimeCredential.bind(node_b, challenge="d" * 64)

    monkeypatch.setattr("core.config.settings.ADMIN_PASSWORD", "different-password")
    different = LegacyOwnerRuntimeCredential.load()
    assert LegacyOwnerRuntimeCredential.bind(
        node_a, challenge=challenge
    ) != LegacyOwnerRuntimeCredential.bind(different, challenge=challenge)
