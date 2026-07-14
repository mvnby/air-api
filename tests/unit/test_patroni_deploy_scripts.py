import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATE = REPO_ROOT / "scripts/ha/run_patroni_migrations.sh"
DEPLOY = REPO_ROOT / "scripts/ha/deploy_patroni_api_node.sh"
CONFIGURE_ENV = REPO_ROOT / "scripts/ha/configure_patroni_replication_env.sh"
CONFIGURE_PITR = REPO_ROOT / "scripts/ha/configure_patroni_pitr_env.sh"
CONFIGURE_IMAGE = REPO_ROOT / "scripts/ha/configure_patroni_image_env.sh"
IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "4" * 64
PATRONI_IMAGE = "ghcr.io/mvnby/air-api/patroni@sha256:" + "5" * 64


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_migration_script_requires_primary_and_never_manages_database_service(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    command_log = tmp_path / "commands.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    _executable(
        fake_bin / "curl",
        "#!/usr/bin/env bash\nprintf '{\"state\":\"running\",\"role\":\"primary\"}\\n'\n",
    )
    _executable(
        fake_bin / "docker",
        '#!/usr/bin/env bash\nprintf "docker %s\\n" "$*" >> "$COMMAND_LOG"\n',
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "COMMAND_LOG": str(command_log),
            "API_PROJECT_DIR": str(project),
            "API_COMPOSE_FILE": "compose.yml",
            "BACKEND_IMAGE": IMAGE,
            "GOOGLE_OAUTH_TOKEN_REQUIRED": "false",
        }
    )

    result = subprocess.run(
        ["bash", str(MIGRATE)], env=env, text=True, capture_output=True, check=False
    )

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "pull app-blue" in commands
    assert "run -T --rm --no-deps app-blue alembic upgrade head" in commands
    assert "ensure_global_config_defaults.py" in commands
    assert " up " not in commands
    assert " db" not in commands


def test_deploy_and_migration_scripts_reject_unknown_running_patroni_role(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    command_log = tmp_path / "commands.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    _executable(
        fake_bin / "curl",
        "#!/usr/bin/env bash\nprintf '{\"state\":\"running\",\"role\":\"mystery\"}\\n'\n",
    )
    _executable(
        fake_bin / "docker",
        '#!/usr/bin/env bash\nprintf "docker %s\\n" "$*" >> "$COMMAND_LOG"\n',
    )
    base_env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "COMMAND_LOG": str(command_log),
        "API_PROJECT_DIR": str(project),
        "API_COMPOSE_FILE": "compose.yml",
        "BACKEND_IMAGE": IMAGE,
        "GOOGLE_OAUTH_TOKEN_REQUIRED": "false",
    }

    deploy = subprocess.run(
        ["bash", str(DEPLOY)],
        env={**base_env, "API_EXPECTED_PATRONI_ROLE": "standby"},
        text=True,
        capture_output=True,
        check=False,
    )
    migrate = subprocess.run(
        ["bash", str(MIGRATE)],
        env=base_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert deploy.returncode != 0
    assert migrate.returncode != 0
    assert "local Patroni API is unavailable" in deploy.stdout
    assert "local Patroni API is unavailable" in migrate.stdout
    assert not command_log.exists()


def test_node_deploy_keeps_migrations_separate_and_has_role_and_maintenance_fences():
    text = DEPLOY.read_text(encoding="utf-8")

    assert "API_EXPECTED_PATRONI_ROLE must be primary or standby" in text
    assert ".patroni-cutover-in-progress" in text
    assert "API_RUN_MIGRATIONS=false" in text
    assert '"${COMPOSE[@]}" stop bot' in text
    assert "standby image updated without enabling traffic" in text
    assert "alembic upgrade head" not in text
    assert 'up -d --no-deps --force-recreate "${active_service}"' in text
    assert "reconcile_standby_proxy" in text
    assert 'run -T --rm --no-deps "${PROXY_SERVICE}" nginx -t' in text
    assert 'up -d --no-deps "${PROXY_SERVICE}"' in text
    assert 'up -d --no-deps --force-recreate "${PROXY_SERVICE}"' in text
    assert "running proxy has stale mounts" in text
    assert "up -d db" not in text


def test_replication_env_updater_replaces_keys_atomically_and_preserves_mode(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_USER=postgres\n"
        "PATRONI_REPLICATION_USERNAME=old\n"
        "PATRONI_REPLICATION_PASSWORD=${invalid}\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)

    result = subprocess.run(
        ["bash", str(CONFIGURE_ENV)],
        env={**os.environ, "PATRONI_ENV_FILE": str(env_file)},
        input="a-secure-replication-password\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    text = env_file.read_text(encoding="utf-8")
    assert text.count("PATRONI_REPLICATION_USERNAME=") == 1
    assert text.count("PATRONI_REPLICATION_PASSWORD=") == 1
    assert "PATRONI_REPLICATION_USERNAME=mvn_replicator" in text
    assert "PATRONI_REPLICATION_PASSWORD=a-secure-replication-password" in text
    assert "${invalid}" not in text
    assert env_file.stat().st_mode & 0o777 == 0o600
    assert len(list(tmp_path.glob(".env.bak-patroni-*"))) == 1


def test_patroni_image_updater_requires_digest_and_preserves_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=postgres\nPATRONI_IMAGE=invalid\n", encoding="utf-8")
    env_file.chmod(0o600)

    result = subprocess.run(
        ["bash", str(CONFIGURE_IMAGE)],
        env={**os.environ, "PATRONI_ENV_FILE": str(env_file)},
        input=f"{PATRONI_IMAGE}\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert env_file.read_text(encoding="utf-8").count("PATRONI_IMAGE=") == 1
    assert f"PATRONI_IMAGE={PATRONI_IMAGE}" in env_file.read_text(encoding="utf-8")
    assert env_file.stat().st_mode & 0o777 == 0o600
    assert len(list(tmp_path.glob(".env.bak-patroni-image-*"))) == 1


def test_patroni_image_updater_rejects_mutable_or_foreign_images(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=postgres\n", encoding="utf-8")

    for image in (
        "ghcr.io/mvnby/air-api/patroni:latest",
        "ghcr.io/other/air-api/patroni@sha256:" + "5" * 64,
    ):
        result = subprocess.run(
            ["bash", str(CONFIGURE_IMAGE)],
            env={**os.environ, "PATRONI_ENV_FILE": str(env_file)},
            input=f"{image}\n",
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode != 0
        assert "immutable MVN Patroni GHCR digest" in result.stderr


def test_legacy_pitr_env_updater_is_disabled_without_mutating_files(tmp_path):
    app_env = tmp_path / ".env"
    systemd_env = tmp_path / "mvn-postgres-pitr.env"
    app_env.write_text(
        "POSTGRES_USER=postgres\nPOSTGRES_PITR_S3_BUCKET=old\n",
        encoding="utf-8",
    )
    app_env.chmod(0o600)
    original = app_env.read_text(encoding="utf-8")

    result = subprocess.run(
        ["bash", str(CONFIGURE_PITR)],
        env={
            **os.environ,
            "PATRONI_APP_ENV_FILE": str(app_env),
            "PATRONI_SYSTEMD_ENV_FILE": str(systemd_env),
            "PATRONI_PROJECT_DIR": "/opt/mvn-reserve",
        },
        input="POSTGRES_PITR_S3_SECRET_ACCESS_KEY=secret\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 64
    assert "permanently disabled" in result.stderr
    assert app_env.read_text(encoding="utf-8") == original
    assert not systemd_env.exists()
