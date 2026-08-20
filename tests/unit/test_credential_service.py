import pytest

from services.credential_service import CredentialPolicyError, CredentialService


def test_credential_policy_counts_characters_and_utf8_bytes() -> None:
    assert CredentialService.validate_password("nine-char") == "nine-char"

    with pytest.raises(CredentialPolicyError) as short:
        CredentialService.validate_password("short")
    assert short.value.code == "password_too_short"

    with pytest.raises(CredentialPolicyError) as long:
        CredentialService.validate_password("я" * 37)
    assert long.value.code == "password_too_long"


def test_credential_verification_rejects_overlong_input_without_bcrypt_error() -> None:
    password_hash = CredentialService.hash_password("safe-password-2026")

    assert CredentialService.verify_password("safe-password-2026", password_hash)
    assert not CredentialService.verify_password("x" * 73, password_hash)
    assert not CredentialService.verify_password("safe-password-2026", "invalid-hash")


def test_credential_policy_rejects_lone_surrogates_without_encoding_error() -> None:
    invalid_unicode = "\ud800" * 9

    with pytest.raises(CredentialPolicyError) as invalid:
        CredentialService.validate_password(invalid_unicode)
    assert invalid.value.code == "password_invalid_encoding"
    assert not CredentialService.verify_password(invalid_unicode, "invalid-hash")
