"""Late capacity changes through the real transaction, lock, guard and migration."""

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from tests.unit.test_patroni_candidate_transactions import PATRONI_RUNNER, _patroni_runner_env
from tests.unit.test_patroni_idle_worker_capacity import (
    FAKE_DOCKER, NEW, OLD, RELEASE, ROOT, change, snapshot,
)


CAPACITY = ROOT / "scripts/ha/require_deploy_capacity.sh"


def _meminfo(path, available=2097152):
    path.write_text(f"MemAvailable: {available} kB\nSwapTotal: 524288 kB\nSwapFree: 524288 kB\n")


@pytest.fixture
def late_env(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    env.update({
        "PATRONI_CANDIDATE_OPERATION": "migrate",
        "PATRONI_MIGRATION_SCRIPT": str(ROOT / "scripts/ha/run_patroni_migrations.sh"),
        "API_DEPLOY_CAPACITY_HELPER": str(CAPACITY),
        "API_DEPLOY_MEMINFO_FILE": str(tmp_path / "meminfo"),
        "TEST_CAPACITY_MEMINFO": str(tmp_path / "meminfo"),
        "API_PATRONI_URL": 'data:application/json,{"state":"running","role":"primary"}',
        "COMMUNICATIONS_WORKER_RELEASE_HELPER": str(RELEASE),
        "GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT": str(tmp_path / "prepare-token.sh"),
        "API_PREVIOUS_BACKEND_IMAGE": OLD,
        "EXPECTED_PREVIOUS_IMAGE": OLD,
        "EXPECTED_CANDIDATE_IMAGE": NEW,
        "BACKEND_IMAGE": NEW,
        "GUARD_CALL_LOG": str(tmp_path / "guard-calls.log"),
    })
    _meminfo(Path(env["API_DEPLOY_MEMINFO_FILE"]))
    (project / ".active-api-slot").write_text("blue\n")
    (project / ".env").write_text(f"BACKEND_IMAGE={OLD}\n")
    (project / "runtime.json").write_text(json.dumps({
        "api_image": OLD, "worker_image": OLD, "running": True, "revision": 3,
        "capacity_drop_after": ["pull"],
    }))
    Path(env["GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT"]).write_text("exit 0\n")
    (tmp_path / "bin/docker").write_text(f"#!{sys.executable}\n" + FAKE_DOCKER)
    python = tmp_path / "bin/python3"
    python.write_text(python.read_text().replace("exec ", '''if [[ "${1:-}" == *patroni_idle_worker_capacity.py ]]; then
  printf '%s\\n' "$*" >> "$GUARD_CALL_LOG"
fi
exec ''', 1))
    curl = tmp_path / "bin/curl"
    curl.write_text('#!/bin/sh\nprintf \'{"state":"running","role":"primary"}\\n\'\n')
    curl.chmod(0o755)
    return env


def _run(env):
    return subprocess.run(["bash", str(PATRONI_RUNNER)], env=env, text=True,
                          capture_output=True, timeout=40)


def _commands(env):
    return [json.loads(line) for line in
            (Path(env["API_PROJECT_DIR"]) / "commands.log").read_text().splitlines()]


def _assert_restored(env):
    project, state = snapshot(env)
    assert state["api_image"] == state["worker_image"] == OLD
    assert state["running"] and state["revision"] == 3
    assert not (project / ".ha-idle-worker-capacity.json").exists()
    assert not (project / ".ha-communications-worker-release-fenced").exists()
    assert (project / ".env").read_text() == f"BACKEND_IMAGE={OLD}\n"


def _prepare_count(env):
    return Path(env["GUARD_CALL_LOG"]).read_text().count(" prepare ")


@pytest.mark.parametrize("drop_after", ["pull", "alembic"])
def test_late_migration_capacity_drop_pauses_idle_worker_and_restores(late_env, drop_after):
    change(late_env, capacity_drop_after=[drop_after])
    result = _run(late_env)
    assert result.returncode == 0, result.stdout + result.stderr
    commands = _commands(late_env)
    drop = next(i for i, cmd in enumerate(commands) if drop_after in cmd)
    stop = next(i for i, cmd in enumerate(commands) if "stop" in cmd)
    defaults = next(i for i, cmd in enumerate(commands) if "scripts/ensure_global_config_defaults.py" in cmd)
    assert drop < stop < defaults
    assert _prepare_count(late_env) == 2  # Initial pass, late relief; no recursive prepare.
    assert (Path(late_env["API_PROJECT_DIR"]) / "operator-switch-blocked").exists()
    _assert_restored(late_env)


@pytest.mark.parametrize("updates", [{"deliveries": 1}, {"fresh": False}, {"allow_all": "true"}])
def test_late_capacity_drop_refuses_active_stale_or_open_gate(late_env, updates):
    change(late_env, **updates)
    result = _run(late_env)
    assert result.returncode != 0
    commands = _commands(late_env)
    assert not any("stop" in cmd or "run" in cmd for cmd in commands)
    _assert_restored(late_env)


def test_failure_after_late_pause_restores_original_generation(late_env):
    change(late_env, fail_run="alembic")
    result = _run(late_env)
    assert result.returncode == 42, result.stdout + result.stderr
    commands = _commands(late_env)
    assert any("stop" in cmd for cmd in commands)
    assert not any("scripts/ensure_global_config_defaults.py" in cmd for cmd in commands)
    _assert_restored(late_env)


def test_owned_journal_prevents_second_late_prepare(late_env):
    change(late_env, capacity_drop_after=["pull", "alembic"])
    result = _run(late_env)
    assert result.returncode != 0
    assert _prepare_count(late_env) == 2
    assert sum("stop" in cmd for cmd in _commands(late_env)) == 1
    _assert_restored(late_env)


def test_relief_does_not_bypass_remaining_capacity_check(late_env):
    change(late_env, still_low=True)
    result = _run(late_env)
    assert result.returncode != 0
    assert _prepare_count(late_env) == 2
    assert not any("run" in cmd for cmd in _commands(late_env))
    _assert_restored(late_env)


@pytest.mark.parametrize("scenario", ["relieve", "fail-before-activation", "fail-after-activation"])
def test_deploy_child_limits_relief_to_original_generation(late_env, tmp_path, scenario):
    late_env.update({
        "PATRONI_CANDIDATE_OPERATION": "deploy",
        "PATRONI_DEPLOY_SCRIPT": str(ROOT / "scripts/ha/deploy_patroni_api_node.sh"),
        "API_BLUE_GREEN_SCRIPT": str(tmp_path / "bluegreen.sh"),
    })
    if scenario == "fail-after-activation":
        change(late_env, capacity_drop_after=["worker-pull"], release_stop_without_idle=True)
    # Simulate a candidate pull inside the child. The real deploy-node parent
    # must pass relief through, then keep the guard for start_candidate only.
    script = '''set -eu
source "$API_DEPLOY_CAPACITY_HELPER"
docker compose -f "$API_COMPOSE_FILE" pull app-green
require_deploy_capacity
'''
    if scenario == "fail-before-activation":
        script += "exit 42\n"
    else:
        script += f'''{shlex.quote(sys.executable)} - <<'UPDATE'
import json, os
from pathlib import Path
p = Path(os.environ['API_PROJECT_DIR'])
s = json.loads((p / 'runtime.json').read_text())
s['api_image'] = os.environ['BACKEND_IMAGE']
if s['capacity_drop_after'] == ['pull']: s['capacity_drop_after'] = []
(p / 'runtime.json').write_text(json.dumps(s))
(p / '.env').write_text('BACKEND_IMAGE=' + os.environ['BACKEND_IMAGE'] + '\\n')
UPDATE
'''
    child = Path(late_env["API_BLUE_GREEN_SCRIPT"])
    child.write_text(script)
    child.chmod(0o755)
    reconcile = Path(late_env["API_RECONCILE_SCRIPT"])
    reconcile.write_text(f'''set -eu
if test "${{API_RECONCILE_OPERATION:-}}" = verify; then exit 0; fi
{shlex.quote(sys.executable)} - <<'UPDATE'
import json, os
from pathlib import Path
p = Path(os.environ['API_PROJECT_DIR'])
s = json.loads((p / 'runtime.json').read_text())
s['api_image'] = os.environ['API_RECONCILE_BACKEND_IMAGE']
(p / 'runtime.json').write_text(json.dumps(s))
UPDATE
''')
    result = _run(late_env)
    expected_prepares = 1 if scenario == "fail-after-activation" else 2
    assert _prepare_count(late_env) == expected_prepares, result.stdout + result.stderr
    if scenario == "fail-after-activation":
        assert result.returncode != 0
        assert "insufficient memory headroom" in result.stderr
        assert any("pull" in cmd and cmd[-1] == "communications-worker" for cmd in _commands(late_env))
        project, state = snapshot(late_env)
        assert state["api_image"] == OLD  # Existing transaction rollback still runs.
        assert not (project / ".ha-idle-worker-capacity.json").exists()
    elif scenario == "fail-before-activation":
        assert result.returncode == 42, result.stdout + result.stderr
        _assert_restored(late_env)
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        project, state = snapshot(late_env)
        assert state["api_image"] == state["worker_image"] == NEW
        assert state["running"]
        assert not (project / ".ha-idle-worker-capacity.json").exists()
