import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OLD_IMAGE = "ghcr.io/mvnby/air-api/backend:" + "1" * 40
NEW_IMAGE = "ghcr.io/mvnby/air-api/backend:" + "2" * 40
OTHER_IMAGE = "ghcr.io/mvnby/air-api/backend:" + "3" * 40


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _fake_environment(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    docker_log.touch()

    _executable(
        fake_bin / "flock",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    _executable(
        fake_bin / "curl",
        "#!/usr/bin/env bash\nprintf '{\"status\":\"ready\"}\\n'\n",
    )
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -u
printf '%s\n' "$*" >> "$DOCKER_LOG"
if [[ -n "${DOCKER_FAIL_MATCH:-}" && "$*" == *"${DOCKER_FAIL_MATCH}"* ]]; then
  exit 42
fi
if [[ "$*" == *"compose -f docker-compose.prod.yml"* && "$*" == *"ps --status running --services"* ]]; then
  printf '%s\n' "${DOCKER_PS_SERVICES:-app}"
elif [[ "$1 $2" == "image ls" ]]; then
  cat "${IMAGE_IDS_FILE:-/dev/null}"
elif [[ "$1 $2" == "image inspect" && "$*" == *"--format"* ]]; then
  printf '%s\n' "${DOCKER_IMAGE_CONTRACT:-directory-v1}"
elif [[ "$1 $2" == "ps -aq" && "$*" == *"ancestor=${RUNNING_IMAGE_ID:-__none__}"* ]]; then
  printf 'container-id\n'
fi
exit 0
""",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "DOCKER_LOG": str(docker_log),
            "GHCR_PAT": "test-token",
            "GITHUB_ACTOR": "test-user",
            "GOOGLE_OAUTH_TOKEN_REQUIRED": "false",
        }
    )
    return fake_bin, env, docker_log


def _project(tmp_path: Path, image: str = OLD_IMAGE) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "docker-compose.prod.yml").write_text(
        "services:\n"
        "  app:\n"
        "    image: ${BACKEND_IMAGE}\n"
        "    environment:\n"
        "      GOOGLE_TOKEN_FILE: /app/google-oauth/token.json\n"
        "    volumes:\n"
        "      - ./google-oauth:/app/google-oauth\n"
        "  bot:\n"
        "    image: ${BACKEND_IMAGE}\n",
        encoding="utf-8",
    )
    (project / ".env").write_text(f"KEEP=value\nBACKEND_IMAGE={image}\n", encoding="utf-8")
    return project


def _run(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(REPO_ROOT / script)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_deploy_changes_only_application_services_and_records_rollback(tmp_path):
    _, env, docker_log = _fake_environment(tmp_path)
    project = _project(tmp_path)
    env.update({"API_PROJECT_DIR": str(project), "BACKEND_IMAGE": NEW_IMAGE})

    result = _run("scripts/deploy.sh", env)

    assert result.returncode == 0, result.stderr
    calls = docker_log.read_text(encoding="utf-8")
    assert "compose -f docker-compose.prod.yml pull app bot" in calls
    assert "compose -f docker-compose.prod.yml run -T --rm --no-deps app alembic upgrade head" in calls
    assert "compose -f docker-compose.prod.yml up -d --no-deps --force-recreate app bot" in calls
    assert " pull db" not in calls
    assert " stop " not in calls
    assert "system prune" not in calls
    assert (project / ".previous-backend-image").read_text(encoding="utf-8").strip() == OLD_IMAGE
    assert f"BACKEND_IMAGE={NEW_IMAGE}" in (project / ".env").read_text(encoding="utf-8")


def test_failed_migration_does_not_activate_candidate(tmp_path):
    _, env, docker_log = _fake_environment(tmp_path)
    project = _project(tmp_path)
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "BACKEND_IMAGE": NEW_IMAGE,
            "DOCKER_FAIL_MATCH": "alembic upgrade head",
        }
    )

    result = _run("scripts/deploy.sh", env)

    assert result.returncode == 42
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(encoding="utf-8")
    assert " up -d " not in docker_log.read_text(encoding="utf-8")


def test_post_deploy_ops_never_changes_service_lifecycle(tmp_path):
    _, env, docker_log = _fake_environment(tmp_path)
    project = _project(tmp_path)
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "RUN_POST_DEPLOY_OPS": "true",
            "OPS_MODE": "report_only",
            "RUN_REPORT_LEGACY_LINKS": "false",
        }
    )

    result = _run("scripts/ops_post_deploy.sh", env)

    assert result.returncode == 0, result.stderr
    calls = docker_log.read_text(encoding="utf-8")
    assert "ps --status running --services" in calls
    assert " up " not in calls
    assert " pull " not in calls
    assert " stop " not in calls


def test_post_deploy_ops_fails_if_app_is_not_running(tmp_path):
    _, env, docker_log = _fake_environment(tmp_path)
    project = _project(tmp_path)
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "RUN_POST_DEPLOY_OPS": "true",
            "DOCKER_PS_SERVICES": "db",
        }
    )

    result = _run("scripts/ops_post_deploy.sh", env)

    assert result.returncode == 1
    assert "app is not running" in result.stdout
    assert " up " not in docker_log.read_text(encoding="utf-8")


def test_post_deploy_ops_executes_in_active_blue_green_slot(tmp_path):
    _, env, docker_log = _fake_environment(tmp_path)
    project = _project(tmp_path)
    (project / ".active-api-slot").write_text("green\n", encoding="utf-8")
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "RUN_POST_DEPLOY_OPS": "true",
            "OPS_MODE": "report_only",
            "DOCKER_PS_SERVICES": "app-green",
        }
    )

    result = _run("scripts/ops_post_deploy.sh", env)

    assert result.returncode == 0, result.stderr
    calls = docker_log.read_text(encoding="utf-8")
    assert "exec -T app-green sh -lc" in calls
    assert " up " not in calls


def test_deploy_rejects_mutable_image_tag_before_docker_calls(tmp_path):
    _, env, docker_log = _fake_environment(tmp_path)
    project = _project(tmp_path)
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "BACKEND_IMAGE": "ghcr.io/mvnby/air-api/backend:latest",
        }
    )

    result = _run("scripts/deploy.sh", env)

    assert result.returncode == 1
    assert "40-character Git SHA tag or sha256 digest" in result.stderr
    calls = docker_log.read_text(encoding="utf-8")
    assert "up -d" not in calls


def test_rollback_refuses_pre_directory_contract_image(tmp_path):
    _, env, _ = _fake_environment(tmp_path)
    project = _project(tmp_path, image=NEW_IMAGE)
    (project / ".previous-backend-image").write_text(OLD_IMAGE + "\n", encoding="utf-8")
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "CONFIRM_ROLLBACK": "true",
            "EXPECTED_CURRENT_IMAGE": NEW_IMAGE,
            "DOCKER_IMAGE_CONTRACT": "legacy-file-mount",
        }
    )

    result = _run("scripts/rollback_backend.sh", env)

    assert result.returncode != 0
    assert "cannot durably refresh Google OAuth" in result.stderr


def test_rollback_refuses_compose_without_exact_token_environment(tmp_path):
    _, env, _ = _fake_environment(tmp_path)
    project = _project(tmp_path, image=NEW_IMAGE)
    compose = project / "docker-compose.prod.yml"
    compose.write_text(
        compose.read_text(encoding="utf-8").replace(
            "      GOOGLE_TOKEN_FILE: /app/google-oauth/token.json\n",
            "",
        ),
        encoding="utf-8",
    )
    (project / ".previous-backend-image").write_text(OLD_IMAGE + "\n", encoding="utf-8")
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "CONFIRM_ROLLBACK": "true",
            "EXPECTED_CURRENT_IMAGE": NEW_IMAGE,
        }
    )

    result = _run("scripts/rollback_backend.sh", env)

    assert result.returncode != 0
    assert "does not provide the directory-v1" in result.stderr


def test_dockerfile_declares_directory_token_contract():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'org.mvn.google-oauth-token-contract="directory-v1"' in dockerfile


def test_automatic_rollback_is_noop_when_candidate_was_not_activated(tmp_path):
    _, env, docker_log = _fake_environment(tmp_path)
    project = _project(tmp_path)
    (project / ".previous-backend-image").write_text(OTHER_IMAGE + "\n", encoding="utf-8")
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "CONFIRM_ROLLBACK": "true",
            "EXPECTED_CURRENT_IMAGE": NEW_IMAGE,
        }
    )

    result = _run("scripts/rollback_backend.sh", env)

    assert result.returncode == 0, result.stderr
    assert "Candidate was not activated" in result.stdout
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(encoding="utf-8")
    assert docker_log.read_text(encoding="utf-8") == ""


def test_rollback_restores_previous_immutable_image(tmp_path):
    _, env, docker_log = _fake_environment(tmp_path)
    project = _project(tmp_path, image=NEW_IMAGE)
    (project / ".previous-backend-image").write_text(OLD_IMAGE + "\n", encoding="utf-8")
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "CONFIRM_ROLLBACK": "true",
            "EXPECTED_CURRENT_IMAGE": NEW_IMAGE,
        }
    )

    result = _run("scripts/rollback_backend.sh", env)

    assert result.returncode == 0, result.stderr
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(encoding="utf-8")
    assert (project / ".previous-backend-image").read_text(encoding="utf-8").strip() == NEW_IMAGE
    assert "up -d --no-deps --force-recreate app bot" in docker_log.read_text(encoding="utf-8")


def test_rollback_delegates_to_blue_green_when_active_slot_exists(tmp_path):
    _, env, docker_log = _fake_environment(tmp_path)
    project = _project(tmp_path, image=NEW_IMAGE)
    (project / ".previous-backend-image").write_text(OLD_IMAGE + "\n", encoding="utf-8")
    (project / ".active-api-slot").write_text("blue\n", encoding="utf-8")
    delegate_log = tmp_path / "delegate.log"
    delegate = tmp_path / "blue-green.sh"
    _executable(
        delegate,
        "#!/usr/bin/env bash\nprintf '%s|%s|%s\\n' \"$BACKEND_IMAGE\" \"$API_RUN_MIGRATIONS\" \"$API_DEPLOY_LOCK_ALREADY_HELD\" > \"$DELEGATE_LOG\"\n",
    )
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "CONFIRM_ROLLBACK": "true",
            "EXPECTED_CURRENT_IMAGE": NEW_IMAGE,
            "API_BLUE_GREEN_SCRIPT": str(delegate),
            "DELEGATE_LOG": str(delegate_log),
        }
    )

    result = _run("scripts/rollback_backend.sh", env)

    assert result.returncode == 0, result.stderr
    assert delegate_log.read_text(encoding="utf-8").strip() == f"{OLD_IMAGE}|false|true"
    calls = docker_log.read_text(encoding="utf-8")
    assert "google-oauth-token-contract" in calls
    assert "exec -T app-blue python3 -" in calls
    assert "up -d" not in calls


def test_rollback_probe_failure_reactivates_previous_blue_green_image(tmp_path):
    _, env, _ = _fake_environment(tmp_path)
    project = _project(tmp_path, image=NEW_IMAGE)
    (project / ".previous-backend-image").write_text(OLD_IMAGE + "\n", encoding="utf-8")
    (project / ".active-api-slot").write_text("blue\n", encoding="utf-8")
    delegate_log = tmp_path / "delegate.log"
    delegate = tmp_path / "blue-green.sh"
    _executable(
        delegate,
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$BACKEND_IMAGE\" >> \"$DELEGATE_LOG\"\n",
    )
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "CONFIRM_ROLLBACK": "true",
            "EXPECTED_CURRENT_IMAGE": NEW_IMAGE,
            "API_BLUE_GREEN_SCRIPT": str(delegate),
            "DELEGATE_LOG": str(delegate_log),
            "DOCKER_FAIL_MATCH": "exec -T app-blue python3 -",
        }
    )

    result = _run("scripts/rollback_backend.sh", env)

    assert result.returncode != 0
    assert delegate_log.read_text(encoding="utf-8").splitlines() == [
        OLD_IMAGE,
        NEW_IMAGE,
    ]
    assert f"BACKEND_IMAGE={NEW_IMAGE}" in (project / ".env").read_text(encoding="utf-8")


def test_rollback_reports_critical_when_probe_and_reactivation_both_fail(tmp_path):
    _, env, _ = _fake_environment(tmp_path)
    project = _project(tmp_path, image=NEW_IMAGE)
    (project / ".previous-backend-image").write_text(OLD_IMAGE + "\n", encoding="utf-8")
    (project / ".active-api-slot").write_text("blue\n", encoding="utf-8")
    delegate = tmp_path / "blue-green.sh"
    _executable(
        delegate,
        f"""#!/usr/bin/env bash
if [[ "$BACKEND_IMAGE" == "{NEW_IMAGE}" ]]; then
  exit 77
fi
exit 0
""",
    )
    env.update(
        {
            "API_PROJECT_DIR": str(project),
            "CONFIRM_ROLLBACK": "true",
            "EXPECTED_CURRENT_IMAGE": NEW_IMAGE,
            "API_BLUE_GREEN_SCRIPT": str(delegate),
            "DOCKER_FAIL_MATCH": "exec -T app-blue python3 -",
        }
    )

    result = _run("scripts/rollback_backend.sh", env)

    assert result.returncode == 90
    assert "CRITICAL" in result.stderr
    assert "could not be restored" in result.stderr


def test_rollback_probe_requires_durable_auth_and_atomic_directory_write():
    script = (REPO_ROOT / "scripts/rollback_backend.sh").read_text(encoding="utf-8")
    assert "google.auth_error is not None" in script
    assert 'status.get("persistence_ok") is not True' in script
    assert 'os.replace(temporary, probe_path)' in script
    assert "Google backup probe returned no backup objects" in script
    list_index = script.index("items = backup_service.list_backups(limit=1)")
    status_index = script.index("status = google.get_token_status()")
    persistence_index = script.index('status.get("persistence_ok") is not True')
    assert list_index < status_index < persistence_index


def test_prune_keeps_three_newest_and_every_container_image(tmp_path):
    _, env, docker_log = _fake_environment(tmp_path)
    image_ids = tmp_path / "image-ids"
    repository = "ghcr.io/mvnby/air-api/backend"
    image_ids.write_text(
        "\n".join(
            f"{repository} {image_id}"
            for image_id in (
                "sha256:new1",
                "sha256:new2",
                "sha256:new3",
                "sha256:old-running",
                "sha256:old",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    env.update(
        {
            "IMAGE_IDS_FILE": str(image_ids),
            "RUNNING_IMAGE_ID": "sha256:old-running",
        }
    )

    result = _run("scripts/prune_unused_docker_images.sh", env)

    assert result.returncode == 0, result.stderr
    calls = docker_log.read_text(encoding="utf-8")
    assert "image rm sha256:old" in calls
    assert "image rm sha256:old-running" not in calls
    assert "image rm sha256:new3" not in calls
    assert "image prune -f --filter until=168h" in calls
    assert "system prune" not in calls
