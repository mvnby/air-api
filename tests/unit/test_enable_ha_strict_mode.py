import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/ha/enable_ha_strict_mode.py"


spec = importlib.util.spec_from_file_location("enable_ha_strict_mode", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class FakeCompleted:
    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_dry_run_does_not_call_subprocess(monkeypatch, capsys):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api", "--dry-run"]) == 0

    assert calls == []
    output = capsys.readouterr().out
    assert "would run and wait for check-cloudflare-lb-config.yml required=true" in output
    assert "would set GitHub variable API_HA_READINESS_STRICT=true" in output
    assert "would run final HA status report with --require-strict" in output


def test_main_runs_proofs_before_enabling_strict_variables(monkeypatch):
    calls = []
    run_id = 28640000000

    def fake_runner(args, stdin):
        nonlocal run_id
        args = list(args)
        calls.append((args, stdin))
        if args[:3] == ["gh", "workflow", "run"]:
            run_id += 1
            return FakeCompleted(stdout=f"https://github.com/mvnby/air-api/actions/runs/{run_id}\n")
        return FakeCompleted()

    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api"]) == 0

    workflow_calls = [args for args, _stdin in calls if args[:3] == ["gh", "workflow", "run"]]
    variable_calls = [args for args, _stdin in calls if args[:3] == ["gh", "variable", "set"]]
    first_variable_index = next(index for index, call in enumerate(calls) if call[0][:3] == ["gh", "variable", "set"])
    last_watch_index = max(index for index, call in enumerate(calls) if call[0][:3] == ["gh", "run", "watch"])
    strict_external_index = next(
        index
        for index, call in enumerate(calls)
        if call[0][-1] == "--require-strict" and "check_ha_external_prerequisites.py" in call[0][1]
    )
    final_report_index = next(
        index
        for index, call in enumerate(calls)
        if call[0][-1] == "--require-strict" and "report_ha_status.py" in call[0][1]
    )

    assert [call[3] for call in workflow_calls] == [
        "check-cloudflare-lb-config.yml",
        "check-postgres-pitr.yml",
        "postgres-pitr-restore-drill.yml",
        "check-api-ha-readiness.yml",
    ]
    assert ["-f", "strict=true"] in [
        workflow_calls[-1][index : index + 2] for index in range(len(workflow_calls[-1]) - 1)
    ]
    assert last_watch_index < first_variable_index
    assert [call[3] for call in variable_calls] == [
        "CLOUDFLARE_LB_CONFIG_REQUIRED",
        "POSTGRES_PITR_REQUIRED",
        "API_HA_READINESS_STRICT",
    ]
    assert all(stdin == "true\n" for _args, stdin in calls if _args[:3] == ["gh", "variable", "set"])
    assert last_watch_index < first_variable_index < strict_external_index < final_report_index
    assert calls[-1][0][-1] == "--require-strict"
    assert "report_ha_status.py" in calls[-1][0][1]


def test_workflow_output_without_url_falls_back_to_recent_run_list(monkeypatch):
    calls = []
    real_datetime = module.datetime

    def fake_runner(args, stdin):
        args = list(args)
        calls.append((args, stdin))
        if args[:3] == ["gh", "workflow", "run"]:
            return FakeCompleted(stdout="Created workflow_dispatch event\n")
        if args[:3] == ["gh", "run", "list"]:
            return FakeCompleted(
                stdout='[{"databaseId":28639999999,"createdAt":"2026-07-03T05:08:21Z",'
                '"url":"https://github.com/mvnby/air-api/actions/runs/28639999999"}]'
            )
        return FakeCompleted()

    class FrozenDatetime:
        @staticmethod
        def now(_tz):
            return real_datetime(2026, 7, 3, 5, 8, 22, tzinfo=module.timezone.utc)

        @staticmethod
        def fromisoformat(value):
            return real_datetime.fromisoformat(value)

    monkeypatch.setattr(module, "_run_subprocess", fake_runner)
    monkeypatch.setattr(module, "datetime", FrozenDatetime)

    run_id = module.trigger_and_wait_workflow(
        module.PROOF_WORKFLOWS[0],
        repo="mvnby/air-api",
        ref="main",
    )

    assert run_id == "28639999999"
    assert any(args[:3] == ["gh", "run", "list"] for args, _stdin in calls)
    assert any(args[:3] == ["gh", "run", "watch"] and args[3] == "28639999999" for args, _stdin in calls)


def test_failed_proof_does_not_enable_strict_variables(monkeypatch):
    calls = []

    def fake_runner(args, stdin):
        args = list(args)
        calls.append((args, stdin))
        if args[:3] == ["gh", "workflow", "run"]:
            return FakeCompleted(stdout="https://github.com/mvnby/air-api/actions/runs/28636799268\n")
        if args[:3] == ["gh", "run", "watch"] and args[3] == "28636799268":
            return FakeCompleted(stderr="workflow failed", returncode=1)
        return FakeCompleted()

    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api"]) == 1

    assert not any(args[:3] == ["gh", "variable", "set"] for args, _stdin in calls)


def test_failed_final_status_report_keeps_strict_helper_failed(monkeypatch, capsys):
    calls = []
    run_id = 28640000000

    def fake_runner(args, stdin):
        nonlocal run_id
        args = list(args)
        calls.append((args, stdin))
        if args[:3] == ["gh", "workflow", "run"]:
            run_id += 1
            return FakeCompleted(stdout=f"https://github.com/mvnby/air-api/actions/runs/{run_id}\n")
        if "report_ha_status.py" in args[1]:
            return FakeCompleted(stderr="strict report failed", returncode=1)
        return FakeCompleted()

    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api"]) == 1

    assert any(args[:3] == ["gh", "variable", "set"] for args, _stdin in calls)
    assert "strict report failed" in capsys.readouterr().out
