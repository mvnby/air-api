import json

import pytest
from pydantic import ValidationError

from core.config import Settings


_PRIMARY_SECRET = "primary-storefront-secret-at-least-32-bytes"
_PREVIOUS_SECRET = "previous-storefront-secret-at-least-32-bytes"


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _keyring(*entries: tuple[str, str, dict[str, str]]) -> str:
    return json.dumps(
        {
            "keys": {
                key_id: {"secret": secret, "host_roles": host_roles}
                for key_id, secret, host_roles in entries
            }
        },
        separators=(",", ":"),
    )


def test_host_scoped_rotation_keyring_is_accepted():
    configured = _settings(
        STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
            (
                "mvn-web-current",
                _PRIMARY_SECRET,
                {"mvn.by": "primary"},
            ),
            (
                "mvn-web-previous",
                _PREVIOUS_SECRET,
                {"mvn.by": "previous"},
            ),
            (
                "polotsk-web-current",
                "polotsk-storefront-secret-at-least-32-bytes",
                {"polotsk.mvn.by": "primary"},
            ),
        ),
        STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=True,
        STOREFRONT_CONTEXT_API_HOSTS="api.mvn.by,api.internal.mvn.by",
    )

    assert configured.storefront_context_api_hosts == (
        "api.mvn.by",
        "api.internal.mvn.by",
    )
    assert len(configured.storefront_context_signing_keyring.keys) == 3


def test_previous_key_requires_primary_for_same_host():
    with pytest.raises(ValidationError, match="previous key requires a primary"):
        _settings(
            STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
                (
                    "mvn-web-previous",
                    _PREVIOUS_SECRET,
                    {"mvn.by": "previous"},
                )
            )
        )


def test_host_may_not_have_two_primary_keys():
    with pytest.raises(ValidationError, match="more than one primary"):
        _settings(
            STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
                (
                    "mvn-web-current",
                    _PRIMARY_SECRET,
                    {"mvn.by": "primary"},
                ),
                (
                    "mvn-web-other",
                    _PREVIOUS_SECRET,
                    {"mvn.by": "primary"},
                ),
            )
        )


def test_secret_reuse_across_key_ids_is_rejected():
    with pytest.raises(ValidationError, match="secrets must be unique"):
        _settings(
            STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
                (
                    "mvn-web-current",
                    _PRIMARY_SECRET,
                    {"mvn.by": "primary"},
                ),
                (
                    "polotsk-web-current",
                    _PRIMARY_SECRET,
                    {"polotsk.mvn.by": "primary"},
                ),
            )
        )


def test_one_key_cannot_expand_across_multiple_storefront_hosts():
    with pytest.raises(ValidationError, match="exactly one storefront host"):
        _settings(
            STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
                (
                    "shared-web-current",
                    _PRIMARY_SECRET,
                    {
                        "mvn.by": "primary",
                        "polotsk.mvn.by": "primary",
                    },
                )
            )
        )


@pytest.mark.parametrize(
    ("hostname", "message"),
    [
        ("MVN.BY.", "already be canonical"),
        ("mvn.by:443", "already be canonical"),
        ("*.mvn.by", "invalid storefront hostname"),
    ],
)
def test_hostnames_must_be_exact_canonical_values(hostname, message):
    with pytest.raises(ValidationError, match=message):
        _settings(
            STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
                (
                    "mvn-web-current",
                    _PRIMARY_SECRET,
                    {hostname: "primary"},
                )
            )
        )


def test_duplicate_json_key_is_rejected():
    raw = (
        '{"keys":{"duplicated":{"secret":"'
        + _PRIMARY_SECRET
        + '","host_roles":{"mvn.by":"primary"}},"duplicated":{"secret":"'
        + _PREVIOUS_SECRET
        + '","host_roles":{"mvn.by":"previous"}}}}'
    )
    with pytest.raises(ValidationError, match="JSON is invalid"):
        _settings(STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=raw)


def test_legacy_primary_pair_requires_explicit_canonical_host():
    with pytest.raises(ValidationError, match="explicit canonical host allowlist"):
        _settings(
            STOREFRONT_CONTEXT_SIGNING_KEY_ID="mvn-web-current",
            STOREFRONT_CONTEXT_SIGNING_SECRET=_PRIMARY_SECRET,
        )


