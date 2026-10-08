import argparse
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.ha import run_postgres_pitr_tool as tool
from scripts.ha import run_postgres_pitr_manual as manual
from scripts.ha import run_postgres_pitr_workflow as workflow
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES

REPO = Path(__file__).resolve().parents[2]
DRILL = REPO / 'scripts/ha/restore_postgres_pitr_drill.sh'
GUARD = REPO / 'scripts/ha/require_deploy_capacity.sh'


def run_guard(tmp_path, available, cap='768', extra='', command=None):
    meminfo = tmp_path / 'meminfo'
    meminfo.write_text(f'MemAvailable: {available} kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n{extra}')
    result = subprocess.run(
        ['bash', '-ec', command or 'source "$1"; require_drill_capacity "$4" "$2" "$3"; touch "$5"',
         'test', str(DRILL), str(GUARD), str(meminfo), cap, str(tmp_path / 'effect')],
        env={**os.environ, 'RECOVERY_MEMORY_MIB': '4096'}, capture_output=True, text=True,
    )
    return result, tmp_path / 'effect'


@pytest.mark.parametrize('available', ['1310719', 'unknown', '-1', '9999999999999'])
def test_rejects_low_or_malformed_meminfo_before_effect(tmp_path, available):
    result, effect = run_guard(tmp_path, available)
    assert result.returncode != 0
    assert not effect.exists()


@pytest.mark.parametrize('extra', ['MemAvailable: 9999999 kB\n', 'SwapFree: 0 kB\n'])
def test_rejects_ambiguous_meminfo_before_effect(tmp_path, extra):
    result, effect = run_guard(tmp_path, '1310720', extra=extra)
    assert result.returncode != 0
    assert not effect.exists()


@pytest.mark.parametrize('cap,available', [('768', '1310720'), ('1024', '1572864'), ('4096', '4718592')])
def test_accepts_exact_largest_sequential_stage_plus_reserve(tmp_path, cap, available):
    result, effect = run_guard(tmp_path, available, cap)
    assert result.returncode == 0, result.stderr
    assert effect.exists()


def test_old_default_is_rejected_at_observed_production_available_memory(tmp_path):
    result, effect = run_guard(tmp_path, '1479092', '4096')
    assert result.returncode != 0
    assert 'required=4718592KiB' in result.stderr
    assert not effect.exists()


def test_memory_change_between_stages_stops_before_next_effect(tmp_path):
    result, effect = run_guard(tmp_path, '1310720', command='''
source "$1"
require_drill_capacity "$4" "$2" "$3"
printf 'MemAvailable: 1310719 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n' > "$3"
require_drill_capacity "$4" "$2" "$3"
touch "$5"
''')
    assert result.returncode != 0
    assert not effect.exists()


@pytest.mark.parametrize('cap', ['767', '4097', '0768', '+768', '768.0', '768m', '1', '999999999999999999999'])
def test_shell_and_both_transports_reject_noncanonical_or_out_of_bounds(tmp_path, cap):
    result, effect = run_guard(tmp_path, '9999999', cap)
    assert result.returncode != 0 and not effect.exists()
    for module in (workflow, manual):
        with pytest.raises(argparse.ArgumentTypeError):
            module.parse_recovery_memory_mib(cap)


@pytest.mark.parametrize('value', [True, '768', 767, 4097, 768.0])
def test_programmatic_transports_reject_untyped_cap(value):
    for module in (workflow, manual):
        with pytest.raises(RuntimeError):
            module.validate_recovery_memory_mib('restore-drill', value)


def test_cap_reaches_the_remote_manual_command_and_other_phases_reject_it():
    command = workflow._remote_command(
        phase='restore-drill', target=PATRONI_NODES[0], expected_database_role='',
        operation_id='a' * 32, expected_release_sha256='b' * 64,
        backup_id='', target_time='', recovery_memory_mib=768,
    )
    assert '--recovery-memory-mib 768' in command
    for module in (workflow, manual):
        with pytest.raises(RuntimeError):
            module.validate_recovery_memory_mib('verify', 768)


def test_capacity_checks_precede_operational_effects_and_all_stages():
    source = DRILL.read_text()
    driver = source[source.index('target_mode="restore_point"'):]
    check = 'require_drill_capacity "${RECOVERY_MEMORY_MIB}"'
    assert driver.index(check) < driver.index('pg_create_restore_point(')
    assert driver.index(check) < driver.index('mvn-patroni-archive-wal')
    for stage in ['"${TOOL_RUNNER}" --phase wal-upload', '"${TOOL_RUNNER}" "${prepare_args[@]}"',
                  'if ! verify_drill_basebackup', 'start_drill_recovery "${container}"']:
        assert driver[:driver.index(stage)].rstrip().endswith(check)


