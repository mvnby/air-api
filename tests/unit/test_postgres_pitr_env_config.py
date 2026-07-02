import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ha/configure_postgres_pitr_env.py"


def _write_input_env(path: Path, *, bucket: str = "mvn-postgres-pitr") -> None:
    path.write_text(
        "\n".join(
            [
                "POSTGRES_PITR_CLUSTER=mvn-api",
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


def _run_configure(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-dir", str(tmp_path), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={},
    )


def test_configure_env_writes_backup_and_redacts_secret(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_USER=postgres\nPRODUCT_MEDIA_S3_BUCKET=public-media\n",
        encoding="utf-8",
    )
    input_file = tmp_path / "pitr.env"
    _write_input_env(input_file)

    result = _run_configure(tmp_path, "--input-env-file", str(input_file))

    assert result.returncode == 0, result.stderr
    env_text = env_file.read_text(encoding="utf-8")
    assert "POSTGRES_USER=postgres" in env_text
    assert "POSTGRES_PITR_CLUSTER=mvn-api" in env_text
    assert "POSTGRES_PITR_S3_BUCKET=mvn-postgres-pitr" in env_text
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=super-secret-key" in env_text
    assert "POSTGRES_PITR_ARCHIVE_MODE=off" in env_text
    assert "POSTGRES_PITR_ARCHIVE_TIMEOUT=300s" in env_text
    assert "super-secret-key" not in result.stdout
    assert "redacted" in result.stdout
    assert list(tmp_path.glob(".env.bak-pitr-*"))
    assert oct(os.stat(env_file).st_mode & 0o777) == "0o600"


def test_configure_env_refuses_public_media_bucket(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MEDIA_S3_BUCKET=public-media\n", encoding="utf-8")
    input_file = tmp_path / "pitr.env"
    _write_input_env(input_file, bucket="public-media")

    result = _run_configure(tmp_path, "--input-env-file", str(input_file))

    assert result.returncode != 0
    assert "must not reuse the public media bucket" in result.stderr
    assert "POSTGRES_PITR_S3_BUCKET" not in env_file.read_text(encoding="utf-8")


def test_configure_env_enable_archive_reuses_existing_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=postgres\n", encoding="utf-8")
    input_file = tmp_path / "pitr.env"
    _write_input_env(input_file)
    first = _run_configure(tmp_path, "--input-env-file", str(input_file))
    assert first.returncode == 0, first.stderr

    second = _run_configure(tmp_path, "--enable-archive")

    assert second.returncode == 0, second.stderr
    env_text = env_file.read_text(encoding="utf-8")
    assert "POSTGRES_PITR_ARCHIVE_MODE=on" in env_text
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=super-secret-key" in env_text
    assert "super-secret-key" not in second.stdout
    assert len(list(tmp_path.glob(".env.bak-pitr-*"))) >= 2


def test_configure_env_dry_run_does_not_write(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=postgres\n", encoding="utf-8")
    input_file = tmp_path / "pitr.env"
    _write_input_env(input_file)

    result = _run_configure(tmp_path, "--input-env-file", str(input_file), "--dry-run")

    assert result.returncode == 0, result.stderr
    assert env_file.read_text(encoding="utf-8") == "POSTGRES_USER=postgres\n"
    assert not list(tmp_path.glob(".env.bak-pitr-*"))
