import copy
import json
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSACTION = REPO_ROOT / "scripts/compose_candidate_transaction.sh"
PATRONI_RUNNER = REPO_ROOT / "scripts/ha/run_patroni_candidate_transaction.sh"
PREVIOUS_IMAGE = "ghcr.io/mvnby/air-api/backend:" + "1" * 40
CANDIDATE_IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "2" * 64
DB_CONTRACT_HELPER = REPO_ROOT / "scripts/ha/patroni_compose_db_contract.py"
DEPLOY_LOCK_HELPER = REPO_ROOT / "scripts/ha/safe_deploy_lock.py"


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _compose_pair(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "compose.yml").write_text(
        "services:\n  app:\n    volumes:\n      - ./token.json:/app/token.json\n",
        encoding="utf-8",
    )
    (project / "compose.yml.candidate").write_text(
        "services:\n  app:\n    volumes:\n      - ./google-oauth:/app/google-oauth\n",
        encoding="utf-8",
    )
    return project


def _db_compose_config() -> dict:
    return {
        "name": "mvn-api",
        "services": {
            "db": {
                "image": "${PATRONI_IMAGE:?set immutable PATRONI_IMAGE}",
                "networks": {"default": None},
                "volumes": [
                    {
                        "source": "postgres_data",
                        "target": "/var/lib/postgresql/data",
                        "type": "volume",
                        "volume": {},
                    }
                ],
            }
        },
        "networks": {"default": {"name": "mvn-api_default"}},
        "volumes": {
            "postgres_data": {
                "external": True,
                "name": "air-api_postgres_data",
            }
        },
    }


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _patroni_runner_env(
    tmp_path: Path,
    child_exit: int,
    *,
    current_role: str = "primary",
    expected_role: str = "primary",
    discover_previous: bool = False,
) -> tuple[dict[str, str], Path]:
    project = _compose_pair(tmp_path)
    if discover_previous:
        (project / ".active-api-slot").write_text("green\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    command_log = tmp_path / "patroni-commands.log"
    command_log.touch()
    systemctl_log = tmp_path / "systemctl.log"
    systemctl_log.touch()
    systemctl_state = tmp_path / "systemctl-state"
    systemctl_state.write_text("active\n", encoding="utf-8")
    canonical_contract = tmp_path / "canonical-contract.json"
    candidate_contract = tmp_path / "candidate-contract.json"
    _write_json(canonical_contract, _db_compose_config())
    _write_json(candidate_contract, copy.deepcopy(_db_compose_config()))
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$PATRONI_COMMAND_LOG"
if [[ "$1" == "compose" && "$*" == *" config --services" ]]; then
  printf 'app\n'
  if [[ "$*" == *"compose.yml.candidate"* \
    && "${FAKE_CANDIDATE_WORKER_SUPPORTED:-false}" == "true" ]]; then
    printf 'communications-worker\n'
  elif [[ "$*" != *"compose.yml.candidate"* \
    && "${FAKE_CANONICAL_WORKER_SUPPORTED:-false}" == "true" ]]; then
    printf 'communications-worker\n'
  fi
elif [[ "$1" == "compose" && "$*" == *" config --format json" ]]; then
  printf '{"name":"air-api","services":{"communications-worker":{"image":"%s","environment":{"COMMUNICATIONS_WORKER_ENABLED":"false","COMMUNICATIONS_WORKER_ALLOW_ALL_MODE":"false"}}}}\n' \
    "${BACKEND_IMAGE:-$EXPECTED_PREVIOUS_IMAGE}"
elif [[ "$1" == "compose" && "$*" == *" config --no-env-resolution --no-interpolate --format json" ]]; then
  if [[ "$*" == *"compose.yml.candidate"* ]]; then
    config_path="$CANDIDATE_DB_CONTRACT"
    if [[ -e "$DEPLOY_CHILD_RAN" && -n "${CANDIDATE_DB_CONTRACT_AFTER_DEPLOY:-}" ]]; then
      config_path="$CANDIDATE_DB_CONTRACT_AFTER_DEPLOY"
    fi
  else
    config_path="$CANONICAL_DB_CONTRACT"
  fi
  exec /bin/cat "$config_path"
elif [[ "$1" == "compose" && "$*" == *" ps -q app-green" ]]; then
  printf 'active-green-container\n'
elif [[ "$1" == "inspect" && "$*" == *" active-green-container" ]]; then
  printf '%s\n' "$EXPECTED_PREVIOUS_IMAGE"
elif [[ "$1" == "compose" && "$*" == *" ps --status running -q communications-worker" ]]; then
  [[ ! -f "${WORKER_RUNTIME_STATE:-}" ]] || printf '%064d\n' 0
elif [[ "$1" == "compose" && "$*" == *" ps -q communications-worker" ]]; then
  [[ ! -f "${WORKER_RUNTIME_STATE:-}" ]] || printf '%064d\n' 0
elif [[ "$1" == "inspect" && "$*" == *"$(printf '%064d' 0)"* ]]; then
  printf '%s|true\n' "$EXPECTED_PREVIOUS_IMAGE"
elif [[ "$1" == "compose" && "$*" == *" stop app app-blue app-green bot" ]]; then
  exit 0
elif [[ "$1" == "compose" && "$*" == *" ps -a -q api-proxy" ]]; then
  if [[ "${PROXY_PREVIOUS_RUNTIME_STATE:-absent}" != "absent" ]]; then
    printf 'proxy-container\n'
  fi
elif [[ "$1" == "inspect" && "$*" == *"proxy-container"* && "$*" == *"State.Running"* ]]; then
  [[ "${PROXY_PREVIOUS_RUNTIME_STATE:-absent}" == "running" ]] && printf 'true\n' || printf 'false\n'
elif [[ "$1" == "compose" && "$*" == *"compose.yml.candidate"* \
  && "$*" == *" stop communications-worker" ]]; then
  if [[ "${FAIL_CANDIDATE_WORKER_STOP:-false}" == "true" ]]; then exit 1; fi
  rm -f -- "${WORKER_RUNTIME_STATE:-}"
elif [[ "$1" == "compose" && "$*" == *" stop communications-worker" ]]; then
  rm -f -- "${WORKER_RUNTIME_STATE:-}"
elif [[ "$1" == "docker-never" ]]; then
  exit 91
elif [[ "$1" == "ps" && "$*" == *"label=com.docker.compose.project=air-api"* \
  && "$*" == *"label=com.docker.compose.service=communications-worker"* ]]; then
  [[ ! -f "${WORKER_RUNTIME_STATE:-}" ]] || printf '%064d\n' 0
elif [[ "$1" == "rm" && "$*" == *"$(printf '%064d' 0)"* ]]; then
  rm -f -- "$WORKER_RUNTIME_STATE"
elif [[ "$1" == "compose" && "$*" == *" up -d --no-deps --force-recreate --wait --wait-timeout 60 api-proxy" ]]; then
  if [[ -n "${PROXY_RUNTIME_CONFIG:-}" ]]; then
    cp "$API_PROXY_CONFIG_FILE" "$PROXY_RUNTIME_CONFIG"
  fi
  exit 0
elif [[ "$1" == "compose" && "$*" == *" exec -T api-proxy nginx -t" ]]; then
  exit 0
elif [[ "$1" == "compose" && "$*" == *" rm -s -f api-proxy" ]]; then
  [[ -z "${PROXY_RUNTIME_CONFIG:-}" ]] || rm -f "$PROXY_RUNTIME_CONFIG"
  exit 0
elif [[ "$1" == "compose" && "$*" == *" stop api-proxy" ]]; then
  exit 0
elif [[ "$1" == "compose" && "$*" == *" ps --status running -q api-proxy" ]]; then
  [[ "${PROXY_PREVIOUS_RUNTIME_STATE:-absent}" == "running" ]] && printf 'proxy-container\n' || true
  exit 0
else
  exit 91
fi
""",
    )
    _executable(
        fake_bin / "install",
        """#!/usr/bin/env bash
set -euo pipefail
count=0
if [[ -f "$INSTALL_COUNT" ]]; then count="$(cat "$INSTALL_COUNT")"; fi
count=$((count + 1))
printf '%s\n' "$count" > "$INSTALL_COUNT"
printf '%s\n' "${!#}" >> "$INSTALL_LOG"
if [[ "$count" -eq "${FAIL_INSTALL_NUMBER:-0}" ]]; then exit 48; fi
exec /usr/bin/install "$@"
""",
    )
    _executable(
        fake_bin / "cp",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s|%s\n' "${@: -2:1}" "${@: -1}" >> "$CP_LOG"
if [[ -n "${FAIL_RESTORE_LABEL:-}" \
  && "${@: -2:1}" == *".patroni-${FAIL_RESTORE_LABEL}.backup."* ]]; then
  exit 49
fi
exec /bin/cp "$@"
""",
    )
    _executable(
        fake_bin / "systemctl",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$SYSTEMCTL_LOG"
case "$1" in
  restart)
    count=0
    if [[ -f "$SYSTEMCTL_RESTART_COUNT" ]]; then
      count="$(cat "$SYSTEMCTL_RESTART_COUNT")"
    fi
    count=$((count + 1))
    printf '%s\n' "$count" > "$SYSTEMCTL_RESTART_COUNT"
    if [[ "$count" -eq "${SYSTEMCTL_FAIL_RESTART_NUMBER:-0}" ]]; then
      printf 'inactive\n' > "$SYSTEMCTL_STATE"
      exit 47
    fi
    printf 'active\n' > "$SYSTEMCTL_STATE"
    ;;
  start)
    printf 'active\n' > "$SYSTEMCTL_STATE"
    ;;
  stop)
    printf 'inactive\n' > "$SYSTEMCTL_STATE"
    ;;
  is-active)
    [[ "$(cat "$SYSTEMCTL_STATE")" == "active" ]]
    ;;