def test_reviewed_default_and_actual_recovery_cgroup_flags():
    source = DRILL.read_text()
    assert 'RECOVERY_MEMORY_MIB="${RECOVERY_MEMORY_MIB:-768}"' in source
    assert '--memory "${recovery_memory_mib}m"' in source
    assert '--memory-swap "${recovery_memory_mib}m"' in source
    assert '--memory 4g' not in source


@pytest.mark.parametrize("paths,expected", [
    (["manager_frontend/src/views/CustomerDetail.vue"], "false"),
    (["scripts/ha/restore_postgres_pitr_drill.sh"], "true"),
    (["scripts/ha/run_postgres_pitr_tool.py"], "true"),
    (["scripts/ha/postgres_pitr_recovery_config.py"], "true"),
    ([], "true"),
])
def test_existing_ci_selects_actual_physical_proof_from_complete_diff(tmp_path, paths, expected):
    config = yaml.load((REPO/".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    step = next(s for s in config["jobs"]["changes"]["steps"] if s.get("id") == "pitr-proof")
    (tmp_path/"change-scope.json").write_text(json.dumps({"schema":1,"changes":[{"path":p} for p in paths]}))
    output = tmp_path/"output"
    result = subprocess.run(["bash","-ec",step["run"]],
        env={**os.environ,"RUNNER_TEMP":str(tmp_path),"GITHUB_OUTPUT":str(output)},
        capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == f"run={expected}\n"
    unit_steps = config["jobs"]["python-tests"]["steps"]
    proof = next(s for s in unit_steps if s.get("id") == "pitr-capacity")
    assert "matrix.suite == 'unit'" in proof["if"]
    assert "!= 'false'" in proof["if"] # Missing/unknown output executes, never silently skips.
    assert proof.get("continue-on-error", "false") == "false"


def test_existing_ci_selector_rejects_invalid_report(tmp_path):
    config = yaml.load((REPO/".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    step = next(s for s in config["jobs"]["changes"]["steps"] if s.get("id") == "pitr-proof")
    (tmp_path/"change-scope.json").write_text('{"changes":[]}')
    output = tmp_path/"output"
    result = subprocess.run(["bash","-ec",step["run"]],
        env={**os.environ,"RUNNER_TEMP":str(tmp_path),"GITHUB_OUTPUT":str(output)},capture_output=True)
    assert result.returncode != 0 and not output.exists()


def test_planned_tool_stage_matches_actual_isolated_tool_cgroup():
    argv = tool._base_command("ghcr.io/mvnby/air-api/backend@sha256:" + "a"*64,
        operation_id="b"*32,phase="restore-prepare",secrets_already_validated=True)
    assert argv[argv.index("--memory")+1] == "768m"


@pytest.mark.parametrize("available", ["1310719", "unknown"])
def test_manual_capacity_failure_precedes_reconcile_and_operation_record(monkeypatch, tmp_path, available):
    from tests.unit.test_postgres_pitr_manual_runner import _run_setup

    project, _, calls, attestations = _run_setup(monkeypatch, tmp_path)
    reconciled = []
    operation_guard = manual._load_operation_guard()
    operation_guard.reconcile_project_operations = reconciled.append

    def reject(cap):
        assert cap == 768
        assert attestations  # Installed shell and guard hashes are already attested.
        result, effect = run_guard(tmp_path, available)
        assert result.returncode != 0 and not effect.exists()
        raise RuntimeError(result.stderr)

    monkeypatch.setattr(manual, "_require_drill_capacity", reject)
    with pytest.raises(RuntimeError, match="memory headroom|MemAvailable"):
        manual.run_manual(
            phase="restore-drill", project_dir=str(project),
            compose_file="docker-compose.patroni.yml", operation_id="a" * 32,
            expected_release_sha256="f" * 64, recovery_memory_mib=768,
        )
    assert reconciled == [] and calls == []


def test_manual_capacity_uses_attested_shell_and_ignores_inherited_environment(monkeypatch):
    calls = []
    monkeypatch.setattr(manual.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setenv("API_DEPLOY_MEMINFO_FILE", "/attacker/meminfo")
    manual._require_drill_capacity(768)
    args, kwargs = calls[0]
    assert args[-2:] == ["/usr/local/sbin/mvn-postgres-pitr-restore-drill", "768"]
    assert kwargs["check"] is True and kwargs["timeout"] == 10
    assert set(kwargs["env"]) == {"PATH"}


def test_physical_proof_removes_only_owned_containers_before_fixture(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from scripts.ci import prove_pitr_recovery_capacity as proof

    events = []
    outputs = iter(["owned-source\nowned-recovery\nforeign-test\n", "foreign-test\n"])

    def run(args, **kwargs):
        if args[1] == "container":
            events.append("list")
            return SimpleNamespace(stdout=next(outputs), returncode=0)
        events.append(args[-1])
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(proof, "run", run)
    monkeypatch.setattr(proof.shutil, "rmtree", lambda root: events.append(("delete", root)))
    proof.cleanup_owned_runtime(["owned-source", "owned-recovery", "owned-verify"], tmp_path)
    assert events == ["list", "owned-source", "owned-recovery", "list", ("delete", tmp_path)]


@pytest.mark.parametrize("mode", ["daemon-failure", "remaining-container", "remove-failure"])
def test_physical_cleanup_failure_keeps_mounted_fixture_and_fails(monkeypatch, tmp_path, mode):
    from types import SimpleNamespace
    from scripts.ci import prove_pitr_recovery_capacity as proof

    deleted = []
    lists = iter(["owned\n", "owned\n" if mode == "remaining-container" else ""])

    def run(args, **kwargs):
        if args[1] == "container":
            if mode == "daemon-failure":
                raise subprocess.CalledProcessError(1, args, stderr="daemon unavailable")
            return SimpleNamespace(stdout=next(lists), returncode=0)
        return SimpleNamespace(returncode=1 if mode == "remove-failure" else 0, stderr="failed")

    monkeypatch.setattr(proof, "run", run)
    monkeypatch.setattr(proof.shutil, "rmtree", deleted.append)
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        proof.cleanup_owned_runtime(["owned"], tmp_path)
    assert deleted == []


def test_physical_cleanup_failure_revokes_pass_artifact_and_fails_step(monkeypatch, tmp_path):
    from scripts.ci import prove_pitr_recovery_capacity as proof

    def reject(*args):
        raise RuntimeError("daemon unavailable")

    monkeypatch.setattr(proof, "cleanup_owned_runtime", reject)
    evidence = tmp_path / "evidence.json"
    with pytest.raises(RuntimeError, match="daemon unavailable"):
        proof.finish_proof({"status": "PASS", "physical_recovery_executed": True}, [], tmp_path, evidence)
    result = json.loads(evidence.read_text())
    assert result["status"] == "FAILED" and result["test_runtime_cleaned"] is False
    assert result["cleanup_error"] == "daemon unavailable"


def test_synthetic_archiver_hides_partial_segment_until_complete(tmp_path):
    import shlex
    import time
    from scripts.ci import prove_pitr_recovery_capacity as proof

    wal = tmp_path / "wal"
    wal.mkdir()
    source = tmp_path / "source-wal"
    with source.open("wb") as stream:
        stream.truncate(16 * 1024**2)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    started, release = tmp_path / "started", tmp_path / "release"
    cp = fake_bin / "cp"
    cp.write_text("""#!/bin/sh
printf partial > "$2"
touch "$TEST_STARTED"
while [ ! -e "$TEST_RELEASE" ]; do sleep 0.01; done
/bin/cp "$1" "$2"
""")
    cp.chmod(0o755)
    name = "00000001000000000000000E"
    command = proof.SYNTHETIC_ARCHIVE_COMMAND.replace("/pitr-wal", shlex.quote(str(wal)))
    command = command.replace("%p", shlex.quote(str(source))).replace("%f", name)
    process = subprocess.Popen(["bash", "-ec", command], env={**os.environ,
        "PATH": str(fake_bin) + ":" + os.environ["PATH"],
        "TEST_STARTED": str(started), "TEST_RELEASE": str(release)})
    try:
        deadline = time.monotonic() + 3
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert started.exists(), "controlled partial copy did not start"
        assert (wal / (name + ".pending")).read_bytes() == b"partial"
        assert not (wal / name).exists(), "selector could observe a partial final segment"
        release.touch()
        assert process.wait(timeout=3) == 0
        assert (wal / name).stat().st_size == 16 * 1024**2
        assert not (wal / (name + ".pending")).exists()
    finally:
        release.touch(exist_ok=True)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)


def test_controller_omitted_cap_forwards_reviewed_default_and_verify_has_no_cap():
    arguments = dict(target=PATRONI_NODES[0], expected_database_role="",
        operation_id="a" * 32, expected_release_sha256="b" * 64, backup_id="", target_time="")
    assert "--recovery-memory-mib 768" in workflow._remote_command(phase="restore-drill", **arguments)
    assert "--recovery-memory-mib" not in workflow._remote_command(phase="verify", **arguments)
