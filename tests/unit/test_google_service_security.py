import os
import stat

import pytest

from services import google_service
from services import google_oauth_credentials
from services.google_oauth_credentials import (
    GoogleDriveListError,
    GoogleTokenExchangeError,
    GoogleTokenLoadError,
    GoogleTokenPersistenceError,
    GoogleTokenRefreshError,
    GoogleTokenUnavailableError,
)


class _CredentialsStub:
    refresh_token = "refresh-token"
    client_id = "client-id"
    client_secret = "client-secret"
    token_uri = "https://oauth2.googleapis.com/token"

    @staticmethod
    def to_json() -> str:
        return '{"refresh_token":"secret"}'


class _FlowStub:
    last_instance = None

    def __init__(self):
        self.authorization_kwargs = None
        self.credentials = _CredentialsStub()
        _FlowStub.last_instance = self

    @classmethod
    def from_client_secrets_file(cls, *_args, **_kwargs):
        return cls()

    def authorization_url(self, **kwargs):
        self.authorization_kwargs = kwargs
        return "https://accounts.google.com/o/oauth2/auth", kwargs["state"]

    def fetch_token(self, *, code: str):
        assert code == "oauth-code"


class _FailingFlowStub(_FlowStub):
    def fetch_token(self, *, code: str):
        super().fetch_token(code=code)
        raise RuntimeError("provider exchange failed")


def _service_without_authentication() -> google_service.GoogleDocsService:
    service = google_service.GoogleDocsService.__new__(google_service.GoogleDocsService)
    service.creds = None
    return service


def test_google_service_forwards_explicit_oauth_state(tmp_path, monkeypatch):
    client_secret = tmp_path / "client-secret.json"
    client_secret.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(google_service, "CLIENT_SECRET_FILE", str(client_secret))
    monkeypatch.setattr(google_service, "Flow", _FlowStub)
    service = _service_without_authentication()

    service.get_auth_url("https://api.example/callback", state="signed-session-state")

    assert _FlowStub.last_instance.authorization_kwargs["state"] == "signed-session-state"


def test_google_token_file_is_replaced_atomically_with_private_mode(tmp_path, monkeypatch):
    client_secret = tmp_path / "client-secret.json"
    token_file = tmp_path / "token.json"
    client_secret.write_text("{}", encoding="utf-8")
    token_file.write_text("stale-token", encoding="utf-8")
    token_file.chmod(0o644)
    monkeypatch.setattr(google_service, "CLIENT_SECRET_FILE", str(client_secret))
    monkeypatch.setattr(google_service, "TOKEN_FILE", str(token_file))
    monkeypatch.setattr(google_service, "Flow", _FlowStub)
    service = _service_without_authentication()

    replace_calls = []
    real_replace = os.replace

    def record_replace(source, destination):
        replace_calls.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(google_oauth_credentials.os, "replace", record_replace)
    service.finish_auth("oauth-code", "https://api.example/callback")

    assert token_file.read_text(encoding="utf-8") == '{"refresh_token":"secret"}'
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert len(replace_calls) == 1
    assert replace_calls[0][1] == str(token_file)
    assert replace_calls[0][0] != str(token_file)
    assert list(tmp_path.glob(".token.json.*")) == []


class _RefreshingCredentials:
    def __init__(self, *, refresh_error: Exception | None = None):
        self.valid = False
        self.expired = True
        self.refresh_token = "refresh-token"
        self.client_id = "client-id"
        self.client_secret = "client-secret"
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.scopes = list(google_service.SCOPES)
        self.expiry = None
        self.refresh_error = refresh_error
        self.refresh_calls = 0

    def refresh(self, _request) -> None:
        self.refresh_calls += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        self.valid = True
        self.expired = False

    @staticmethod
    def to_json() -> str:
        return '{"refresh_token":"rotated-secret"}'


class _PartiallyRefreshingCredentials(_RefreshingCredentials):
    def refresh(self, _request) -> None:
        self.refresh_calls += 1
        self.valid = True
        self.expired = False
        raise RuntimeError("refresh failed after a partial mutation")


class _DriveListRequest:
    def __init__(self, *, result=None, error: Exception | None = None):
        self.result = result
        self.error = error

    def execute(self):
        if self.error is not None:
            raise self.error
        return self.result


class _DriveFiles:
    def __init__(self, request: _DriveListRequest):
        self.request = request

    def list(self, **_kwargs):
        return self.request


class _DriveService:
    def __init__(self, request: _DriveListRequest):
        self.request = request

    def files(self):
        return _DriveFiles(self.request)


def _configure_loaded_credentials(monkeypatch, credentials) -> None:
    monkeypatch.setattr(
        google_oauth_credentials.Credentials,
        "from_authorized_user_file",
        lambda *_args, **_kwargs: credentials,
    )