esac
""",
    )
    child = tmp_path / "deploy-child.sh"
    _executable(
        child,
        f'''#!/usr/bin/env bash
set -euo pipefail
grep -Fq '/app/token.json' "$API_PROJECT_DIR/compose.yml"
printf "%s|%s\n" "$API_COMPOSE_FILE" "${{API_DEPLOY_LOCK_FD:-}}" > "$CHILD_LOG"
if [[ -n "${{PROXY_RUNTIME_CONFIG:-}}" ]]; then
  cp "$API_PROXY_CONFIG_FILE" "$PROXY_RUNTIME_CONFIG"
fi
: > "$DEPLOY_CHILD_RAN"
exit {child_exit}
''',
    )
    role_agent = tmp_path / "role-agent.py"
    role_agent.write_text("#!/usr/bin/env python3\n# new role agent\n", encoding="utf-8")
    role_compose_runtime = tmp_path / "patroni-compose-runtime.py"
    role_compose_runtime.write_text("# new compose runtime\n", encoding="utf-8")
    role_agent_config = tmp_path / "patroni-role-agent-config.py"
    role_agent_config.write_text("# new role agent config\n", encoding="utf-8")
    role_identity = tmp_path / "patroni-local-identity.py"
    role_identity.write_text("# new identity helper\n", encoding="utf-8")
    role_unit = tmp_path / "mvn-patroni-role-agent.service"
    role_unit.write_text("[Service]\nExecStart=/new-role-agent\n", encoding="utf-8")
    reconcile = tmp_path / "reconcile.sh"
    _executable(
        reconcile,
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${API_RECONCILE_OPERATION:-reconcile}" != "verify" ]]; then
  grep -Fq '/app/token.json' "$API_PROJECT_DIR/$API_COMPOSE_FILE"
fi
printf '%s|%s\n' "$API_COMPOSE_FILE" "$API_DEPLOY_SERVICES" > "$RECONCILE_LOG"
printf 'reconcile:%s\n' "$API_COMPOSE_FILE" >> "$PATRONI_COMMAND_LOG"
if [[ "${API_RECONCILE_OPERATION:-reconcile}" == "verify" ]]; then
  test "$API_RECONCILE_BACKEND_IMAGE" = "$EXPECTED_CANDIDATE_IMAGE"
else
  test "$API_RECONCILE_BACKEND_IMAGE" = "$EXPECTED_PREVIOUS_IMAGE"
fi
if [[ "${API_RECONCILE_OPERATION:-reconcile}" != "verify" \
  && " $API_DEPLOY_SERVICES " == *" communications-worker "* ]]; then
  : > "$WORKER_RUNTIME_STATE"
fi
exit 0
""",
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "PATRONI_CANDIDATE_OPERATION": "deploy",
        "API_PROJECT_DIR": str(project),
        "PATRONI_CANONICAL_COMPOSE_FILE": str(project / "compose.yml"),
        "PATRONI_CANDIDATE_COMPOSE_FILE": str(project / "compose.yml.candidate"),
        "COMPOSE_CANDIDATE_TRANSACTION_SCRIPT": str(TRANSACTION),
        "PATRONI_DEPLOY_SCRIPT": str(child),
        "API_RECONCILE_SCRIPT": str(reconcile),
        "API_EXPECTED_PATRONI_ROLE": expected_role,
        "API_CURRENT_PATRONI_ROLE": current_role,
        "PATRONI_ROLE_AGENT_SOURCE": str(role_agent),
        "PATRONI_ROLE_AGENT_TARGET": str(tmp_path / "installed-role-agent"),
        "PATRONI_ROLE_COMPOSE_RUNTIME_SOURCE": str(role_compose_runtime),
        "PATRONI_ROLE_COMPOSE_RUNTIME_TARGET": str(
            tmp_path / "installed-patroni-compose-runtime.py"
        ),
        "PATRONI_ROLE_AGENT_CONFIG_SOURCE": str(role_agent_config),
        "PATRONI_ROLE_AGENT_CONFIG_TARGET": str(
            tmp_path / "installed-patroni-role-agent-config.py"
        ),
        "PATRONI_ROLE_IDENTITY_SOURCE": str(role_identity),
        "PATRONI_ROLE_IDENTITY_TARGET": str(tmp_path / "installed-role-identity.py"),
        "PATRONI_ROLE_UNIT_SOURCE": str(role_unit),
        "PATRONI_ROLE_UNIT_TARGET": str(tmp_path / "installed-role-agent.service"),
        "PATRONI_DB_CONTRACT_HELPER": str(DB_CONTRACT_HELPER),
        "PATRONI_ROLE_AGENT_UNIT": "test.service",
        "CHILD_LOG": str(tmp_path / "child.log"),
        "RECONCILE_LOG": str(tmp_path / "reconcile.log"),
        "PATRONI_COMMAND_LOG": str(command_log),
        "SYSTEMCTL_LOG": str(systemctl_log),
        "SYSTEMCTL_STATE": str(systemctl_state),
        "SYSTEMCTL_RESTART_COUNT": str(tmp_path / "systemctl-restart-count"),
        "INSTALL_COUNT": str(tmp_path / "install-count"),
        "INSTALL_LOG": str(tmp_path / "install.log"),
        "CP_LOG": str(tmp_path / "cp.log"),
        "WORKER_RUNTIME_STATE": str(tmp_path / "worker-runtime-state"),
        "CANONICAL_DB_CONTRACT": str(canonical_contract),
        "CANDIDATE_DB_CONTRACT": str(candidate_contract),
        "DEPLOY_CHILD_RAN": str(tmp_path / "deploy-child-ran"),
        "API_PREVIOUS_BACKEND_IMAGE": "" if discover_previous else PREVIOUS_IMAGE,
        "EXPECTED_PREVIOUS_IMAGE": PREVIOUS_IMAGE,
        "BACKEND_IMAGE": CANDIDATE_IMAGE,
        "EXPECTED_CANDIDATE_IMAGE": CANDIDATE_IMAGE,
        "API_DEPLOY_LOCK_HELPER": str(DEPLOY_LOCK_HELPER),
        "API_DEPLOY_LOCK_HELPER_SHA256": __import__("hashlib").sha256(
            DEPLOY_LOCK_HELPER.read_bytes()
        ).hexdigest(),
    }
    return env, project


