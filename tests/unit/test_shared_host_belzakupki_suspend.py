import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "scripts/shared_host_belzakupki_suspend.sh"
PATRONI_RUNNER = REPO_ROOT / "scripts/ha/run_patroni_candidate_transaction.sh"
PATRONI_REMOTE = REPO_ROOT / "scripts/ha/run_patroni_node_remote.sh"
GUARD_LIFECYCLE = REPO_ROOT / "scripts/ha/shared_host_belzakupki_guard_lifecycle.sh"
SCHEDULER_ID = "a" * 64
WORKER_ID = "b" * 64


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _environment(tmp_path: Path, *, worker_state: str = "running") -> tuple[dict[str, str], Path, Path]:
    belzakupki_dir = tmp_path / "belzakupki"
    belzakupki_dir.mkdir(mode=0o700)
    marker = belzakupki_dir / ".kitlane-deploy-guard-enabled"
    marker.write_text("enabled\n", encoding="utf-8")
    marker.chmod(0o600)

    guard = tmp_path / "guard.sh"
    guard_source = SOURCE.read_text(encoding="utf-8").replace(
        "/opt/belzakupki", str(belzakupki_dir)
    )
    guard.write_text(
        guard_source.replace("metadata.st_uid != 0", "metadata.st_uid != os.geteuid()").replace(
            "directory_metadata.st_uid != 0", "directory_metadata.st_uid != os.geteuid()"
        ),
        encoding="utf-8",
    )
    guard.chmod(0o755)

    state = tmp_path / "docker-state"
    state.write_text(
        f"scheduler=running\nworker={worker_state}\n", encoding="utf-8"
    )
    command_log = tmp_path / "docker-commands"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env bash
set -euo pipefail
state_file="$MOCK_DOCKER_STATE"
command_log="$MOCK_DOCKER_LOG"
service_for_id() {{
  case "$1" in
    {SCHEDULER_ID}) printf 'scheduler\\n' ;;
    {WORKER_ID}) printf 'worker\\n' ;;
    *) exit 1 ;;
  esac
}}
state_for() {{ sed -n "s/^$1=//p" "$state_file"; }}
set_state() {{
  value="$2"
  sed "s/^$1=.*/$1=$value/" "$state_file" > "$state_file.tmp"
  mv "$state_file.tmp" "$state_file"
}}
if [[ "$1" == ps ]]; then
  service=""
  for argument in "$@"; do
    case "$argument" in *com.docker.compose.service=*) service="${{argument##*=}}" ;; esac
  done
  if [[ "$(state_for "$service")" == running ]]; then
    [[ "$service" == scheduler ]] && printf '{SCHEDULER_ID}\\n' || printf '{WORKER_ID}\\n'
  fi
  exit 0
fi
if [[ "$1" == inspect ]]; then
  id="${{@: -1}}"; service="$(service_for_id "$id")"
  if [[ "$*" == *'.Name'* ]]; then
    printf '/belzakupki-%s-1|belzakupki|%s|%s\\n' "$service" "$service" "$(dirname "$state_file")/belzakupki"
  else
    state="$(state_for "$service")"
    [[ "$state" == missing ]] && exit 1
    printf '%s\\n' "$state"
  fi
  exit 0
fi
if [[ "$1" == kill ]]; then
  id="${{@: -1}}"; service="$(service_for_id "$id")"
  printf 'kill %s\\n' "$service" >> "$command_log"
  if [[ "${{MOCK_TIMEOUT_SERVICE:-}}" != "$service" ]]; then set_state "$service" exited; fi
  exit 0
fi
if [[ "$1" == start ]]; then
  id="$2"; service="$(service_for_id "$id")"
  printf 'start %s\\n' "$service" >> "$command_log"
  set_state "$service" running
  exit 0
