import argparse
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/ha/upload_postgres_pitr_to_s3.py"
SPEC = importlib.util.spec_from_file_location("upload_postgres_pitr_to_s3", MODULE_PATH)
assert SPEC and SPEC.loader
pitr = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pitr
SPEC.loader.exec_module(pitr)


def test_wal_filename_filter_accepts_postgres_archive_files(tmp_path):
    accepted = [
        "00000001000000000000000A",
        "00000001000000000000000A.00000028.backup",
        "00000002.history",
    ]
    rejected = [
        ".hidden",
        "00000001000000000000000A.partial",
        "README",
        "00000001000000000000000",
    ]

    for name in accepted + rejected:
        (tmp_path / name).write_bytes(b"x")

    assert [path.name for path in pitr.iter_wal_files(tmp_path)] == accepted


def test_wal_key_groups_by_cluster_and_timeline():
    config = pitr.PitrS3Config(
        bucket="private",
        endpoint_url="https://example.invalid",
        region="auto",
        access_key_id="key",
        secret_access_key="secret",
        key_prefix="postgres/pitr",
        cluster="mvn-api",
    )

    assert (
        pitr.wal_key(config, "00000001000000000000000A")
        == "postgres/pitr/mvn-api/wal/00000001/00000001000000000000000A"
    )