def test_patroni_candidate_failure_leaves_canonical_old(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    old = (project / "compose.yml").read_text(encoding="utf-8")

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 42
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()
    assert (tmp_path / "child.log").read_text(encoding="utf-8").strip() == "compose.yml.candidate|9"
    assert (tmp_path / "reconcile.log").read_text(encoding="utf-8").strip() == "compose.yml|app"




def test_patroni_candidate_rejects_db_service_drift_before_host_mutation(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    candidate = json.loads(Path(env["CANDIDATE_DB_CONTRACT"]).read_text())
    candidate["services"]["db"]["image"] = "other-patroni-image"
    _write_json(Path(env["CANDIDATE_DB_CONTRACT"]), candidate)

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "candidate changes the Patroni db contract" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()
    assert not (tmp_path / "child.log").exists()
    assert not (tmp_path / "systemctl.log").read_text(encoding="utf-8")
    assert not Path(env["PATRONI_ROLE_AGENT_TARGET"]).exists()
    assert not Path(env["PATRONI_ROLE_IDENTITY_TARGET"]).exists()


@pytest.mark.parametrize("unsafe_helper", ["missing", "symlink"])
def test_patroni_candidate_cleans_up_when_db_contract_helper_is_unsafe(
    tmp_path, unsafe_helper
):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    helper = tmp_path / "unsafe-contract-helper.py"
    if unsafe_helper == "symlink":
        helper.symlink_to(DB_CONTRACT_HELPER)
    env["PATRONI_DB_CONTRACT_HELPER"] = str(helper)

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "db contract helper is missing or unsafe" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()
    assert not (tmp_path / "child.log").exists()
    assert not (tmp_path / "systemctl.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("drift", ["project_name", "external_volume"])
def test_patroni_candidate_rejects_db_resource_identity_drift_before_host_mutation(
    tmp_path, drift
):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    candidate = json.loads(Path(env["CANDIDATE_DB_CONTRACT"]).read_text())
    if drift == "project_name":
        candidate["name"] = "mvn-api-shadow"
    else:
        candidate["volumes"]["postgres_data"]["name"] = "other-postgres-data"
        candidate["volumes"]["postgres_data"]["driver_opts"] = {"type": "tmpfs"}
    _write_json(Path(env["CANDIDATE_DB_CONTRACT"]), candidate)

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "candidate changes the Patroni db contract" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (tmp_path / "child.log").exists()
    assert not (tmp_path / "systemctl.log").read_text(encoding="utf-8")


def test_patroni_candidate_rejects_latent_db_interpolation_drift(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    candidate = json.loads(Path(env["CANDIDATE_DB_CONTRACT"]).read_text())
    candidate["services"]["db"]["image"] = (
        "${BACKEND_IMAGE:?set immutable BACKEND_IMAGE}"
    )
    _write_json(Path(env["CANDIDATE_DB_CONTRACT"]), candidate)

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "candidate changes the Patroni db contract" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (tmp_path / "child.log").exists()


def test_patroni_candidate_rechecks_db_contract_immediately_before_promotion(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    drifted_contract = tmp_path / "candidate-contract-after-deploy.json"
    candidate = json.loads(Path(env["CANDIDATE_DB_CONTRACT"]).read_text())
    candidate["volumes"]["postgres_data"]["name"] = "late-postgres-data"
    _write_json(drifted_contract, candidate)
    env["CANDIDATE_DB_CONTRACT_AFTER_DEPLOY"] = str(drifted_contract)

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "candidate changes the Patroni db contract" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()
    assert (tmp_path / "child.log").exists()
    assert (tmp_path / "reconcile.log").read_text(encoding="utf-8").strip() == (
        "compose.yml|app"
    )


def test_patroni_discovers_previous_runtime_image_from_active_slot_before_reconcile(
    tmp_path,
):
    env, project = _patroni_runner_env(
        tmp_path,
        child_exit=42,
        discover_previous=True,
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 42, result.stderr
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    commands = (tmp_path / "patroni-commands.log").read_text(encoding="utf-8").splitlines()
    ps_index = next(i for i, line in enumerate(commands) if " ps -q app-green" in line)
    inspect_index = next(
        i for i, line in enumerate(commands) if line.startswith("inspect --format ")
    )
    reconcile_index = commands.index("reconcile:compose.yml")
    assert ps_index < inspect_index < reconcile_index
    assert (tmp_path / "reconcile.log").read_text(encoding="utf-8").strip() == (
        "compose.yml|app"
    )


def test_patroni_role_drift_fences_all_api_slots_and_bot_without_reconcile(tmp_path):
    env, project = _patroni_runner_env(
        tmp_path,
        child_exit=42,
        expected_role="primary",
        current_role="standby",
    )
    old = (project / "compose.yml").read_text(encoding="utf-8")

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 90
    assert "Patroni role changed during deployment" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()
    assert not (tmp_path / "reconcile.log").exists()
    commands = (tmp_path / "patroni-commands.log").read_text(encoding="utf-8").splitlines()
    assert any(
        " stop app app-blue app-green bot" in command for command in commands
    )


def test_patroni_unknown_live_role_fences_runtime_instead_of_assuming_standby(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    env.pop("API_CURRENT_PATRONI_ROLE")
    _executable(
        tmp_path / "bin/curl",
        "#!/usr/bin/env bash\nprintf '%s\n' '{\"state\":\"running\",\"role\":\"mystery\"}'\n",
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 90
    assert "could not establish live Patroni role" in result.stderr
    assert not (project / "compose.yml.candidate").exists()
    assert not (tmp_path / "reconcile.log").exists()
    commands = (tmp_path / "patroni-commands.log").read_text(encoding="utf-8")
    assert " stop app app-blue app-green bot" in commands


@pytest.mark.parametrize("migration_exit", [0, 48])
def test_patroni_migration_always_cleans_candidate_without_promoting(
    tmp_path,
    migration_exit,
):
    project = _compose_pair(tmp_path)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    migration_log = tmp_path / "migration.log"
    migration = tmp_path / "migration.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    _executable(
        migration,
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$API_COMPOSE_FILE" > "$MIGRATION_LOG"
exit {migration_exit}
""",
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "PATRONI_CANDIDATE_OPERATION": "migrate",
            "API_PROJECT_DIR": str(project),
            "PATRONI_CANONICAL_COMPOSE_FILE": str(project / "compose.yml"),
            "PATRONI_CANDIDATE_COMPOSE_FILE": str(project / "compose.yml.candidate"),
            "COMPOSE_CANDIDATE_TRANSACTION_SCRIPT": str(TRANSACTION),
            "PATRONI_MIGRATION_SCRIPT": str(migration),
                "MIGRATION_LOG": str(migration_log),
                "API_DEPLOY_LOCK_HELPER": str(DEPLOY_LOCK_HELPER),
                "API_DEPLOY_LOCK_HELPER_SHA256": __import__("hashlib").sha256(
                    DEPLOY_LOCK_HELPER.read_bytes()
                ).hexdigest(),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == migration_exit, result.stderr
    assert migration_log.read_text(encoding="utf-8").strip() == "compose.yml.candidate"
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()


def test_patroni_post_rename_promotion_error_preserves_new_canonical(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    new = (project / "compose.yml.candidate").read_text(encoding="utf-8")
    transaction_driver = tmp_path / "patroni-transaction.sh"
    _executable(
        transaction_driver,
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "promote" ]]; then
  bash "$REAL_TRANSACTION" "$1"
  exit 46
fi
exec bash "$REAL_TRANSACTION" "$@"
""",
    )
    env.update(
        {
            "COMPOSE_CANDIDATE_TRANSACTION_SCRIPT": str(transaction_driver),
            "REAL_TRANSACTION": str(TRANSACTION),
        }
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 46
    assert "promotion committed" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == new
    assert not (project / "compose.yml.candidate").exists()
    assert not (tmp_path / "reconcile.log").exists()


def test_legacy_source_bind_deploy_is_retired():
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "deploy_api.sh")],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "retired" in result.stderr
    assert "GitHub Actions image workflow" in result.stderr


@pytest.mark.parametrize("operation", ["deploy", "migrate"])
def test_patroni_candidate_rejects_database_rollout_marker_before_mutation(
    tmp_path, operation
):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    marker = project / ".patroni-cutover-in-progress"
    marker.write_text("0" * 32 + "\n", encoding="ascii")
    env["PATRONI_CANDIDATE_OPERATION"] = operation
    if operation == "migrate":
        env["PATRONI_MIGRATION_SCRIPT"] = env["PATRONI_DEPLOY_SCRIPT"]

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Patroni database rollout is in progress" in result.stderr
    assert not (tmp_path / "child.log").exists()
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
