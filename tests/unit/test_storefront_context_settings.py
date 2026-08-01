import pytest
from pydantic import ValidationError

from core.config import Settings


_PRIMARY_SECRET = "primary-storefront-secret-at-least-32-bytes"
_PREVIOUS_SECRET = "previous-storefront-secret-at-least-32-bytes"


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_primary_storefront_signing_key_requires_complete_pair():
    with pytest.raises(ValidationError, match="must be configured together"):
        _settings(
            STOREFRONT_CONTEXT_SIGNING_KEY_ID="mvn-web-current",
            STOREFRONT_CONTEXT_SIGNING_SECRET="",
        )


def test_previous_storefront_key_requires_primary_pair():
    with pytest.raises(ValidationError, match="requires a configured primary"):
        _settings(
            STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID="mvn-web-previous",
            STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET=_PREVIOUS_SECRET,
        )


def test_rotation_key_ids_must_be_distinct():
    with pytest.raises(ValidationError, match="key IDs must differ"):
        _settings(
            STOREFRONT_CONTEXT_SIGNING_KEY_ID="mvn-web-current",
            STOREFRONT_CONTEXT_SIGNING_SECRET=_PRIMARY_SECRET,
            STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID="mvn-web-current",
            STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET=_PREVIOUS_SECRET,
        )


def test_require_signed_switch_needs_primary_key_at_startup():
    with pytest.raises(
        ValidationError,
        match="cannot be required without a primary signing key",
    ):
        _settings(STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=True)


@pytest.mark.parametrize("value", [1023, 64 * 1024 * 1024 + 1])
def test_signed_body_buffer_must_remain_bounded(value):
    with pytest.raises(ValidationError, match="between 1 KiB and 64 MiB"):
        _settings(STOREFRONT_CONTEXT_MAX_BODY_BYTES=value)


def test_complete_rotation_keyring_is_accepted():
    configured = _settings(
        STOREFRONT_CONTEXT_SIGNING_KEY_ID="mvn-web-current",
        STOREFRONT_CONTEXT_SIGNING_SECRET=_PRIMARY_SECRET,
        STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID="mvn-web-previous",
        STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET=_PREVIOUS_SECRET,
        STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=True,
        STOREFRONT_CONTEXT_API_HOSTS="api.mvn.by,api.internal.mvn.by",
    )

    assert configured.storefront_context_api_hosts == (
        "api.mvn.by",
        "api.internal.mvn.by",
    )