def test_pitr_config_does_not_fall_back_to_public_media_env(monkeypatch):
    monkeypatch.delenv("POSTGRES_PITR_S3_BUCKET", raising=False)
    monkeypatch.delenv("POSTGRES_PITR_S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("POSTGRES_PITR_S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("POSTGRES_PITR_S3_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setenv("POSTGRES_PITR_CLUSTER", "mvn-api")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_BUCKET", "public-media")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_ENDPOINT_URL", "https://public.invalid")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_ACCESS_KEY_ID", "public-key")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY", "public-secret")

    with pytest.raises(SystemExit) as exc:
        pitr.load_config()

    assert "POSTGRES_PITR_S3_BUCKET" in str(exc.value)


def test_credential_probe_proves_put_head_get_delete(monkeypatch, capsys):
    config = pitr.PitrS3Config(
        bucket="private",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        region="auto",
        access_key_id="key",
        secret_access_key="secret",
        key_prefix="postgres/pitr",
        cluster="mvn-api",
    )

    class MissingObject(Exception):
        response = {
            "Error": {"Code": "404"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }

    class Client:
        def __init__(self):
            self.payload = None
            self.metadata = None
            self.deleted = False
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append("put")
            self.payload = kwargs["Body"]
            self.metadata = kwargs["Metadata"]

        def head_object(self, **_kwargs):
            self.calls.append("head-missing" if self.deleted else "head")
            if self.deleted:
                raise MissingObject
            return {
                "ContentLength": len(self.payload),
                "Metadata": self.metadata,
            }

        def get_object(self, **_kwargs):
            self.calls.append("get")
            return {"Body": io.BytesIO(self.payload)}

        def delete_object(self, **_kwargs):
            self.calls.append("delete")
            self.deleted = True

    client = Client()
    monkeypatch.setattr(pitr, "load_config", lambda: config)
    monkeypatch.setattr(pitr, "build_client", lambda _config: client)
    monkeypatch.setattr(pitr.secrets, "token_bytes", lambda _size: b"x" * 64)
    monkeypatch.setattr(pitr.secrets, "token_hex", lambda _size: "c" * 32)

    result = pitr.probe_credentials(
        argparse.Namespace(transaction_id="a" * 32, node="zakup")
    )

    assert result == 0
    assert client.calls == ["put", "head", "get", "delete", "head-missing"]
    assert '"status": "passed"' in capsys.readouterr().out


def test_credential_probe_deletes_canary_when_get_verification_fails(monkeypatch):
    config = pitr.PitrS3Config("b", "https://e", "auto", "k", "s", "p", "mvn-api")

    class Client:
        deleted = False

        def put_object(self, **_kwargs):
            pass

        def head_object(self, **_kwargs):
            return {"ContentLength": 64, "Metadata": {"sha256": "0" * 64}}

        def get_object(self, **_kwargs):
            raise AssertionError("GET must not run after bad HEAD")

        def delete_object(self, **_kwargs):
            self.deleted = True

    client = Client()
    monkeypatch.setattr(pitr, "load_config", lambda: config)
    monkeypatch.setattr(pitr, "build_client", lambda _config: client)

    with pytest.raises(RuntimeError, match="HEAD verification failed"):
        pitr.probe_credentials(
            argparse.Namespace(transaction_id="a" * 32, node="mvn-api")
        )

    assert client.deleted is True


def _basebackup_args(source_dir: Path, **overrides):
    values = {
        "source_dir": str(source_dir),
        "backup_id": "20260713T120000Z",
        "system_identifier": "7612345678901234567",
        "timeline": "7",
        "start_lsn": "1/A000000",
        "end_lsn": "1/B000000",
        "started_at": "2026-07-13T12:00:00Z",
        "completed_at": "2026-07-13T12:02:00Z",
        "source_node": "mvn-api",
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_basebackup_manifest_has_exact_lineage_schema(monkeypatch, tmp_path):
    (tmp_path / "base.tar.gz").write_bytes(b"base")
    (tmp_path / "backup_manifest").write_bytes(b"postgres-manifest")
    config = pitr.PitrS3Config(
        "private", "https://example.invalid", "auto", "key", "secret", "pitr", "mvn-api"
    )

    class Client:
        def __init__(self):
            self.objects = {}
            self.manifest = b""

        class MissingObject(Exception):
            response = {
                "Error": {"Code": "NoSuchKey"},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            }

        def put_object(self, **kwargs):
            body = kwargs["Body"]
            payload = body.read() if hasattr(body, "read") else body
            if kwargs["Key"].endswith("/manifest.json"):
                self.manifest = payload
            self.objects[kwargs["Key"]] = (payload, kwargs["Metadata"])
            assert kwargs["IfNoneMatch"] == "*"

        def head_object(self, *, Bucket, Key):
            assert Bucket == "private"
            if Key not in self.objects:
                raise self.MissingObject
            payload, metadata = self.objects[Key]
            return {"ContentLength": len(payload), "Metadata": metadata}

        def get_object(self, *, Bucket, Key):
            assert Bucket == "private"
            payload, _metadata = self.objects[Key]
            return {"ContentLength": len(payload), "Body": io.BytesIO(payload)}

    client = Client()
    monkeypatch.setattr(pitr, "load_config", lambda: config)
    monkeypatch.setattr(pitr, "build_client", lambda _config: client)

    assert pitr.upload_basebackup(_basebackup_args(tmp_path)) == 0
    manifest = json.loads(client.manifest)
    assert set(manifest) == {
        "schema_version",
        "backup_id",
        "cluster",
        "system_identifier",
        "timeline",
        "start_lsn",
        "end_lsn",
        "started_at",
        "completed_at",
        "source_node",
        "files",
    }
    assert manifest["schema_version"] == 1
    assert manifest["system_identifier"] == "7612345678901234567"
    assert manifest["timeline"] == 7
    assert manifest["start_lsn"] == "1/A000000"
    assert manifest["end_lsn"] == "1/B000000"
    assert {entry["name"] for entry in manifest["files"]} == {
        "backup_manifest",
        "base.tar.gz",
    }
    assert all(
        set(entry) == {"name", "key", "size_bytes", "sha256"}
        for entry in manifest["files"]
    )
    manifest_key = "pitr/mvn-api/basebackups/20260713T120000Z/manifest.json"
    _, metadata = client.objects[manifest_key]
    assert metadata == {
        "sha256": hashlib.sha256(client.manifest).hexdigest(),
        "uploaded-by": "mvn-postgres-pitr",
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("system_identifier", "0", "system identifier"),
        ("timeline", "01", "timeline"),
        ("start_lsn", "01/A000000", "not canonical"),
        ("end_lsn", "1/9000000", "precedes start LSN"),
        ("started_at", "2026-07-13T12:00:00+00:00", "not canonical UTC"),
        ("source_node", "unknown", "source node"),
    ],
)
def test_basebackup_lineage_rejects_noncanonical_values(
    tmp_path, field, value, message
):
    with pytest.raises(SystemExit, match=message):
        pitr._basebackup_lineage(_basebackup_args(tmp_path, **{field: value}))


def test_wal_upload_is_create_only_and_idempotent_for_identical_content(
    monkeypatch, tmp_path
):
    wal_name = "00000007000000010000000A"
    wal_path = tmp_path / wal_name
    wal_path.write_bytes(b"reviewed-wal")
    config = pitr.PitrS3Config(
        "private", "https://example.invalid", "auto", "key", "secret", "pitr", "mvn-api"
    )

    class MissingObject(Exception):
        response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }

    class Client:
        def __init__(self):
            self.objects = {}
            self.put_calls = 0

        def head_object(self, *, Bucket, Key):
            assert Bucket == "private"
            if Key not in self.objects:
                raise MissingObject
            payload, metadata = self.objects[Key]
            return {"ContentLength": len(payload), "Metadata": metadata}

        def put_object(self, **kwargs):
            assert kwargs["IfNoneMatch"] == "*"
            self.put_calls += 1
            self.objects[kwargs["Key"]] = (
                kwargs["Body"].read(),
                kwargs["Metadata"],
            )

        def get_object(self, *, Bucket, Key):
            assert Bucket == "private"
            payload, _metadata = self.objects[Key]
            return {"ContentLength": len(payload), "Body": io.BytesIO(payload)}

    client = Client()
    monkeypatch.setattr(pitr, "load_config", lambda: config)
    monkeypatch.setattr(pitr, "build_client", lambda _config: client)
    args = argparse.Namespace(
        archive_dir=str(tmp_path),
        dry_run=False,
        delete_after_upload=False,
    )

    assert pitr.upload_wal(args) == 0
    assert pitr.upload_wal(args) == 0
    assert client.put_calls == 1

    wal_path.write_bytes(b"different-wal")
    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        pitr.upload_wal(args)
    assert client.put_calls == 1


def test_conditional_upload_accepts_racing_identical_object(monkeypatch, tmp_path):
    source = tmp_path / "00000007000000010000000B"
    source.write_bytes(b"same-content")
    config = pitr.PitrS3Config(
        "private", "https://example.invalid", "auto", "key", "secret", "pitr", "mvn-api"
    )
    digest = hashlib.sha256(b"same-content").hexdigest()

    class MissingObject(Exception):
        response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }

    class PreconditionFailed(Exception):
        response = {
            "Error": {"Code": "PreconditionFailed"},
            "ResponseMetadata": {"HTTPStatusCode": 412},
        }

    class Client:
        calls = 0

        def head_object(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise MissingObject
            return {
                "ContentLength": len(b"same-content"),
                "Metadata": {
                    "sha256": digest,
                    "uploaded-by": "mvn-postgres-pitr",
                },
            }

        def put_object(self, **_kwargs):
            raise PreconditionFailed

        def get_object(self, **_kwargs):
            return {
                "ContentLength": len(b"same-content"),
                "Body": io.BytesIO(b"same-content"),
            }

    snapshot = pitr.upload_file(
        Client(),
        config,
        source,
        pitr.wal_key(config, source.name),
        False,
        conditional_create=True,
    )

    assert snapshot.sha256 == digest


@pytest.mark.parametrize(
    "remote_body",
    (b"forged-bytes", b"short", b"expected-bytes-extra"),
)
def test_existing_object_requires_actual_bounded_content_hash(remote_body):
    expected = b"expected-bytes"
    digest = hashlib.sha256(expected).hexdigest()

    class Client:
        def head_object(self, **_kwargs):
            return {
                "ContentLength": len(expected),
                "Metadata": {
                    "sha256": digest,
                    "uploaded-by": "mvn-postgres-pitr",
                },
            }

        def get_object(self, **_kwargs):
            return {
                "ContentLength": len(expected),
                "Body": io.BytesIO(remote_body),
            }

    with pytest.raises(RuntimeError, match="content verification|exceeds"):
        pitr._verify_remote_object(
            Client(),
            bucket="private",
            key="pitr/mvn-api/wal/00000001/object",
            size_bytes=len(expected),
            sha256=digest,
        )


def test_large_artifact_uses_conditional_multipart_completion(
    monkeypatch, tmp_path
):
    payload = b"multipart-reviewed-content"
    source = tmp_path / "base.tar.gz"
    source.write_bytes(payload)
    config = pitr.PitrS3Config(
        "private", "https://example.invalid", "auto", "key", "secret", "pitr", "mvn-api"
    )
    key = "pitr/mvn-api/basebackups/id/base.tar.gz"

    class MissingObject(Exception):
        response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }

    class Client:
        def __init__(self):
            self.parts = []
            self.object = None
            self.metadata = None
            self.completed_condition = None
            self.aborted = False

        def head_object(self, **_kwargs):
            if self.object is None:
                raise MissingObject
            return {"ContentLength": len(self.object), "Metadata": self.metadata}

        def create_multipart_upload(self, **kwargs):
            self.metadata = kwargs["Metadata"]
            return {"UploadId": "upload-1"}

        def upload_part(self, **kwargs):
            assert kwargs["PartNumber"] == len(self.parts) + 1
            assert kwargs["ContentLength"] == len(kwargs["Body"])
            self.parts.append(kwargs["Body"])
            return {"ETag": f'"part-{len(self.parts)}"'}

        def complete_multipart_upload(self, **kwargs):
            self.completed_condition = kwargs["IfNoneMatch"]
            assert len(kwargs["MultipartUpload"]["Parts"]) == len(self.parts)
            self.object = b"".join(self.parts)

        def abort_multipart_upload(self, **_kwargs):
            self.aborted = True

        def get_object(self, **_kwargs):
            return {"ContentLength": len(self.object), "Body": io.BytesIO(self.object)}

    client = Client()
    monkeypatch.setattr(pitr, "MULTIPART_THRESHOLD_BYTES", 4)
    monkeypatch.setattr(pitr, "MULTIPART_PART_BYTES", 7)

    snapshot = pitr.upload_file(client, config, source, key, False)

    assert snapshot.sha256 == hashlib.sha256(payload).hexdigest()
    assert client.object == payload
    assert client.completed_condition == "*"
    assert client.aborted is False


