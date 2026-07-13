from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from core import config as config_module
from core.config import Settings
from services import private_attachment_storage_service as storage_module
from services.private_attachment_storage_service import (
    S3PrivateAttachmentStorage,
    verify_private_attachment_storage_startup,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class _Body:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class _MissingObject(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class _ProbeS3Client:
    def __init__(self, *, delete_objects: bool = True) -> None:
        self.delete_objects = delete_objects
        self.objects: dict[str, bytes] = {}
        self.operations: list[tuple[str, str, str]] = []

    def put_object(self, **kwargs) -> None:
        self.operations.append(("write", kwargs["Bucket"], kwargs["Key"]))
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        self.operations.append(("read", kwargs["Bucket"], kwargs["Key"]))
        try:
            return {"Body": _Body(self.objects[kwargs["Key"]])}
        except KeyError as exc:
            raise _MissingObject from exc

    def head_object(self, **kwargs):
        self.operations.append(("verify-delete", kwargs["Bucket"], kwargs["Key"]))
        if kwargs["Key"] not in self.objects:
            raise _MissingObject
        return {}

    def delete_object(self, **kwargs) -> None:
        self.operations.append(("delete", kwargs["Bucket"], kwargs["Key"]))
        if self.delete_objects:
            self.objects.pop(kwargs["Key"], None)


def _settings_values(**overrides):
    values = {
        "SECRET_KEY": "secret-key-must-not-leak",
        "BOT_TOKEN": "bot-token-must-not-leak",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "admin-password-must-not-leak",
        "POSTGRES_PASSWORD": "postgres-password-must-not-leak",
        "ENVIRONMENT": "production",
        "SERVICE_ATTACHMENT_STORAGE_PROVIDER": "r2",
        "SERVICE_ATTACHMENT_S3_BUCKET": "private-service-evidence",
        "SERVICE_ATTACHMENT_S3_ENDPOINT_URL": "https://account.r2.invalid",
        "SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID": "r2-access-key-must-not-leak",
        "SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY": "r2-secret-key-must-not-leak",
        "MEDIA_S3_BUCKET": "public-media",
        "PRODUCT_MEDIA_S3_BUCKET": "public-products",
    }
    values.update(overrides)
    return values


def _startup_settings(**overrides):
    values = _settings_values(**overrides)
    values.update(
        {
            "is_production": values["ENVIRONMENT"] == "production",
            "SERVICE_ATTACHMENT_LOCAL_DIR": "private_media/service-attachments",
            "SERVICE_ATTACHMENT_S3_REGION": "auto",
            "SERVICE_ATTACHMENT_S3_KEY_PREFIX": "service-attachments",
        }
    )
    return SimpleNamespace(**values)


def test_validation_error_hides_all_settings_inputs():
    values = _settings_values(SERVICE_ATTACHMENT_STORAGE_PROVIDER="local")

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)

    rendered_error = "\n".join(
        (
            str(error.value),
            repr(error.value.errors()),
            error.value.json(),
        )
    )
    assert error.value.__context__ is None
    for secret_name in (
        "SECRET_KEY",
        "BOT_TOKEN",
        "ADMIN_PASSWORD",
        "POSTGRES_PASSWORD",
        "SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID",
        "SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY",
    ):
        assert values[secret_name] not in rendered_error


def test_production_private_storage_requires_https_endpoint():
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            _env_file=None,
            **_settings_values(
                SERVICE_ATTACHMENT_S3_ENDPOINT_URL="http://account.r2.invalid"
            ),
        )


@pytest.mark.parametrize("public_bucket_setting", ["MEDIA_S3_BUCKET", "PRODUCT_MEDIA_S3_BUCKET"])
def test_production_private_bucket_must_not_be_shared(public_bucket_setting):
    values = _settings_values()
    values[public_bucket_setting] = values["SERVICE_ATTACHMENT_S3_BUCKET"].upper()

    with pytest.raises(ValidationError, match="must differ"):
        Settings(_env_file=None, **values)


def test_local_settings_do_not_require_r2_or_run_startup_probe(monkeypatch):
    local_settings = Settings(
        _env_file=None,
        SECRET_KEY="test",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="admin",
        ENVIRONMENT="local",
    )
    calls = []
    monkeypatch.setattr(
        storage_module,
        "verify_private_attachment_storage_startup",
        calls.append,
    )

    config_module._run_production_startup_checks(local_settings)

    assert local_settings.SERVICE_ATTACHMENT_STORAGE_PROVIDER == "local"
    assert calls == []


def test_production_startup_hook_invokes_private_storage_probe(monkeypatch):
    configured = _startup_settings()
    calls = []
    monkeypatch.setattr(
        storage_module,
        "verify_private_attachment_storage_startup",
        calls.append,
    )

    config_module._run_production_startup_checks(configured)

    assert calls == [configured]


def test_s3_storage_rejects_non_https_endpoint():
    with pytest.raises(ValueError, match="HTTPS"):
        S3PrivateAttachmentStorage(
            bucket="private-service-evidence",
            endpoint_url="http://account.r2.invalid",
            access_key_id="access",
            secret_access_key="secret",
            region="auto",
            key_prefix="service-attachments",
        )


def test_startup_probe_writes_reads_deletes_and_confirms_cleanup():
    client = _ProbeS3Client()

    verify_private_attachment_storage_startup(
        _startup_settings(),
        client=client,
    )

    assert [operation for operation, _bucket, _key in client.operations] == [
        "write",
        "read",
        "delete",
        "verify-delete",
    ]
    assert {bucket for _operation, bucket, _key in client.operations} == {
        "private-service-evidence"
    }
    assert client.objects == {}


def test_startup_probe_fails_closed_when_delete_does_not_remove_object():
    client = _ProbeS3Client(delete_objects=False)
    configured = _startup_settings()

    with pytest.raises(RuntimeError, match="startup probe failed") as error:
        verify_private_attachment_storage_startup(configured, client=client)

    assert configured.SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY not in str(error.value)


@pytest.mark.parametrize(
    "compose_path",
    [
        REPO_ROOT / "docker-compose.prod.yml",
        REPO_ROOT / "deploy/ha/mvn-api/docker-compose.patroni.yml",
    ],
)
def test_production_compose_pins_environment_and_private_storage_provider(compose_path):
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    service_environments = [
        compose["services"][service_name]["environment"]
        for service_name in ("app", "app-blue", "app-green", "bot")
    ]

    for environment in service_environments:
        assert environment["ENVIRONMENT"] == "production"
        assert environment["SERVICE_ATTACHMENT_STORAGE_PROVIDER"] == "r2"
