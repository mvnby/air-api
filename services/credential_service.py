"""Shared password policy and bcrypt operations for staff credentials."""

import bcrypt


class CredentialPolicyError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CredentialService:
    MIN_PASSWORD_CHARACTERS = 9
    MAX_PASSWORD_UTF8_BYTES = 72

    @classmethod
    def validate_password(cls, password: str) -> str:
        value = str(password or "")
        if len(value) < cls.MIN_PASSWORD_CHARACTERS:
            raise CredentialPolicyError(
                "password_too_short",
                f"Пароль должен содержать не менее {cls.MIN_PASSWORD_CHARACTERS} символов",
            )
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise CredentialPolicyError(
                "password_invalid_encoding",
                "Пароль содержит недопустимую Unicode-последовательность",
            ) from exc
        if len(encoded) > cls.MAX_PASSWORD_UTF8_BYTES:
            raise CredentialPolicyError(
                "password_too_long",
                f"Пароль должен занимать не более {cls.MAX_PASSWORD_UTF8_BYTES} UTF-8 байт",
            )
        return value

    @classmethod
    def hash_password(cls, password: str) -> str:
        value = cls.validate_password(password)
        return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @classmethod
    def verify_password(cls, password: str, password_hash: str | None) -> bool:
        if not password_hash:
            return False
        value = str(password or "")
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError:
            return False
        if len(encoded) > cls.MAX_PASSWORD_UTF8_BYTES:
            return False
        try:
            return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
        except (TypeError, ValueError):
            return False


__all__ = ["CredentialPolicyError", "CredentialService"]
