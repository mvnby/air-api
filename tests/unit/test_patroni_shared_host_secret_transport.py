import subprocess
from pathlib import Path

import pytest

from tests.unit.test_patroni_candidate_transactions import (
    PATRONI_RUNNER,
    REPO_ROOT,
    _executable,
    _patroni_runner_env,
)


@pytest.mark.parametrize("operation", ["migrate", "deploy"])
@pytest.mark.parametrize("child_exit", [0, 42])
def test_voice_secret_survives_both_lock_reexecutions(tmp_path, operation, child_exit):
    env, project = _patroni_runner_env(tmp_path, child_exit=child_exit)
    shared = tmp_path / "belzakupki"
    shared.mkdir(mode=0o700)
    lifecycle = tmp_path / "shared-lifecycle.sh"
    lifecycle.write_text(
        (REPO_ROOT / "scripts/ha/shared_host_belzakupki_guard_lifecycle.sh")
        .read_text()
        .replace("/opt/belzakupki", str(shared))
    )
    guard = tmp_path / "shared-guard.sh"
    guard_log = tmp_path / "shared-guard.log"
    _executable(guard, '''#!/usr/bin/env bash
set -euo pipefail
test -z "${BOT_VOICE_TRANSCRIPTION_API_KEY+x}"
test -z "${VOICE_SECRET+x}"
if [[ "$1" == enabled ]]; then printf 'enabled\n'; exit 0; fi
printf '%s\n' "$1" >> "$SHARED_GUARD_LOG"
''')
    child = Path(env["PATRONI_DEPLOY_SCRIPT"])
    child.write_text(child.read_text().replace(
        'test -f "$VOICE_SYNC_LOG"',
        'test -f "$VOICE_SYNC_LOG"\n'
        'python3 "$API_DEPLOY_LOCK_HELPER" verify "$API_PROJECT_DIR/.deploy.lock" 9\n'
        'python3 "$API_DEPLOY_LOCK_HELPER" verify "$SHARED_LOCK_PATH" 8',
    ))
    env.update({
        "PATRONI_CANDIDATE_OPERATION": operation,
        "PATRONI_MIGRATION_SCRIPT": str(child),
        "API_SHARED_HOST_BELZAKUPKI_GUARD_LIFECYCLE": str(lifecycle),
        "API_SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT": str(guard),
        "SHARED_GUARD_LOG": str(guard_log),
        "SHARED_LOCK_PATH": str(shared / ".kitlane-deploy.lock"),
    })

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)], env=env, text=True,
        capture_output=True, timeout=30, check=False,
    )

    assert result.returncode == child_exit, result.stderr
    assert Path(env["VOICE_SYNC_LOG"]).is_file()
    assert "test-voice-secret" not in result.stdout + result.stderr
    assert guard_log.read_text().splitlines() == ["prepare", "restore"]
    assert not (project / "compose.yml.candidate").exists()