fi
exit 1
""",
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "MOCK_DOCKER_STATE": str(state),
        "MOCK_DOCKER_LOG": str(command_log),
        "API_SHARED_HOST_BELZAKUPKI_GUARD": "auto",
        "API_SHARED_HOST_BELZAKUPKI_STOP_TIMEOUT_SECONDS": "1",
        "API_SHARED_HOST_BELZAKUPKI_DIR": str(belzakupki_dir),
    }
    return env, guard, command_log


def _run(guard: Path, action: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(guard), action], env=env, text=True, capture_output=True, check=False
    )


def test_suspend_then_restores_only_the_originally_running_worker_and_scheduler(tmp_path):
    env, guard, command_log = _environment(tmp_path)

    prepared = _run(guard, "prepare", env)
    assert prepared.returncode == 0, prepared.stderr
    assert "scheduler=exited" in Path(env["MOCK_DOCKER_STATE"]).read_text()
    assert "worker=exited" in Path(env["MOCK_DOCKER_STATE"]).read_text()
    assert command_log.read_text().splitlines() == ["kill scheduler", "kill worker"]

    restored = _run(guard, "restore", env)
    assert restored.returncode == 0, restored.stderr
    assert "scheduler=running" in Path(env["MOCK_DOCKER_STATE"]).read_text()
    assert "worker=running" in Path(env["MOCK_DOCKER_STATE"]).read_text()
    assert command_log.read_text().splitlines() == [
        "kill scheduler",
        "kill worker",
        "start worker",
        "start scheduler",
    ]
    assert not (Path(env["API_SHARED_HOST_BELZAKUPKI_DIR"]) / ".air-api-deploy-suspension").exists()


def test_previously_stopped_scheduler_is_never_started(tmp_path):
    env, guard, command_log = _environment(tmp_path, worker_state="running")
    state = Path(env["MOCK_DOCKER_STATE"])
    state.write_text("scheduler=exited\nworker=running\n", encoding="utf-8")

    assert _run(guard, "prepare", env).returncode == 0
    assert _run(guard, "restore", env).returncode == 0

    assert "scheduler=exited" in state.read_text()
    assert command_log.read_text().splitlines() == ["kill worker", "start worker"]


def test_graceful_stop_timeout_aborts_and_keeps_recovery_record(tmp_path):
    env, guard, command_log = _environment(tmp_path)
    env["MOCK_TIMEOUT_SERVICE"] = "worker"

    prepared = _run(guard, "prepare", env)

    assert prepared.returncode != 0
    assert "without SIGKILL" in prepared.stderr
    assert (Path(env["API_SHARED_HOST_BELZAKUPKI_DIR"]) / ".air-api-deploy-suspension").exists()
    assert command_log.read_text().splitlines() == [
        "kill scheduler",
        "kill worker",
        "start scheduler",
    ]


def test_next_prepare_recovers_a_stale_record_before_suspending_again(tmp_path):
    env, guard, command_log = _environment(tmp_path)

    assert _run(guard, "prepare", env).returncode == 0
    repeated = _run(guard, "prepare", env)

    assert repeated.returncode == 0, repeated.stderr
    assert command_log.read_text().splitlines() == [
        "kill scheduler",
        "kill worker",
        "start worker",
        "start scheduler",
        "kill scheduler",
        "kill worker",
    ]
    source = SOURCE.read_text(encoding="utf-8")
    assert "trap 'restore || true; exit 143' INT TERM" in source


def test_patroni_release_bundles_the_guard_and_suspends_before_migration_or_deploy():
    transaction = PATRONI_RUNNER.read_text(encoding="utf-8")
    remote = PATRONI_REMOTE.read_text(encoding="utf-8")

    assert "shared_host_belzakupki_suspend.sh" in remote
    assert "shared_host_belzakupki_guard_lifecycle.sh" in remote
    assert "API_SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT" in remote
    assert "bash \"${SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT}\" prepare" in GUARD_LIFECYCLE.read_text(
        encoding="utf-8"
    )
    migration_prepare = transaction.index(
        "shared_belzakupki_guard_prepare_with_signal_recovery"
    )
    migration_start = transaction.index('bash "${MIGRATION_SCRIPT}"')
    deploy_start = transaction.index('bash "${DEPLOY_SCRIPT}"')
    deploy_prepare = transaction.rindex(
        "shared_belzakupki_guard_prepare_with_signal_recovery", 0, deploy_start
    )
    assert migration_prepare < migration_start
    assert deploy_prepare < deploy_start
