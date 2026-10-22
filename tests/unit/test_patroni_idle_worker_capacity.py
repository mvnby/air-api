"""Host-only release tests. Fake Docker, real deploy lock and shell contract."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts/ha/patroni_idle_worker_capacity.py"
LOCK = ROOT / "scripts/ha/safe_deploy_lock.py"
RELEASE = ROOT / "scripts/ha/communications_worker_release_contract.sh"
OLD = "ghcr.io/example/backend:" + "1" * 40
NEW = "ghcr.io/example/backend:" + "2" * 40

FAKE_DOCKER = r'''import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

p = Path(os.environ['API_PROJECT_DIR'])
state_path = p / 'runtime.json'
def state(): return json.loads(state_path.read_text())
def save(value): state_path.write_text(json.dumps(value))
args = sys.argv[1:]
with (p / 'commands.log').open('a') as log: log.write(json.dumps(args) + '\n')
s = state()
if args == ['capacity-check']:
    sys.exit(0 if s.get('capacity_high') or (not s['running'] and not s.get('still_low')) else 1)
if args[0] == 'inspect':
    image = s['api_image'] if args[-1] == 'api-id' else s['worker_image']
    if '--format' in args:
        print(image + '|true' if 'State.Running' in args[args.index('--format')+1] else image)
    else:
        print(json.dumps([{'Config': {'Image': image, 'Env': [
            'APP_ROLE=' + s.get('worker_role', 'primary'),
            'COMMUNICATIONS_WORKER_ENABLED=true',
            'COMMUNICATIONS_WORKER_ALLOW_ALL_MODE=' + s.get('allow_all', 'false')]},
            'State': {'Running': s['running']}}]))
    sys.exit(0)
if 'config' in args:
    if '--services' in args: print('app-blue\ncommunications-worker\ndb')
    elif '--no-env-resolution' in args:
        print(Path(os.environ['CANONICAL_DB_CONTRACT']).read_text())
    else: print(json.dumps({'name': 'air-api', 'services': {'communications-worker': {
        'image': os.environ.get('BACKEND_IMAGE', s['api_image']),
        'environment': {'COMMUNICATIONS_WORKER_ENABLED': 'true',
            'COMMUNICATIONS_WORKER_ALLOW_ALL_MODE': s.get('allow_all', 'false')}}}}))
elif 'ps' in args:
    if args[-1].startswith('app'): print('api-id')
    elif not s['running'] and s.get('fail_stopped_probe'): sys.exit(5)
    elif '--all' in args and s.get('worker_exists', True): print('worker-id')
    elif s['running']: print('worker-id')
elif 'exec' in args and 'db' in args:
    lock = (p / 'control.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX)
    (p / 'sql-held').touch()
    sql = ''
    for line in sys.stdin:
        sql += line
        if line.strip() == ') FROM control;':
            s = state()
            print(json.dumps({'primary': True, 'mode': s.get('mode', 'all'),
                'status': s.get('status', 'paused'), 'revision': s['revision'],
                'fresh': s.get('fresh', True), 'running': s.get('deliveries', 0)}), flush=True)
        if line.strip() == r'\q': break
    (p / 'sql-used').write_text(sql)
    (p / 'sql-held').unlink()
    fcntl.flock(lock, fcntl.LOCK_UN)
    if state().get('switch_after_stop'):
        s = state(); s['revision'] += 1; save(s)
elif 'exec' in args:  # Existing release helper's tiny environment check only.
    sys.exit(0)
elif 'stop' in args:
    if s.get('fail_stop'): sys.exit(3)
    if not s['running']: sys.exit(0)
    journal = p / '.ha-idle-worker-capacity.json'
    assert journal.exists() and journal.stat().st_mode & 0o777 == 0o600
    # A concurrent operator cannot change the row between proof and stop.
    with (p / 'control.lock').open('w') as probe:
        try: fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: (p / 'operator-switch-blocked').touch()
        else: raise AssertionError('stop escaped the SQL control lock')
    s['running'] = False; save(s)
    if s.get('signal_stop_command'):
        os.kill(os.getpid(), signal.SIGTERM)
    if s.get('lose_fence_during_stop'):
        (p / '.ha-communications-worker-release-fenced').unlink()
    if s.get('failed_stop_state'):
        s['container_status'] = s['failed_stop_state']; save(s)
        sys.exit(3)
    if s.get('removed_during_stop'):
        s['worker_exists'] = False; save(s)
        # The role agent enforces the same fence via stop + rm concurrently.
        print('fake secret must never appear in guard diagnostics', file=sys.stderr)
        sys.exit(3)
    if s.get('term_after_stop'):
        os.kill(os.getppid(), signal.SIGTERM)
elif 'up' in args:
    if s.get('fail_start'): sys.exit(4)
    if s.get('delayed_start'):
        subprocess.Popen([sys.executable, '-c',
            "import time; from pathlib import Path; time.sleep(2); Path('late-start').touch()"])
        time.sleep(10)
    assert (p / 'sql-held').exists(), 'restore must authorize original control under lock'
    s['running'] = True; s['worker_image'] = os.environ['BACKEND_IMAGE']
    if 'worker_exists' in s: s['worker_exists'] = True
    save(s)
elif 'pull' in args:
    pass
else:
    raise AssertionError(args)
'''


@pytest.fixture
def release_env(tmp_path):
    project = tmp_path / "project"
    project.mkdir(mode=0o700)
    (project / "compose.yml").write_text("services: {}\n")
    (project / ".active-api-slot").write_text("blue\n")
    (project / "runtime.json").write_text(json.dumps({
        "api_image": OLD, "worker_image": OLD, "running": True, "revision": 3,
    }))
    binary = tmp_path / "bin"
    binary.mkdir()
    docker = binary / "docker"
    docker.write_text(f"#!{sys.executable}\n" + FAKE_DOCKER)
    docker.chmod(0o755)
    capacity = tmp_path / "capacity.sh"
    capacity.write_text("require_deploy_capacity() { docker capacity-check; }\n")
    return {
        **os.environ,
        "PATH": f"{binary}:{os.environ['PATH']}",
        "API_PROJECT_DIR": str(project),
        "API_PATRONI_URL": 'data:application/json,{"state":"running","role":"primary"}',
        "API_EXPECTED_PATRONI_ROLE": "primary",
        "PATRONI_CANONICAL_COMPOSE_FILE": str(project / "compose.yml"),
        "API_DEPLOY_LOCK_HELPER": str(LOCK),
        "API_DEPLOY_LOCK_HELPER_SHA256": hashlib.sha256(LOCK.read_bytes()).hexdigest(),
        "API_DEPLOY_CAPACITY_HELPER": str(capacity),
        "COMMUNICATIONS_WORKER_RELEASE_HELPER": str(RELEASE),
        "BACKEND_IMAGE": NEW,
        "API_COMPOSE_FILE": "candidate.yml",
    }


def change(env, **values):
    path = Path(env["API_PROJECT_DIR"]) / "runtime.json"
    current = json.loads(path.read_text())
    current.update(values)
    path.write_text(json.dumps(current))


def run(env, action, *, transactional=False):
    guard = f"{shlex.quote(sys.executable)} {shlex.quote(str(GUARD))}"
    script = f"{guard} {action}"
    if transactional:
        script = f'''set -Eeuo pipefail
cleanup() {{ local code=$?; trap - EXIT; {guard} recover || code=90; exit "$code"; }}
trap cleanup EXIT
trap 'exit 143' INT TERM
{guard} recover
{guard} prepare migrate
source "$API_DEPLOY_CAPACITY_HELPER"
require_deploy_capacity
{guard} recover
trap - EXIT
'''
    return subprocess.run(
        [sys.executable, str(LOCK), "exec", str(Path(env["API_PROJECT_DIR"]) / ".deploy.lock"),
         "bash", "-c", script], env=env, text=True, capture_output=True, timeout=35,
    )


def snapshot(env):
    project = Path(env["API_PROJECT_DIR"])
    return project, json.loads((project / "runtime.json").read_text())


def test_idle_migration_restores_original_worker_and_keeps_control(release_env):
    result = run(release_env, "", transactional=True)
    assert result.returncode == 0, result.stderr
    project, state = snapshot(release_env)
    assert state == {"api_image": OLD, "worker_image": OLD, "running": True, "revision": 3}
    assert not (project / ".ha-idle-worker-capacity.json").exists()
    assert not (project / ".ha-communications-worker-release-fenced").exists()
    assert not (project / "sql-held").exists()
    assert (project / "operator-switch-blocked").exists()
    sql = (project / "sql-used").read_text()
    assert "FOR UPDATE" in sql and "lock_timeout = '2s'" in sql
    assert not any(word in sql.upper() for word in ("UPDATE COMMUNICATION", "DELETE FROM", "INSERT INTO"))
    commands = (project / "commands.log").read_text()
    assert '"db", "sh", "-lc"' in commands
    assert '"app-blue", "python' not in commands


@pytest.mark.parametrize("updates", [
    {"allow_all": "true"}, {"deliveries": 1}, {"mode": "canary"},
    {"fresh": False}, {"worker_image": NEW}, {"worker_role": "standby"},
])
def test_active_or_inconclusive_runtime_refused_without_stop(release_env, updates):
    change(release_env, **updates)
    result = run(release_env, "", transactional=True)
    assert result.returncode != 0
    project, state = snapshot(release_env)
    assert state["running"]
    assert not (project / ".ha-idle-worker-capacity.json").exists()
    assert '"stop"' not in (project / "commands.log").read_text()


def test_high_capacity_never_reads_or_stops_worker(release_env):
    change(release_env, capacity_high=True, allow_all="true")
    assert run(release_env, "", transactional=True).returncode == 0
    project, _ = snapshot(release_env)
    assert '"inspect"' not in (project / "commands.log").read_text()


def test_capacity_still_low_aborts_and_restores_worker(release_env):
    change(release_env, still_low=True)
    result = run(release_env, "", transactional=True)
    assert result.returncode != 0
    project, state = snapshot(release_env)
    assert state["running"]
    assert not (project / ".ha-idle-worker-capacity.json").exists()


def test_stop_failure_restores_and_cleans_own_fence(release_env):
    change(release_env, fail_stop=True)
    result = run(release_env, "", transactional=True)
    assert result.returncode != 0
    project, state = snapshot(release_env)
    assert state["running"]
    assert not (project / ".ha-idle-worker-capacity.json").exists()


def test_concurrent_role_agent_removal_satisfies_stopped_postcondition(release_env):
    change(release_env, removed_during_stop=True)
    result = run(release_env, "", transactional=True)
    assert result.returncode == 0, result.stderr
    project, state = snapshot(release_env)
    assert state["running"] and state["worker_image"] == OLD
    assert "fake secret" not in result.stdout + result.stderr
    inventories = [json.loads(line) for line in (project / "commands.log").read_text().splitlines()
                   if '"--all"' in line]
    assert len(inventories) == 1
    assert inventories[0] == [
        "compose", "-f", str(project / "compose.yml"), "--profile", "bluegreen",
        "ps", "--all", "-q", "communications-worker",
    ]
    assert not (project / ".ha-idle-worker-capacity.json").exists()
    assert not (project / ".ha-communications-worker-release-fenced").exists()


def test_failed_stop_with_running_worker_is_not_accepted(release_env):
    change(release_env, fail_stop=True)
    result = run(release_env, "prepare deploy")
    assert result.returncode != 0
    project, state = snapshot(release_env)
    assert state["running"]
    assert "stop communications worker" in result.stderr and "exit=3" in result.stderr
    assert (project / ".ha-idle-worker-capacity.json").exists()
    assert (project / ".ha-communications-worker-release-fenced").exists()


@pytest.mark.parametrize("status", ["exited", "restarting", "paused", "created", "removing"])
def test_failed_stop_with_any_remaining_container_is_not_accepted(release_env, status):
    change(release_env, failed_stop_state=status)
    result = run(release_env, "prepare deploy")
    assert result.returncode != 0
    project, state = snapshot(release_env)
    assert not state["running"] and state["container_status"] == status
    assert "stop communications worker" in result.stderr and "exit=3" in result.stderr
    assert (project / ".ha-idle-worker-capacity.json").exists()
    assert (project / ".ha-communications-worker-release-fenced").exists()
    assert "suspended inside release transaction" not in result.stdout


@pytest.mark.parametrize("restore_fails", [False, True])
def test_removed_worker_requires_successful_stopped_probe_and_safe_recovery(release_env, restore_fails):
    change(release_env, removed_during_stop=True, fail_stopped_probe=True)
    result = run(release_env, "prepare deploy")
    assert result.returncode != 0
    project, state = snapshot(release_env)
    assert not state["running"]
    assert "query all communications worker containers" in result.stderr and "exit=5" in result.stderr
    assert "fake secret" not in result.stdout + result.stderr
    assert (project / ".ha-idle-worker-capacity.json").exists()
    assert (project / ".ha-communications-worker-release-fenced").exists()
    assert not any("up" in json.loads(line) for line in (project / "commands.log").read_text().splitlines())
    change(release_env, fail_stopped_probe=False, fail_start=restore_fails)
    recovered = run(release_env, "recover")
    assert (recovered.returncode != 0) == restore_fails
    assert snapshot(release_env)[1]["running"] is not restore_fails
    assert (project / ".ha-idle-worker-capacity.json").exists() is restore_fails
    assert (project / ".ha-communications-worker-release-fenced").exists() is restore_fails


def test_signaled_stop_command_is_not_accepted_even_after_container_stopped(release_env):
    change(release_env, signal_stop_command=True)
    result = run(release_env, "prepare deploy")
    assert result.returncode != 0
    project, state = snapshot(release_env)
    assert not state["running"]
    assert "stop communications worker interrupted" in result.stderr
    assert (project / ".ha-idle-worker-capacity.json").exists()
    assert (project / ".ha-communications-worker-release-fenced").exists()


def test_stopped_worker_requires_retained_release_fence(release_env):
    change(release_env, lose_fence_during_stop=True)
    result = run(release_env, "prepare deploy")
    assert result.returncode != 0
    project, state = snapshot(release_env)
    assert not state["running"]
    assert (project / ".ha-idle-worker-capacity.json").exists()
    assert (project / ".ha-communications-worker-release-fenced").exists()
    assert "suspended inside release transaction" not in result.stdout


def test_restore_failure_keeps_durable_journal_and_fence(release_env):
    change(release_env, fail_start=True)
    result = run(release_env, "", transactional=True)
    assert result.returncode == 90
    project, state = snapshot(release_env)
    assert not state["running"]
    assert (project / ".ha-idle-worker-capacity.json").exists()
    assert (project / ".ha-communications-worker-release-fenced").exists()


def test_term_releases_sql_and_transaction_restores_worker(release_env):
    change(release_env, term_after_stop=True)
    result = run(release_env, "", transactional=True)
    assert result.returncode != 0
    project, state = snapshot(release_env)
    assert state["running"], result.stderr
    assert not (project / "sql-held").exists()
    assert not (project / ".ha-idle-worker-capacity.json").exists()


def test_next_transaction_recovers_stale_journal_before_new_capture(release_env):
    assert run(release_env, "prepare migrate").returncode == 0
    change(release_env, capacity_high=True)
    result = run(release_env, "", transactional=True)
    assert result.returncode == 0, result.stderr
    project, state = snapshot(release_env)
    assert state["running"]
    assert not (project / ".ha-idle-worker-capacity.json").exists()


@pytest.mark.parametrize("drift", ["role", "image", "control"])
def test_stale_recovery_refuses_new_role_image_or_control(release_env, drift):
    assert run(release_env, "prepare migrate").returncode == 0
    if drift == "role":
        release_env["API_PATRONI_URL"] = 'data:application/json,{"state":"running","role":"replica"}'
    elif drift == "image":
        change(release_env, api_image=NEW)
    else:
        change(release_env, revision=4)
    result = run(release_env, "recover")
    assert result.returncode != 0
    project, state = snapshot(release_env)
    assert not state["running"]
    assert (project / ".ha-communications-worker-release-fenced").exists()
    assert (project / ".ha-idle-worker-capacity.json").exists()


def test_operator_switch_after_stop_prevents_restore(release_env):
    change(release_env, switch_after_stop=True)
    result = run(release_env, "", transactional=True)
    assert result.returncode == 90
    project, state = snapshot(release_env)
    assert not state["running"]
    assert (project / "operator-switch-blocked").exists()
    assert (project / ".ha-idle-worker-capacity.json").exists()


def test_preexisting_fence_is_not_lifted(release_env):
    project, _ = snapshot(release_env)
    marker = project / ".ha-communications-worker-release-fenced"
    marker.write_text("fenced\n")
    marker.chmod(0o600)
    change(release_env, running=False, still_low=True)
    assert run(release_env, "", transactional=True).returncode != 0
    assert marker.exists()
    assert not snapshot(release_env)[1]["running"]


def test_promoted_error_never_restores_old_image(release_env):
    assert run(release_env, "prepare deploy").returncode == 0
    change(release_env, api_image=NEW)
    assert run(release_env, "promoted").returncode == 0
    assert run(release_env, "recover").returncode != 0
    project, state = snapshot(release_env)
    assert not state["running"] and state["worker_image"] == OLD
    assert (project / ".ha-communications-worker-release-fenced").exists()


def test_verified_new_deploy_clears_journal_without_old_restart(release_env):
    assert run(release_env, "prepare deploy").returncode == 0
    change(release_env, api_image=NEW, worker_image=NEW, running=True)
    project, _ = snapshot(release_env)
    (project / ".ha-communications-worker-release-fenced").unlink()
    assert run(release_env, "promoted").returncode == 0
    result = run(release_env, "complete")
    assert result.returncode == 0, result.stderr
    assert not (project / ".ha-idle-worker-capacity.json").exists()


@pytest.mark.parametrize("revision", [3, 4])
def test_candidate_start_checks_original_control_before_unfencing(release_env, revision):
    assert run(release_env, "prepare deploy").returncode == 0
    change(release_env, api_image=NEW, revision=revision)
    result = run(release_env, "start_candidate")
    project, state = snapshot(release_env)
    if revision == 3:
        assert result.returncode == 0, result.stderr
        assert state["running"] and state["worker_image"] == NEW
    else:
        assert result.returncode != 0
        assert not state["running"]
        assert (project / ".ha-communications-worker-release-fenced").exists()
    assert (project / ".ha-idle-worker-capacity.json").exists()
    if revision == 3:
        commands = [json.loads(line) for line in (project / "commands.log").read_text().splitlines()]
        starts = [command for command in commands if "up" in command]
        assert starts and starts[-1][starts[-1].index("-f") + 1] == str(project / "candidate.yml")


def test_actual_migration_entrypoint_with_empty_expected_role(tmp_path):
    from tests.unit.test_patroni_candidate_transactions import (
        PATRONI_RUNNER, _patroni_runner_env,
    )

    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    env.update({
        "PATRONI_CANDIDATE_OPERATION": "migrate",
        "API_EXPECTED_PATRONI_ROLE": "",
        "API_PATRONI_URL": 'data:application/json,{"state":"running","role":"primary"}',
        "COMMUNICATIONS_WORKER_RELEASE_HELPER": str(RELEASE),
    })
    (project / "runtime.json").write_text(json.dumps({
        "api_image": OLD, "worker_image": OLD, "running": True, "revision": 3,
    }))
    docker = tmp_path / "bin/docker"
    docker.write_text(f"#!{sys.executable}\n" + FAKE_DOCKER)
    Path(env["API_DEPLOY_CAPACITY_HELPER"]).write_text(
        "require_deploy_capacity() { docker capacity-check; }\n"
    )
    migration = tmp_path / "migration.sh"
    migration.write_text('''set -eu
source "$API_DEPLOY_CAPACITY_HELPER"
require_deploy_capacity
test -e "$API_PROJECT_DIR/.ha-idle-worker-capacity.json"
touch "$API_PROJECT_DIR/migration-ran"
''')
    env["PATRONI_MIGRATION_SCRIPT"] = str(migration)
    result = subprocess.run(["bash", str(PATRONI_RUNNER)], env=env, text=True,
                            capture_output=True, timeout=35)
    assert result.returncode == 0, result.stderr
    assert (project / "migration-ran").exists()
    assert snapshot(env)[1]["running"]
    assert not (project / ".ha-idle-worker-capacity.json").exists()


def test_unsafe_journal_is_not_followed(release_env):
    project, _ = snapshot(release_env)
    target = project / "unrelated"
    target.write_text("preserve\n")
    (project / ".ha-idle-worker-capacity.json").symlink_to(target)
    assert run(release_env, "recover").returncode != 0
    assert target.read_text() == "preserve\n"


def test_timeout_cannot_leave_a_late_starting_grandchild(release_env):
    assert run(release_env, "prepare deploy").returncode == 0
    change(release_env, api_image=NEW, delayed_start=True)
    code = f"""import importlib.util, sys