def test_missing_token_keeps_reauthentication_available(tmp_path, monkeypatch):
    token_file = tmp_path / "oauth" / "token.json"
    token_file.parent.mkdir()
    client_secret = tmp_path / "client-secret.json"
    client_secret.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(google_service, "TOKEN_FILE", str(token_file))
    monkeypatch.setattr(google_service, "CLIENT_SECRET_FILE", str(client_secret))
    monkeypatch.setattr(google_service, "Flow", _FlowStub)

    service = google_service.GoogleDocsService()

    assert service.creds is None
    assert service.get_auth_url(
        "https://api.example/callback",
        state="signed-session-state",
    ).startswith("https://accounts.google.com/")
    assert service.finish_auth("oauth-code", "https://api.example/callback") is True
    assert token_file.read_text(encoding="utf-8") == '{"refresh_token":"secret"}'


def test_missing_token_fails_api_operation_without_building_adc_client(tmp_path, monkeypatch):
    monkeypatch.setattr(google_service, "TOKEN_FILE", str(tmp_path / "missing-token.json"))
    build_calls = []
    monkeypatch.setattr(
        google_service,
        "build",
        lambda *_args, **_kwargs: build_calls.append(True),
    )

    service = google_service.GoogleDocsService()

    with pytest.raises(GoogleTokenUnavailableError, match="token file is missing"):
        service.list_files("backup-folder")
    assert build_calls == []


