import hashlib
import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ha/configure_postgres_pitr_env.py"


def _write_input_env(
    path: Path,
    *,
    bucket: str = "mvn-postgres-pitr",
    cluster: str = "mvn-api",
) -> None:
    path.write_text(
        "\n".join(
            [
                f"POSTGRES_PITR_CLUSTER={cluster}",
                f"POSTGRES_PITR_S3_BUCKET={bucket}",
                "POSTGRES_PITR_S3_ENDPOINT_URL=https://account-id.r2.cloudflarestorage.com",
                "POSTGRES_PITR_S3_REGION=auto",
                "POSTGRES_PITR_S3_ACCESS_KEY_ID=access-key-id",
                "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=super-secret-key",
                "POSTGRES_PITR_S3_KEY_PREFIX=postgres/pitr",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _destination_fingerprint(bucket: str = "mvn-postgres-pitr") -> str:
    destination = "\n".join(
        (
            bucket,
            "https://account-id.r2.cloudflarestorage.com",
            "auto",
            "postgres/pitr",
            "",
        )
    )
    return hashlib.sha256(destination.encode()).hexdigest()


def _run_configure(
    tmp_path: Path,
    *args: str,
    destination_bucket: str = "mvn-postgres-pitr",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-dir",
            str(tmp_path),
            "--expected-destination-fingerprint",
            _destination_fingerprint(destination_bucket),
            *args,
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={},
    )


def test_configure_env_splits_secrets_and_redacts_output(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_USER=postgres\nPRODUCT_MEDIA_S3_BUCKET=public-media\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    input_file = tmp_path / "pitr.env"
    _write_input_env(input_file)

    result = _run_configure(tmp_path, "--input-env-file", str(input_file))

    assert result.returncode == 0, result.stderr
    env_text = env_file.read_text(encoding="utf-8")
    assert "POSTGRES_USER=postgres" in env_text
    assert "POSTGRES_PITR_CLUSTER" not in env_text
    assert "POSTGRES_PITR_S3_BUCKET" not in env_text
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY" not in env_text
    assert "POSTGRES_PITR_ARCHIVE_MODE=off" in env_text
    assert "POSTGRES_PITR_ARCHIVE_TIMEOUT=300s" in env_text
    secrets_file = tmp_path / ".mvn-postgres-pitr.secrets.env"
    secrets_text = secrets_file.read_text(encoding="utf-8")
    assert "POSTGRES_PITR_CLUSTER=mvn-api" in secrets_text
    assert "POSTGRES_PITR_S3_BUCKET=mvn-postgres-pitr" in secrets_text
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=super-secret-key" in secrets_text
    assert "super-secret-key" not in result.stdout
    assert "redacted" in result.stdout
    assert not list(tmp_path.glob(".env.bak-pitr-*"))
    assert oct(os.stat(env_file).st_mode & 0o777) == "0o600"
    assert oct(os.stat(secrets_file).st_mode & 0o777) == "0o600"
    assert not list((tmp_path / ".mvn-postgres-pitr-transactions").iterdir())


def test_configure_env_refuses_public_media_bucket(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MEDIA_S3_BUCKET=public-media\n", encoding="utf-8")
    env_file.chmod(0o600)
    input_file = tmp_path / "pitr.env"
    _write_input_env(input_file, bucket="public-media")

    result = _run_configure(
        tmp_path,
        "--input-env-file",
        str(input_file),
        destination_bucket="public-media",
    )

    assert result.returncode != 0
    assert "must not reuse the public media bucket" in result.stderr
    assert "POSTGRES_PITR_S3_BUCKET" not in env_file.read_text(encoding="utf-8")


def test_configure_env_refuses_physical_node_namespace(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=postgres\n", encoding="utf-8")
    env_file.chmod(0o600)
    input_file = tmp_path / "pitr.env"
    _write_input_env(input_file, cluster="zakup")

    result = _run_configure(tmp_path, "--input-env-file", str(input_file))

    assert result.returncode != 0
    assert "logical namespace" in result.stderr


def test_configure_env_enable_archive_reuses_existing_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=postgres\n", encoding="utf-8")
    env_file.chmod(0o600)
    input_file = tmp_path / "pitr.env"
    _write_input_env(input_file)
    first = _run_configure(tmp_path, "--input-env-file", str(input_file))
    assert first.returncode == 0, first.stderr

    second = _run_configure(tmp_path, "--enable-archive")

    assert second.returncode == 0, second.stderr
    env_text = env_file.read_text(encoding="utf-8")
    assert "POSTGRES_PITR_ARCHIVE_MODE=on" in env_text
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY" not in env_text
    secrets_text = (tmp_path / ".mvn-postgres-pitr.secrets.env").read_text(
        encoding="utf-8"
    )
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=super-secret-key" in secrets_text
    assert "super-secret-key" not in second.stdout
    assert not list(tmp_path.glob(".env.bak-pitr-*"))


def test_configure_env_dry_run_does_not_write(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=postgres\n", encoding="utf-8")
    env_file.chmod(0o600)
    input_file = tmp_path / "pitr.env"
    _write_input_env(input_file)

    result = _run_configure(tmp_path, "--input-env-file", str(input_file), "--dry-run")

    assert result.returncode == 0, result.stderr
    assert env_file.read_text(encoding="utf-8") == "POSTGRES_USER=postgres\n"
    assert not list(tmp_path.glob(".env.bak-pitr-*"))
    assert not (tmp_path / ".mvn-postgres-pitr.secrets.env").exists()
