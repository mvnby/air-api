import os
import stat

from services import google_service


class _CredentialsStub:
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

    monkeypatch.setattr(google_service.os, "replace", record_replace)
    service.finish_auth("oauth-code", "https://api.example/callback")

    assert token_file.read_text(encoding="utf-8") == '{"refresh_token":"secret"}'
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert len(replace_calls) == 1
    assert replace_calls[0][1] == str(token_file)
    assert replace_calls[0][0] != str(token_file)
    assert list(tmp_path.glob(".token.json.*")) == []