def test_oauth_exchange_failure_is_typed_and_does_not_write_token(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    client_secret = tmp_path / "client-secret.json"
    client_secret.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(google_service, "TOKEN_FILE", str(token_file))
    monkeypatch.setattr(google_service, "CLIENT_SECRET_FILE", str(client_secret))
    monkeypatch.setattr(google_service, "Flow", _FailingFlowStub)
    service = google_service.GoogleDocsService()

    with pytest.raises(GoogleTokenExchangeError, match="code exchange failed"):
        service.finish_auth("oauth-code", "https://api.example/callback")
    assert not token_file.exists()


def test_refresh_persistence_failure_keeps_valid_credentials_and_never_uses_adc(
    tmp_path,
    monkeypatch,
    caplog,
):
    token_file = tmp_path / "oauth" / "token.json"
    token_file.parent.mkdir()
    token_file.write_text("stale", encoding="utf-8")
    credentials = _RefreshingCredentials()
    _configure_loaded_credentials(monkeypatch, credentials)
    monkeypatch.setattr(google_service, "TOKEN_FILE", str(token_file))

    def fail_replace(_source, _destination):
        raise OSError(16, "Device or resource busy")

    monkeypatch.setattr(google_oauth_credentials.os, "replace", fail_replace)
    built_with = []

    def fake_build(_api, _version, *, credentials):
        built_with.append(credentials)
        return _DriveService(_DriveListRequest(result={"files": []}))

    monkeypatch.setattr(google_service, "build", fake_build)

    service = google_service.GoogleDocsService()

    assert credentials.refresh_calls == 1
    assert credentials.valid is True
    assert isinstance(service.auth_error, GoogleTokenPersistenceError)
    assert service.get_token_status()["valid"] is True
    assert service.get_token_status()["persistence_ok"] is False
    assert (
        service.get_token_status()["persistence_error_code"]
        == "GoogleTokenPersistenceError"
    )
    assert "persistence_state=failed" in caplog.text
    assert service.list_files("backup-folder") == []
    assert built_with == [credentials]
    assert list(token_file.parent.glob(".token.json.*")) == []


def test_valid_in_memory_refresh_retries_and_recovers_durable_persistence(
    tmp_path,
    monkeypatch,
):
    token_file = tmp_path / "oauth" / "token.json"
    token_file.parent.mkdir()
    token_file.write_text("stale", encoding="utf-8")
    credentials = _RefreshingCredentials()
    _configure_loaded_credentials(monkeypatch, credentials)
    monkeypatch.setattr(google_service, "TOKEN_FILE", str(token_file))
    real_replace = google_oauth_credentials.os.replace
    attempts = 0

    def fail_first_replace(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(16, "Device or resource busy")
        real_replace(source, destination)

    monkeypatch.setattr(google_oauth_credentials.os, "replace", fail_first_replace)
    monkeypatch.setattr(
        google_service,
        "build",
        lambda *_args, **_kwargs: _DriveService(
            _DriveListRequest(result={"files": []})
        ),
    )

    service = google_service.GoogleDocsService()
    assert isinstance(service.auth_error, GoogleTokenPersistenceError)

    assert service.list_files("backup-folder") == []
    assert service.auth_error is None
    assert service.get_token_status()["persistence_ok"] is True
    assert token_file.read_text(encoding="utf-8") == credentials.to_json()
    assert attempts == 2


def test_non_refreshable_oauth_exchange_does_not_replace_durable_token(
    tmp_path,
    monkeypatch,
):
    token_file = tmp_path / "token.json"
    token_file.write_text('{"refresh_token":"durable"}', encoding="utf-8")
    client_secret = tmp_path / "client-secret.json"
    client_secret.write_text("{}", encoding="utf-8")

    class NonRefreshableCredentials(_CredentialsStub):
        refresh_token = None

    class NonRefreshableFlow(_FlowStub):
        def __init__(self):
            super().__init__()
            self.credentials = NonRefreshableCredentials()

    monkeypatch.setattr(google_service, "CLIENT_SECRET_FILE", str(client_secret))
    monkeypatch.setattr(google_service, "TOKEN_FILE", str(token_file))
    monkeypatch.setattr(google_service, "Flow", NonRefreshableFlow)
    service = _service_without_authentication()

    with pytest.raises(GoogleTokenPersistenceError, match="refresh_token"):
        service.finish_auth("oauth-code", "https://api.example/callback")

    assert token_file.read_text(encoding="utf-8") == '{"refresh_token":"durable"}'


def test_refresh_failure_is_typed_and_does_not_build_google_client(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    token_file.write_text("stale", encoding="utf-8")
    credentials = _RefreshingCredentials(refresh_error=RuntimeError("provider rejected refresh"))
    _configure_loaded_credentials(monkeypatch, credentials)
    monkeypatch.setattr(google_service, "TOKEN_FILE", str(token_file))
    build_calls = []
    monkeypatch.setattr(google_service, "build", lambda *_args, **_kwargs: build_calls.append(True))

    service = google_service.GoogleDocsService()

    with pytest.raises(GoogleTokenRefreshError, match="token refresh failed"):
        service.list_files("backup-folder")
    assert build_calls == []


def test_refresh_error_wins_even_if_provider_partially_marks_credentials_valid(
    tmp_path,
    monkeypatch,
):
    token_file = tmp_path / "token.json"
    token_file.write_text("stale", encoding="utf-8")
    credentials = _PartiallyRefreshingCredentials()
    _configure_loaded_credentials(monkeypatch, credentials)
    monkeypatch.setattr(google_service, "TOKEN_FILE", str(token_file))
    build_calls = []
    monkeypatch.setattr(
        google_service,
        "build",
        lambda *_args, **_kwargs: build_calls.append(True),
    )

    service = google_service.GoogleDocsService()

    with pytest.raises(GoogleTokenRefreshError, match="token refresh failed"):
        service.list_files("backup-folder")
    assert credentials.valid is True
    assert build_calls == []


def test_malformed_token_is_distinct_from_refresh_failure(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    token_file.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(google_service, "TOKEN_FILE", str(token_file))

    def fail_to_load_token(*_args, **_kwargs):
        raise ValueError("invalid json")

    monkeypatch.setattr(
        google_oauth_credentials.Credentials,
        "from_authorized_user_file",
        fail_to_load_token,
    )
    build_calls = []
    monkeypatch.setattr(
        google_service,
        "build",
        lambda *_args, **_kwargs: build_calls.append(True),
    )

    service = google_service.GoogleDocsService()

    with pytest.raises(GoogleTokenLoadError, match="could not be loaded"):
        service.list_files("backup-folder")
    assert build_calls == []


def test_list_files_propagates_provider_failure_instead_of_returning_empty(
    monkeypatch,
):
    service = _service_without_authentication()
    credentials = _RefreshingCredentials()
    credentials.valid = True
    credentials.expired = False
    service.creds = credentials
    service._auth_error = None
    monkeypatch.setattr(
        google_service,
        "build",
        lambda *_args, **_kwargs: _DriveService(
            _DriveListRequest(error=RuntimeError("drive unavailable"))
        ),
    )

    with pytest.raises(GoogleDriveListError, match="failed to list files"):
        service.list_files("backup-folder")


def test_delete_file_strict_treats_provider_not_found_as_success(monkeypatch):
    class FakeHttpError(Exception):
        def __init__(self, status: int):
            super().__init__(f"provider status {status}")
            self.resp = type("Response", (), {"status": status})()

    class DeleteRequest:
        def execute(self):
            raise FakeHttpError(404)

    class DriveFiles:
        def update(self, *, fileId, body):
            assert fileId == "drive-file"
            assert body == {"trashed": True}
            return DeleteRequest()

    class DriveService:
        @staticmethod
        def files():
            return DriveFiles()

    service = _service_without_authentication()
    monkeypatch.setattr(service, "_require_credentials", lambda: object())
    monkeypatch.setattr(google_service, "HttpError", FakeHttpError)
    monkeypatch.setattr(google_service, "build", lambda *_args, **_kwargs: DriveService())

    service.delete_file_strict(" drive-file ")


def test_delete_file_strict_surfaces_retryable_provider_failure(monkeypatch):
    class FakeHttpError(Exception):
        def __init__(self, status: int):
            super().__init__(f"provider status {status}")
            self.resp = type("Response", (), {"status": status})()

    class DeleteRequest:
        def execute(self):
            raise FakeHttpError(503)

    class DriveFiles:
        @staticmethod
        def update(**_kwargs):
            return DeleteRequest()

    class DriveService:
        @staticmethod
        def files():
            return DriveFiles()

    service = _service_without_authentication()
    monkeypatch.setattr(service, "_require_credentials", lambda: object())
    monkeypatch.setattr(google_service, "HttpError", FakeHttpError)
    monkeypatch.setattr(google_service, "build", lambda *_args, **_kwargs: DriveService())

    with pytest.raises(FakeHttpError, match="provider status 503"):
        service.delete_file_strict("drive-file")
