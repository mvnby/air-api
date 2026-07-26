import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
NODE_DEPLOY = REPO_ROOT / "scripts/ha/deploy_patroni_api_node.sh"
CANDIDATE = REPO_ROOT / "scripts/ha/run_patroni_candidate_transaction.sh"
RECONCILE = REPO_ROOT / "scripts/reconcile_backend_compose_runtime.sh"
REMOTE = REPO_ROOT / "scripts/ha/run_patroni_node_remote.sh"
RELEASE_CONTRACT = (
    REPO_ROOT / "scripts/ha/communications_worker_release_contract.sh"
)
CANDIDATE_LIFECYCLE = (
    REPO_ROOT / "scripts/ha/patroni_communications_candidate_lifecycle.sh"
)
WORKFLOW = REPO_ROOT / ".github/workflows/deploy-api-patroni.yml"
OLD_IMAGE = "ghcr.io/mvnby/air-api/backend:" + "1" * 40
NEW_IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "2" * 64


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_node_deploy_keeps_api_cutover_separate_and_worker_dormant():
    text = NODE_DEPLOY.read_text(encoding="utf-8")
    contract = RELEASE_CONTRACT.read_text(encoding="utf-8")
    primary = text.index('bash "${BLUE_GREEN_SCRIPT}"')
    worker = text.index("deploy_communications_worker", primary)

    assert primary < worker
    assert '"${COMPOSE[@]}" stop "${COMMUNICATIONS_WORKER_SERVICE}"' in text
    assert '"${COMPOSE[@]}" pull "${COMMUNICATIONS_WORKER_SERVICE}"' in text
    assert 'communications_worker_start_controlled "${EXPECTED_ROLE}"' in text
    assert "communications_worker_clear_release_fence" in contract
    assert "communications_worker_set_release_fence" in contract
    assert '"${runtime}" == "${BACKEND_IMAGE}|true"' in contract
    assert "COMMUNICATIONS_WORKER_ENABLED" in contract
    assert "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE" in contract
    assert "must remain false during Phase 2A" in contract


def test_candidate_rollback_fences_worker_before_old_compose_and_image_restore():
    text = CANDIDATE.read_text(encoding="utf-8")
    lifecycle = CANDIDATE_LIFECYCLE.read_text(encoding="utf-8")
    recovery = text[text.index("reconcile_failed_deploy()") :]

    assert recovery.index("patroni_communications_fence_candidate") < recovery.index(
        "transaction cleanup"
    )
    assert "PREVIOUS_WORKER_RUNNING" in recovery
    assert 'recovery_services+=" ${COMMUNICATIONS_WORKER_SERVICE}"' in recovery
    assert 'API_DEPLOY_SERVICES="${recovery_services}"' in recovery
    assert 'patroni_communications_require_runtime "${CANDIDATE_FILE}"' in text
    assert 'transaction promote' in text
    assert 'patroni_communications_require_runtime "${CANONICAL_FILE}"' in text
    assert text.index('transaction promote') < text.index(
        'patroni_communications_require_runtime "${CANONICAL_FILE}"'
    )
    assert "patroni_communications_capture_previous()" in lifecycle
    assert "patroni_communications_fence_candidate()" in lifecycle
    assert "patroni_communications_fence_canonical()" in lifecycle
    assert "patroni_communications_capture_previous()" not in text


def test_reconcile_fences_worker_before_image_transition_and_restores_parity(
    tmp_path,
):
    project = tmp_path / "project"
    project.mkdir()
    env_file = project / ".env"
    env_file.write_text(f"BACKEND_IMAGE={OLD_IMAGE}\n", encoding="utf-8")
    fence_marker = project / ".ha-communications-worker-release-fenced"
    fence_marker.write_text(
        "fenced\n", encoding="utf-8"
    )
    fence_marker.chmod(0o600)
    (project / ".active-api-slot").write_text("blue\n", encoding="utf-8")
    (project / "compose.yml").write_text(
        "services:\n"
        "  app-blue:\n"
        "    image: ${BACKEND_IMAGE}\n"
        "  communications-worker:\n"
        "    image: ${BACKEND_IMAGE}\n"
        "    environment:\n"
        '      COMMUNICATIONS_WORKER_ENABLED: "false"\n'
        '      COMMUNICATIONS_WORKER_ALLOW_ALL_MODE: "false"\n',
        encoding="utf-8",
    )
    command_log = tmp_path / "commands.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    rendered = {
        "services": {
            "app-blue": {"image": NEW_IMAGE},
            "communications-worker": {
                "image": NEW_IMAGE,
                "environment": {
                    "COMMUNICATIONS_WORKER_ENABLED": "false",
                    "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE": "false",
                },
            },
        }
    }
    rendered_path = tmp_path / "rendered.json"
    rendered_path.write_text(json.dumps(rendered), encoding="utf-8")
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
current="$(sed -n 's/^BACKEND_IMAGE=//p' "$ENV_PATH" | tail -n 1)"
printf '%s|env=%s\n' "$*" "$current" >> "$COMMAND_LOG"
if [[ "$1" == "compose" && "$*" == *"config --format json"* ]]; then
  exec /bin/cat "$RENDERED_PATH"
