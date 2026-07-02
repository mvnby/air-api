import importlib.util
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
