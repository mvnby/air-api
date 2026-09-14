"""Dependency-free staff password policy shared by API and operator tooling."""


class CredentialPolicyError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CredentialPolicy:
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
