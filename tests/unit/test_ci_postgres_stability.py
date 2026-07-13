import os
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ci/wait_for_stable_postgres.sh"
PYTHON_WAITER = REPO_ROOT / "scripts/ci/wait_for_stable_postgres.py"
CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _linux_process_state(pid: int, *, proc_root: Path = Path("/proc")) -> str | None:
    try:
        stat = (proc_root / str(pid) / "stat").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    command_end = stat.rfind(")")
    if command_end < 0 or command_end + 2 >= len(stat):
        raise AssertionError(f"malformed proc stat for pid {pid}: {stat!r}")
    return stat[command_end + 2]


def _process_is_live(pid: int, *, proc_root: Path = Path("/proc")) -> bool:
    if proc_root.is_dir():
        state = _linux_process_state(pid, proc_root=proc_root)
        return state is not None and state not in {"Z", "X", "x"}
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _run_waiter(
    tmp_path: Path,
    fake_docker: str,
    *,
    service: str = "db",
    database: str = "air_conditioners",
    timeout: str = "5",
    probe_timeout: str = "5",
    stable_samples: str = "3",
    interval: str = "0.01",
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(fake_bin / "docker", fake_docker)

    return subprocess.run(
        ["bash", str(SCRIPT), service, database, "postgres"],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "POSTGRES_WAIT_TIMEOUT_SECONDS": timeout,
            "POSTGRES_WAIT_PROBE_TIMEOUT_SECONDS": probe_timeout,
            "POSTGRES_WAIT_STABLE_SAMPLES": stable_samples,
            "POSTGRES_WAIT_SAMPLE_INTERVAL_SECONDS": interval,
            "FAKE_DOCKER_STATE": str(tmp_path / "docker-state"),
            "FAKE_DOCKER_CALLS": str(tmp_path / "docker-calls"),
            "FAKE_DOCKER_MARKER": str(tmp_path / "docker-marker"),
            "FAKE_DOCKER_PID_FILE": str(tmp_path / "docker-child-pid"),
            "FAKE_DOCKER_TERM_MARKER": str(tmp_path / "docker-term-marker"),
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_temp_postmaster_restart_resets_stability_before_final_server(tmp_path):
    result = _run_waiter(
        tmp_path,
        """#!/usr/bin/env bash
set -euo pipefail
state_file="${FAKE_DOCKER_STATE}"
calls_file="${FAKE_DOCKER_CALLS}"
count=0
[[ ! -f "${state_file}" ]] || count="$(cat "${state_file}")"
count=$((count + 1))
printf '%s' "${count}" > "${state_file}"
printf '%s\n' "$*" >> "${calls_file}"
case "${count}" in
  1|2) printf '2026-07-13 20:03:50+00\n' ;;
  *) printf '2026-07-13 20:03:52+00\n' ;;
esac
""",
    )

    assert result.returncode == 0, result.stderr
    assert "restarted; resetting stability samples" in result.stdout
    assert "stable after" in result.stdout
    assert (tmp_path / "docker-state").read_text(encoding="utf-8") == "5"
    calls = (tmp_path / "docker-calls").read_text(encoding="utf-8").splitlines()
    expected_call = (
        "compose exec -T db psql -X -w -v ON_ERROR_STOP=1 -U postgres "
        "-d air_conditioners -tAc SELECT pg_postmaster_start_time()::text;"
    )
    assert all(call == expected_call for call in calls)


def test_never_ready_service_times_out_and_fails_closed(tmp_path):
    result = _run_waiter(
        tmp_path,
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${FAKE_DOCKER_CALLS}"
printf '\n'
""",
        timeout="1",
        interval="0.05",
    )

    assert result.returncode != 0
    assert "did not produce 3 stable SQL samples within 1s" in result.stderr
    assert "is stable" not in result.stdout


def test_failed_sql_query_does_not_count_as_a_stable_sample(tmp_path):
    result = _run_waiter(
        tmp_path,
        """#!/usr/bin/env bash
set -euo pipefail
state_file="${FAKE_DOCKER_STATE}"
count=0
[[ ! -f "${state_file}" ]] || count="$(cat "${state_file}")"
count=$((count + 1))
printf '%s' "${count}" > "${state_file}"
if (( count == 2 )); then
  printf 'query failed\n' >&2
  exit 1
fi
printf '2026-07-13 20:04:00+00\n'
""",
    )

    assert result.returncode == 0, result.stderr
    assert "SQL probe failed; resetting stability samples" in result.stdout
    assert (tmp_path / "docker-state").read_text(encoding="utf-8") == "5"


def test_hung_sql_probe_is_killed_within_remaining_global_budget(tmp_path):
    started = time.monotonic()
    result = _run_waiter(
        tmp_path,
        """#!/usr/bin/env bash
set -euo pipefail
trap 'printf terminated > "${FAKE_DOCKER_TERM_MARKER}"; exit 143' TERM
(
  trap '' TERM
  sleep 3
  printf 'orphaned\n' > "${FAKE_DOCKER_MARKER}"
) &
child_pid="$!"
printf '%s' "${child_pid}" > "${FAKE_DOCKER_PID_FILE}"
wait "${child_pid}"
printf '2026-07-13 20:04:00+00\n'
""",
        timeout="1",
        probe_timeout="5",
    )
    elapsed = time.monotonic() - started

    assert result.returncode != 0
    assert elapsed < 1.75
    assert "within 1s" in result.stderr
    assert (tmp_path / "docker-term-marker").read_text(encoding="utf-8") == "terminated"

    child_pid = int((tmp_path / "docker-child-pid").read_text(encoding="utf-8"))
    cleanup_deadline = time.monotonic() + 0.5
    while _process_is_live(child_pid) and time.monotonic() < cleanup_deadline:
        time.sleep(0.02)
    if _process_is_live(child_pid):
        raise AssertionError(f"timed-out probe child {child_pid} is still running")

    assert not (tmp_path / "docker-marker").exists()


def test_linux_proc_state_distinguishes_live_process_from_zombie(tmp_path):
    proc_root = tmp_path / "proc"
    live_pid = 101
    zombie_pid = 202
    (proc_root / str(live_pid)).mkdir(parents=True)
    (proc_root / str(zombie_pid)).mkdir(parents=True)
    (proc_root / str(live_pid) / "stat").write_text(
        "101 (fake ) live child) S 1 2 3\n",
        encoding="utf-8",
    )
    (proc_root / str(zombie_pid) / "stat").write_text(
        "202 (fake zombie) Z 1 2 3\n",
        encoding="utf-8",
    )

    assert _process_is_live(live_pid, proc_root=proc_root) is True
    assert _process_is_live(zombie_pid, proc_root=proc_root) is False
    assert _process_is_live(303, proc_root=proc_root) is False


def test_ci_waits_for_both_postgres_services_with_sql_stability_gate():
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "pg_isready" not in workflow
    assert (
        "scripts/ci/wait_for_stable_postgres.sh db air_conditioners postgres"
        in workflow
    )
    assert (
        "scripts/ci/wait_for_stable_postgres.sh db_test air_conditioners_test postgres"
        in workflow
    )


def test_waiter_executes_sql_probe_for_each_ci_postgres_service(tmp_path):
    fake_docker = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${FAKE_DOCKER_CALLS}"
printf '2026-07-13 20:04:00+00\n'
"""

    for service, database in (
        ("db", "air_conditioners"),
        ("db_test", "air_conditioners_test"),
    ):
        case_dir = tmp_path / service
        case_dir.mkdir()
        result = _run_waiter(
            case_dir,
            fake_docker,
            service=service,
            database=database,
            stable_samples="2",
        )

        assert result.returncode == 0, result.stderr
        calls = (case_dir / "docker-calls").read_text(encoding="utf-8").splitlines()
        expected_call = (
            f"compose exec -T {service} psql -X -w -v ON_ERROR_STOP=1 "
            f"-U postgres -d {database} -tAc "
            "SELECT pg_postmaster_start_time()::text;"
        )
        assert len(calls) == 2
        assert all(call == expected_call for call in calls)


def test_default_stability_window_uses_three_samples_two_seconds_apart():
    script = PYTHON_WAITER.read_text(encoding="utf-8")

    assert "DEFAULT_STABLE_SAMPLES = 3" in script
    assert "DEFAULT_SAMPLE_INTERVAL_SECONDS = 2.0" in script
    assert "DEFAULT_PROBE_TIMEOUT_SECONDS = 5.0" in script
    assert "SELECT pg_postmaster_start_time()::text;" in script
    assert "start_new_session=True" in script
    assert "os.killpg(process_group_id, sig)" in script
    assert "signal.SIGKILL" in script