spec = importlib.util.spec_from_file_location('guard', {str(GUARD)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.COMMAND_TIMEOUT_SECONDS = 0.4
sys.argv = ['guard', 'start_candidate']
module.main()
"""
    project, _ = snapshot(release_env)
    result = subprocess.run(
        [sys.executable, str(LOCK), "exec", str(project / ".deploy.lock"),
         sys.executable, "-c", code], env=release_env, text=True,
        capture_output=True, timeout=15,
    )
    assert result.returncode != 0
    time.sleep(2.1)
    assert not (project / "late-start").exists()
    assert not (project / "sql-held").exists()
    record = json.loads((project / ".ha-idle-worker-capacity.json").read_text())
    assert record["phase"] == "uncertain"
    assert (project / ".ha-communications-worker-release-fenced").exists()
    assert run(release_env, "recover").returncode != 0


@pytest.mark.parametrize("switch_revision,direct_without_guard,removed_during_stop", [
    (False, False, False), (True, False, False), (False, True, False),
    (False, False, True),
])
def test_actual_deploy_entrypoint_checks_control_before_candidate_start(
    tmp_path, switch_revision, direct_without_guard, removed_during_stop,
):
    from tests.unit.test_patroni_candidate_transactions import (
        PATRONI_RUNNER, _patroni_runner_env,
    )

    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    env.update({
        "API_PATRONI_URL": 'data:application/json,{"state":"running","role":"primary"}',
        "COMMUNICATIONS_WORKER_RELEASE_HELPER": str(RELEASE),
        "PATRONI_DEPLOY_SCRIPT": str(ROOT / "scripts/ha/deploy_patroni_api_node.sh"),
        "API_PREVIOUS_BACKEND_IMAGE": OLD,
        "EXPECTED_PREVIOUS_IMAGE": OLD,
        "EXPECTED_CANDIDATE_IMAGE": NEW,
        "BACKEND_IMAGE": NEW,
        "API_BLUE_GREEN_SCRIPT": str(tmp_path / "bluegreen.sh"),
        "GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT": str(tmp_path / "prepare-token.sh"),
    })
    (project / "runtime.json").write_text(json.dumps({
        "api_image": OLD, "worker_image": OLD, "running": True, "revision": 3,
    }))
    change(env, removed_during_stop=removed_during_stop)
    Path(env["GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT"]).write_text("#!/bin/bash\nexit 0\n")
    docker = tmp_path / "bin/docker"
    docker.write_text(f"#!{sys.executable}\n" + FAKE_DOCKER)
    Path(env["API_DEPLOY_CAPACITY_HELPER"]).write_text(
        "require_deploy_capacity() { docker capacity-check; }\n"
    )
    curl = tmp_path / "bin/curl"
    curl.write_text('#!/bin/sh\nprintf \'{"state":"running","role":"primary"}\\n\'\n')
    curl.chmod(0o755)
    bluegreen = Path(env["API_BLUE_GREEN_SCRIPT"])
    script = f'''import json, os
from pathlib import Path
p = Path(os.environ["API_PROJECT_DIR"])
s = json.loads((p / "runtime.json").read_text())
s["api_image"] = os.environ["BACKEND_IMAGE"]
if {switch_revision!r}: s["revision"] += 1
(p / "runtime.json").write_text(json.dumps(s))
(p / ".env").write_text("BACKEND_IMAGE=" + os.environ["BACKEND_IMAGE"] + "\\n")
'''
    bluegreen.write_text(f"#!/bin/bash\n{shlex.quote(sys.executable)} - <<'PY'\n{script}\nPY\n")
    bluegreen.chmod(0o755)
    reconcile = Path(env["API_RECONCILE_SCRIPT"])
    reconcile.write_text(f'''#!/bin/bash
set -eu
if test "${{API_RECONCILE_OPERATION:-reconcile}}" = verify; then exit 0; fi
{shlex.quote(sys.executable)} - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ["API_PROJECT_DIR"])
s = json.loads((p / "runtime.json").read_text())
s["api_image"] = os.environ["API_RECONCILE_BACKEND_IMAGE"]
(p / "runtime.json").write_text(json.dumps(s))
PY
''')
    command = ["bash", str(PATRONI_RUNNER)]
    if direct_without_guard:
        env.pop("BOT_VOICE_TRANSCRIPTION_API_KEY", None)
        assert run(env, "prepare deploy").returncode == 0
        env["API_COMPOSE_FILE"] = "compose.yml.candidate"
        env.pop("API_IDLE_WORKER_CAPACITY_GUARD", None)
        command = [sys.executable, str(LOCK), "exec", str(project / ".deploy.lock"),
                   "bash", env["PATRONI_DEPLOY_SCRIPT"]]
    result = subprocess.run(command, env=env, text=True,
                            capture_output=True, timeout=40)
    state = snapshot(env)[1]
    commands = [json.loads(line) for line in (project / "commands.log").read_text().splitlines()]
    starts = [command for command in commands if "up" in command]
    if direct_without_guard:
        assert result.returncode != 0
        assert not starts
        assert not state["running"]
        assert (project / ".ha-idle-worker-capacity.json").exists()
        assert (project / ".ha-communications-worker-release-fenced").exists()
        assert "requires its verified startup guard" in result.stdout
    elif switch_revision:
        assert result.returncode != 0
        assert not starts, result.stdout + result.stderr
        assert not state["running"]
        assert state["api_image"] == OLD
        assert (project / ".ha-idle-worker-capacity.json").exists()
        assert (project / ".ha-communications-worker-release-fenced").exists()
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert state["running"] and state["worker_image"] == NEW
        assert starts and "candidate" in starts[-1][starts[-1].index("-f") + 1]
        assert not (project / ".ha-idle-worker-capacity.json").exists()