fi
if [[ "$1" == "compose" && "$*" == *"config --services"* ]]; then
  printf 'app-blue\ncommunications-worker\n'
  exit 0
fi
if [[ "$1" == "compose" && "$*" == *"ps -q communications-worker"* ]]; then
  printf 'worker-container\n'
  exit 0
fi
if [[ "$1" == "inspect" ]]; then
  printf '%s|true\n' "$EXPECTED_IMAGE"
  exit 0
fi
if [[ "$1" == "compose" && "$*" == *"exec -T communications-worker"* ]]; then
  expected_role="${!#}"
  [[ "${RUNTIME_APP_ROLE:-primary}" == "$expected_role" ]]
  [[ "${RUNTIME_WORKER_ENABLED:-false}" == "false" ]]
  [[ "${RUNTIME_ALLOW_ALL_MODE:-false}" == "false" ]]
  exit 0
fi
exit 0
""",
    )
    _executable(fake_bin / "curl", "#!/usr/bin/env bash\nprintf '{\"status\":\"ok\"}\\n'\n")

    result = subprocess.run(
        ["bash", str(RECONCILE)],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "API_PROJECT_DIR": str(project),
            "API_COMPOSE_FILE": "compose.yml",
            "API_DEPLOY_SERVICES": "app communications-worker",
            "API_RECONCILE_BACKEND_IMAGE": NEW_IMAGE,
            "API_READY_URL": "http://127.0.0.1/health",
            "API_HEALTH_ATTEMPTS": "1",
            "ENV_PATH": str(env_file),
            "COMMAND_LOG": str(command_log),
            "RENDERED_PATH": str(rendered_path),
            "EXPECTED_IMAGE": NEW_IMAGE,
            "API_EXPECTED_PATRONI_ROLE": "primary",
            "API_DEPLOY_LOCK_FD": "9",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert env_file.read_text(encoding="utf-8") == f"BACKEND_IMAGE={NEW_IMAGE}\n"
    commands = command_log.read_text(encoding="utf-8").splitlines()
    stop_index = next(
        index
        for index, line in enumerate(commands)
        if "stop communications-worker" in line
    )
    up_index = next(
        index
        for index, line in enumerate(commands)
        if "up -d --no-deps --force-recreate app-blue" in line
    )
    assert commands[stop_index].endswith(f"env={OLD_IMAGE}")
    assert commands[up_index].endswith(f"env={NEW_IMAGE}")
    assert stop_index < up_index
    assert any("ps -q communications-worker" in line for line in commands)
    assert any(line.startswith("inspect ") for line in commands)
    assert any("exec -T communications-worker" in line for line in commands)
    assert not (project / ".ha-communications-worker-release-fenced").exists()


def test_reconcile_verify_rejects_and_stops_stale_fenced_worker(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text(f"BACKEND_IMAGE={NEW_IMAGE}\n", encoding="utf-8")
    (project / "compose.yml").write_text(
        "services:\n"
        "  communications-worker:\n"
        "    image: ${BACKEND_IMAGE}\n"
        "    environment:\n"
        '      COMMUNICATIONS_WORKER_ENABLED: "false"\n'
        '      COMMUNICATIONS_WORKER_ALLOW_ALL_MODE: "false"\n',
        encoding="utf-8",
    )
    marker = project / ".ha-communications-worker-release-fenced"
    marker.write_text("fenced\n", encoding="utf-8")
    marker.chmod(0o600)
    command_log = tmp_path / "commands.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$COMMAND_LOG"
if [[ "$1" == "compose" && "$*" == *"config --services"* ]]; then
  printf 'communications-worker\n'
elif [[ "$1" == "compose" && "$*" == *"config --format json"* ]]; then
  printf '%s\n' "$RENDERED_CONFIG"
elif [[ "$1" == "compose" && "$*" == *"stop communications-worker"* ]]; then
  exit 0
else
  exit 91
fi
""",
    )
    rendered = json.dumps(
        {
            "services": {
                "communications-worker": {
                    "image": NEW_IMAGE,
                    "environment": {
                        "COMMUNICATIONS_WORKER_ENABLED": "false",
                        "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE": "false",
                    },
                }
            }
        }
    )

    result = subprocess.run(
        ["bash", str(RECONCILE)],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "API_PROJECT_DIR": str(project),
            "API_COMPOSE_FILE": "compose.yml",
            "API_DEPLOY_SERVICES": "communications-worker",
            "API_RECONCILE_OPERATION": "verify",
            "API_RECONCILE_BACKEND_IMAGE": NEW_IMAGE,
            "API_EXPECTED_PATRONI_ROLE": "primary",
            "COMMAND_LOG": str(command_log),
            "RENDERED_CONFIG": rendered,
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "communications worker release fence remains latched" in result.stderr
    assert marker.read_text(encoding="utf-8") == "fenced\n"
    assert "stop communications-worker" in command_log.read_text(encoding="utf-8")


def test_workflow_verifies_release_parity_on_every_deployed_node():
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    jobs = workflow["jobs"]

    for job_name in (
        "deploy-replica-reserve",
        "deploy-replica-api",
        "deploy-primary-api",
        "deploy-primary-reserve",
    ):
        run = jobs[job_name]["steps"][-1]["run"]
        assert run == (
            "bash scripts/ha/run_patroni_node_remote.sh deploy "
            "&& bash scripts/ha/run_patroni_node_remote.sh verify"
        )
    final = jobs["deployment-complete"]["steps"][-1]["run"]
    assert "dormant worker release verified on both nodes" in final


def test_remote_verify_requires_exact_images_running_and_false_phase2a_gates():
    text = REMOTE.read_text(encoding="utf-8")
    verify = text[text.index('if [[ "${OPERATION}" == "verify" ]]') :]

    assert "COMMUNICATIONS_WORKER_ENABLED" in verify
    assert "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE" in verify
    assert "worker.get(\"image\") != expected_image" in verify
    assert "app.get(\"image\") != expected_image" in verify
    assert "communications-worker" in verify
    assert "{{.Config.Image}}|{{.State.Running}}" in verify
    assert "exec -T communications-worker" in verify
    assert "APP_ROLE" in verify
    assert "NRestarts" in verify
    assert ".ha-communications-worker-release-fenced" in verify
    assert "test ! -L ${CANONICAL_REMOTE_COMPOSE_FILE}" in verify
    assert "API/worker parity confirmed" in verify
    assert "GHCR_PAT" not in verify.split(
        'ssh "${SSH_OPTS[@]}" "${REMOTE}" \\\n'
        '  "test -d', 1
    )[0]


@pytest.mark.parametrize(
    (
        "runtime_role",
        "runtime_enabled",
        "restart_drift",
        "stale_marker",
        "canary_result",
        "final_role_flip",
        "expected_code",
    ),
    [
        ("primary", "false", "false", False, "verified", "false", 0),
        ("primary", "false", "false", False, "changed", "false", 0),
        ("primary", "false", "false", False, "deferred_once", "false", 0),
        ("standby", "false", "false", False, "verified", "false", 1),
        ("primary", "true", "false", False, "verified", "false", 1),
        ("primary", "false", "true", False, "verified", "false", 1),
        ("primary", "false", "false", True, "verified", "false", 1),
        ("primary", "false", "false", False, "failed", "false", 1),
        ("primary", "false", "false", False, "empty", "false", 1),
        ("primary", "false", "false", False, "duplicate", "false", 1),
        ("primary", "false", "false", False, "warning", "false", 1),
        ("primary", "false", "false", False, "wrong_changed_role", "false", 1),
        ("primary", "false", "false", False, "always_deferred", "false", 1),
        ("primary", "false", "false", False, "verified", "true", 1),
    ],
)
def test_remote_verify_path_executes_against_canonical_compose(
    tmp_path,
    runtime_role,
    runtime_enabled,
    restart_drift,
    stale_marker,
    canary_result,
    final_role_flip,
    expected_code,
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "docker-compose.patroni.yml").write_text(
        "services:\n"
        "  app:\n"
        "    image: ${BACKEND_IMAGE}\n"
        "  communications-worker:\n"
        "    image: ${BACKEND_IMAGE}\n",
        encoding="utf-8",
    )
    if stale_marker:
        (project / ".ha-communications-worker-release-fenced").write_text(
            "fenced\n", encoding="utf-8"
        )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(
        fake_bin / "ssh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'remote_command="${!#}"\n'
        'bash -c "${remote_command}"\n',
    )
    curl_count = tmp_path / "curl-count"
    _executable(
        fake_bin / "curl",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'count=0; [[ ! -f "$CURL_COUNT" ]] || count="$(cat "$CURL_COUNT")"\n'
        'count=$((count + 1)); printf "%s\\n" "$count" > "$CURL_COUNT"\n'
        'role=primary\n'
        'if [[ "$FINAL_ROLE_FLIP" == "true" && "$count" -gt 1 ]]; then role=standby; fi\n'
        'printf \'{"state":"running","role":"%s"}\\n\' "$role"\n',
    )
    rendered = json.dumps(
        {
            "services": {
                "app": {"image": NEW_IMAGE},
                "communications-worker": {
                    "image": NEW_IMAGE,
                    "environment": {
                        "COMMUNICATIONS_WORKER_ENABLED": "false",
                        "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE": "false",
                    },
                },
            }
        }
    )
    _executable(
        fake_bin / "docker",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf "%s\\n" "$*" >> "$REMOTE_DOCKER_LOG"\n'
        'if [[ "$1" == "compose" && "$*" == *"config --format json"* ]]; then\n'
        f"  printf '%s\\n' {repr(rendered)}\n"
        'elif [[ "$1" == "compose" && "$*" == *"ps -q app"* ]]; then\n'
        "  printf 'app-container\\n'\n"
        'elif [[ "$1" == "compose" && "$*" == *"ps -q communications-worker"* ]]; then\n'
        "  printf 'worker-container\\n'\n"
            'elif [[ "$1" == "inspect" ]]; then\n'
            f"  printf '%s|true\\n' {repr(NEW_IMAGE)}\n"
        'elif [[ "$1" == "compose" && "$*" == *"exec -T communications-worker"* ]]; then\n'
        '  expected_role="${!#}"\n'
        '  if [[ "$RUNTIME_APP_ROLE" != "$expected_role" '
        '|| "$RUNTIME_WORKER_ENABLED" != "false" '
        '|| "$RUNTIME_ALLOW_ALL_MODE" != "false" ]]; then exit 1; fi\n'
            "else\n"
            "  exit 91\n"
            "fi\n",
        )
    systemctl_count = tmp_path / "systemctl-count"
    remote_docker_log = tmp_path / "remote-docker.log"
    _executable(
        fake_bin / "systemctl",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$1" == "is-active" ]]; then exit 0; fi\n'
        'if [[ "$*" == *"--property=MainPID"* ]]; then printf "123\\n"; exit 0; fi\n'
        'if [[ "$*" == *"--property=NRestarts"* ]]; then\n'
        '  count=0; [[ ! -f "$SYSTEMCTL_COUNT" ]] || count="$(cat "$SYSTEMCTL_COUNT")"\n'
        '  count=$((count + 1)); printf "%s\\n" "$count" > "$SYSTEMCTL_COUNT"\n'
        '  if [[ "$SYSTEMCTL_RESTART_DRIFT" == "true" && "$count" -gt 1 ]]; then\n'
        '    printf "1\\n"\n'
        '  else\n'
        '    printf "0\\n"\n'
        '  fi\n'
        "  exit 0\n"
        "fi\n"
        "exit 91\n",
    )
    _executable(fake_bin / "sleep", "#!/usr/bin/env bash\nexit 0\n")
    canary_count = tmp_path / "canary-count"
    _executable(
        fake_bin / "timeout",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'count=0; [[ ! -f "$CANARY_COUNT" ]] || count="$(cat "$CANARY_COUNT")"\n'
        'count=$((count + 1)); printf "%s\\n" "$count" > "$CANARY_COUNT"\n'
        'if [[ "$CANARY_RESULT" == "failed" ]]; then\n'
        '  printf "patroni_role_agent_status=failed role=primary error=hidden\\n"\n'
        "  exit 1\n"
        "fi\n"
        'if [[ "$CANARY_RESULT" == "empty" ]]; then exit 0; fi\n'
        'if [[ "$CANARY_RESULT" == "warning" ]]; then\n'
        '  printf "patroni_role_agent_status=warning patroni_unavailable=hidden\\n"\n'
        '  printf "patroni_role_agent_once_status=verified role=primary\\n"\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$CANARY_RESULT" == "duplicate" ]]; then\n'
        '  printf "patroni_role_agent_once_status=verified role=primary\\n"\n'
        '  printf "patroni_role_agent_once_status=verified role=primary\\n"\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$CANARY_RESULT" == "always_deferred" '
        '|| ( "$CANARY_RESULT" == "deferred_once" && "$count" -eq 1 ) ]]; then\n'
        '  printf "patroni_role_agent_status=deferred '
        'reason=deployment_lock_busy\\n"\n'
        "  exit 75\n"
        "fi\n"
        'if [[ "$CANARY_RESULT" == "changed" ]]; then\n'
        '  printf "patroni_role_agent_status=reconciled role=primary '
        'app_service=app reasons=communications_worker_role_drift '
        'actions=recreate_communications_worker\\n"\n'
        "fi\n"
        'if [[ "$CANARY_RESULT" == "wrong_changed_role" ]]; then\n'
        '  printf "patroni_role_agent_status=reconciled role=standby '
        'app_service=app reasons=role_state actions=write_role_state\\n"\n'
        "fi\n"
        'printf "patroni_role_agent_once_status=verified role=primary\\n"\n',
    )

    result = subprocess.run(
        ["bash", str(REMOTE), "verify"],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "API_NODE_HOST": "example.invalid",
            "API_NODE_USER": "deploy",
            "API_NODE_PROJECT_DIR": str(project),
            "API_NODE_SSH_HOST_KEY_SOURCE": str(
                REPO_ROOT / "deploy/ha/security/mvn-api-ssh-host-key.pub"
            ),
            "API_EXPECTED_PATRONI_ROLE": "primary",
            "SSH_PRIVATE_KEY": "test-private-key",
            "BACKEND_IMAGE": NEW_IMAGE,
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_RUN_ID": "verify-test",
            "GITHUB_JOB": "verify",
            "API_PITR_MAINTENANCE_MARKER": str(tmp_path / "absent-maintenance"),
            "RUNTIME_APP_ROLE": runtime_role,
            "RUNTIME_WORKER_ENABLED": runtime_enabled,
            "RUNTIME_ALLOW_ALL_MODE": "false",
            "SYSTEMCTL_RESTART_DRIFT": restart_drift,
            "SYSTEMCTL_COUNT": str(systemctl_count),
            "REMOTE_DOCKER_LOG": str(remote_docker_log),
            "CANARY_RESULT": canary_result,
            "CANARY_COUNT": str(canary_count),
            "FINAL_ROLE_FLIP": final_role_flip,
            "CURL_COUNT": str(curl_count),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == expected_code, result.stderr
    if expected_code == 0:
        assert "API/worker parity confirmed" in result.stdout
    else:
        assert "API/worker parity confirmed" not in result.stdout
        assert "error=hidden" not in result.stdout + result.stderr


def test_release_contract_never_materializes_effective_environment():
    paths = (
        NODE_DEPLOY,
        CANDIDATE,
        RECONCILE,
        RELEASE_CONTRACT,
        CANDIDATE_LIFECYCLE,
        REMOTE,
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "communications-worker-compose" not in combined
    assert "config --format json >" not in combined
    assert "config --services" in RELEASE_CONTRACT.read_text(encoding="utf-8")
    assert 'grep -Fxq "${COMMUNICATIONS_WORKER_SERVICE}"' in (
        RELEASE_CONTRACT.read_text(encoding="utf-8")
    )
    assert RELEASE_CONTRACT.as_posix() not in combined
    assert "communications_worker_release_contract.sh" in REMOTE.read_text(
        encoding="utf-8"
    )
    assert "patroni_communications_candidate_lifecycle.sh" in REMOTE.read_text(
        encoding="utf-8"
    )
    assert len(CANDIDATE.read_text(encoding="utf-8").splitlines()) <= 650