def test_legacy_key_cannot_be_bound_to_polotsk_or_multiple_hosts():
    with pytest.raises(ValidationError, match="only to the canonical"):
        _settings(
            PUBLIC_SITE_URL="https://mvn.by",
            STOREFRONT_CONTEXT_SIGNING_KEY_ID="mvn-web-current",
            STOREFRONT_CONTEXT_SIGNING_SECRET=_PRIMARY_SECRET,
            STOREFRONT_CONTEXT_LEGACY_ALLOWED_HOSTS="mvn.by,polotsk.mvn.by",
        )


def test_legacy_canonical_rotation_is_accepted_for_migration_only():
    configured = _settings(
        PUBLIC_SITE_URL="https://mvn.by",
        STOREFRONT_CONTEXT_SIGNING_KEY_ID="mvn-web-current",
        STOREFRONT_CONTEXT_SIGNING_SECRET=_PRIMARY_SECRET,
        STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID="mvn-web-previous",
        STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET=_PREVIOUS_SECRET,
        STOREFRONT_CONTEXT_LEGACY_ALLOWED_HOSTS="mvn.by",
        STOREFRONT_CONTEXT_ALLOW_LEGACY_V1_READS=True,
    )

    assert all(
        key.legacy_v1_read_compatible
        for key in configured.storefront_context_signing_keyring.keys
    )


def test_require_signed_switch_needs_any_host_scoped_key():
    with pytest.raises(
        ValidationError,
        match="cannot be required without a signing keyring",
    ):
        _settings(STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=True)


def test_require_signed_switch_needs_primary_for_canonical_host():
    with pytest.raises(
        ValidationError,
        match="primary key for the canonical",
    ):
        _settings(
            PUBLIC_SITE_URL="https://mvn.by",
            STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
                (
                    "polotsk-web-current",
                    _PRIMARY_SECRET,
                    {"polotsk.mvn.by": "primary"},
                )
            ),
            STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=True,
        )


@pytest.mark.parametrize(
    "public_site_url",
    [
        "https://user@mvn.by",
        "https://mvn.by/catalog",
        "https://mvn.by?tenant=1",
        "https://mvn.by#fragment",
        "https://mvn.by:443",
    ],
)
def test_require_signed_rejects_non_origin_public_site_url(public_site_url):
    with pytest.raises(
        ValidationError,
        match="valid PUBLIC_SITE_URL",
    ):
        _settings(
            PUBLIC_SITE_URL=public_site_url,
            STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
                (
                    "mvn-web-current",
                    _PRIMARY_SECRET,
                    {"mvn.by": "primary"},
                )
            ),
            STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=True,
        )


def test_legacy_v1_flag_cannot_apply_to_new_keyring_keys():
    with pytest.raises(
        ValidationError,
        match="canonical legacy signing key",
    ):
        _settings(
            STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
                (
                    "mvn-web-current",
                    _PRIMARY_SECRET,
                    {"mvn.by": "primary"},
                )
            ),
            STOREFRONT_CONTEXT_ALLOW_LEGACY_V1_READS=True,
        )


@pytest.mark.parametrize("value", [1023, 64 * 1024 * 1024 + 1])
def test_signed_body_buffer_must_remain_bounded(value):
    with pytest.raises(ValidationError, match="between 1 KiB and 64 MiB"):
        _settings(STOREFRONT_CONTEXT_MAX_BODY_BYTES=value)


def test_secret_values_are_absent_from_repr_and_validation_error():
    configured = _settings(
        STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
            (
                "mvn-web-current",
                _PRIMARY_SECRET,
                {"mvn.by": "primary"},
            )
        )
    )
    assert _PRIMARY_SECRET not in repr(configured)
    assert _PRIMARY_SECRET not in repr(
        configured.storefront_context_signing_keyring
    )
    assert _PRIMARY_SECRET not in str(configured.model_dump())
    assert "STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON" not in configured.model_dump()

    unsafe = "secret-that-must-never-appear-in-an-error"
    with pytest.raises(ValidationError) as captured:
        _settings(
            STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON=_keyring(
                ("mvn-web-current", unsafe, {"mvn.by": "not-a-role"})
            )
        )
    assert unsafe not in str(captured.value)