def test_multipart_precondition_race_aborts_and_accepts_only_exact_winner(
    monkeypatch, tmp_path
):
    payload = b"winning-content"
    source = tmp_path / "base.tar.gz"
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    config = pitr.PitrS3Config(
        "private", "https://example.invalid", "auto", "key", "secret", "pitr", "mvn-api"
    )

    class MissingObject(Exception):
        response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }

    class PreconditionFailed(Exception):
        response = {
            "Error": {"Code": "PreconditionFailed"},
            "ResponseMetadata": {"HTTPStatusCode": 412},
        }

    class Client:
        head_calls = 0
        aborted = False

        def head_object(self, **_kwargs):
            self.head_calls += 1
            if self.head_calls == 1:
                raise MissingObject
            return {
                "ContentLength": len(payload),
                "Metadata": {
                    "sha256": digest,
                    "uploaded-by": "mvn-postgres-pitr",
                },
            }

        def create_multipart_upload(self, **_kwargs):
            return {"UploadId": "upload-race"}

        def upload_part(self, **kwargs):
            return {"ETag": f'"part-{kwargs["PartNumber"]}"'}

        def complete_multipart_upload(self, **kwargs):
            assert kwargs["IfNoneMatch"] == "*"
            raise PreconditionFailed

        def abort_multipart_upload(self, **_kwargs):
            self.aborted = True

        def get_object(self, **_kwargs):
            return {"ContentLength": len(payload), "Body": io.BytesIO(payload)}

    client = Client()
    monkeypatch.setattr(pitr, "MULTIPART_THRESHOLD_BYTES", 4)
    monkeypatch.setattr(pitr, "MULTIPART_PART_BYTES", 7)

    snapshot = pitr.upload_file(
        client,
        config,
        source,
        "pitr/mvn-api/basebackups/id/base.tar.gz",
        False,
    )

    assert snapshot.sha256 == digest
    assert client.aborted is True
