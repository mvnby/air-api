import os
import tempfile
from dataclasses import dataclass
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


class GoogleCredentialsError(RuntimeError):
    """Base error for unavailable Google OAuth credentials."""


class GoogleTokenUnavailableError(GoogleCredentialsError):
    """The configured token is missing or cannot authorize requests."""


class GoogleTokenLoadError(GoogleCredentialsError):
    """The configured token file cannot be parsed."""


class GoogleTokenRefreshError(GoogleCredentialsError):
    """Google rejected or failed the token refresh request."""


class GoogleTokenPersistenceError(GoogleCredentialsError):
    """A refreshed or newly issued token cannot be persisted safely."""


class GoogleTokenExchangeError(GoogleCredentialsError):
    """The OAuth authorization code cannot be exchanged for credentials."""


class GoogleDriveListError(RuntimeError):
    """Google Drive failed to list files; this is not an empty result."""


@dataclass(frozen=True)
class GoogleCredentialState:
    credentials: Credentials | None
    error: GoogleCredentialsError | None = None


class GoogleOAuthCredentialStore:
    """Loads, refreshes, and atomically persists one OAuth token file."""

    def __init__(self, token_file: str, scopes: Sequence[str]):
        self.token_file = os.path.abspath(token_file)
        self.scopes = list(scopes)

    def load(self) -> GoogleCredentialState:
        if not os.path.exists(self.token_file):
            return GoogleCredentialState(
                credentials=None,
                error=GoogleTokenUnavailableError(
                    f"Google OAuth token file is missing: {self.token_file}"
                ),
            )

        try:
            credentials = Credentials.from_authorized_user_file(
                self.token_file,
                self.scopes,
            )
        except Exception as exc:
            error = GoogleTokenLoadError(
                f"Google OAuth token file could not be loaded: {self.token_file}"
            )
            error.__cause__ = exc
            return GoogleCredentialState(
                credentials=None,
                error=error,
            )

        if credentials.valid:
            return GoogleCredentialState(credentials=credentials)

        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception as exc:
                error = GoogleTokenRefreshError("Google OAuth token refresh failed")
                error.__cause__ = exc
                return GoogleCredentialState(
                    credentials=credentials,
                    error=error,
                )

            try:
                self.persist(credentials)
            except GoogleTokenPersistenceError as exc:
                # Keep the refreshed in-memory credentials for status reporting,
                # and let the caller decide whether current-process availability
                # can continue while the persistence incident remains visible.
                return GoogleCredentialState(credentials=credentials, error=exc)

            if credentials.valid:
                return GoogleCredentialState(credentials=credentials)

        return GoogleCredentialState(
            credentials=credentials,
            error=GoogleTokenUnavailableError(
                "Google OAuth credentials are invalid and cannot be refreshed"
            ),
        )

    def persist(self, credentials: Credentials) -> None:
        token_dir = os.path.dirname(self.token_file)
        temp_path: str | None = None
        required_fields = ("refresh_token", "client_id", "client_secret", "token_uri")
        missing = [name for name in required_fields if not getattr(credentials, name, None)]
        if missing:
            raise GoogleTokenPersistenceError(
                "Google OAuth credentials cannot be persisted without: "
                + ",".join(missing)
            )
        try:
            parent_existed = os.path.isdir(token_dir)
            os.makedirs(token_dir, mode=0o700, exist_ok=True)
            if not parent_existed:
                os.chmod(token_dir, 0o700)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=token_dir,
                prefix=f".{os.path.basename(self.token_file)}.",
                delete=False,
            ) as token:
                temp_path = token.name
                os.chmod(temp_path, 0o600)
                token.write(credentials.to_json())
                token.flush()
                os.fsync(token.fileno())

            os.replace(temp_path, self.token_file)
            temp_path = None
            os.chmod(self.token_file, 0o600)
            directory_fd = os.open(token_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception as exc:
            raise GoogleTokenPersistenceError(
                f"Google OAuth token could not be persisted: {self.token_file}"
            ) from exc
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
