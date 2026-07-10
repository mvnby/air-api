import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATE = REPO_ROOT / "scripts/ha/run_patroni_migrations.sh"
DEPLOY = REPO_ROOT / "scripts/ha/deploy_patroni_api_node.sh"
IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "4" * 64


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


def test_node_deploy_keeps_migrations_separate_and_has_role_and_maintenance_fences():
    text = DEPLOY.read_text(encoding="utf-8")

    assert "API_EXPECTED_PATRONI_ROLE must be primary or standby" in text
    assert ".patroni-cutover-in-progress" in text
    assert "API_RUN_MIGRATIONS=false" in text
    assert '"${COMPOSE[@]}" stop bot' in text
    assert "standby image updated without enabling traffic" in text
    assert "alembic upgrade head" not in text
    assert 'up -d --no-deps --force-recreate "${active_service}"' in text
    assert "up -d db" not in text
