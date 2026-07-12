from pathlib import Path

import pytest

from scripts import media_worker


def _claimed_job(*, lease_token: str | None = "lease-token-with-at-least-thirty-two-characters") -> dict:
    return {
        "job_id": "job-1",
        "operation": "background_removal",
        "provider": "rembg",
        "lease_token": lease_token,
    }


def test_run_once_sends_lease_token_when_completing(monkeypatch: pytest.MonkeyPatch):
    completed: dict = {}
    monkeypatch.setattr(media_worker, "_claim_job", lambda *args: _claimed_job())
    monkeypatch.setattr(media_worker, "_download_source", lambda *args: None)
    monkeypatch.setattr(media_worker, "_process_job", lambda *args: None)

    def complete(api_url, token, job_id, worker_id, lease_token, output_path: Path):
        completed.update(
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            output_path=output_path,
        )
        return {"result_asset_id": 42}

    monkeypatch.setattr(media_worker, "_complete_job", complete)

    assert media_worker._run_once("http://api", "api-token", "worker-a", [], 900) is True
    assert completed["job_id"] == "job-1"
    assert completed["worker_id"] == "worker-a"
    assert completed["lease_token"] == _claimed_job()["lease_token"]


def test_run_once_sends_lease_token_when_failing(monkeypatch: pytest.MonkeyPatch):
    failed: dict = {}
    monkeypatch.setattr(media_worker, "_claim_job", lambda *args: _claimed_job())
    monkeypatch.setattr(media_worker, "_download_source", lambda *args: None)

    def fail_processing(*args):
        raise RuntimeError("processor failed")

    def fail(api_url, token, job_id, worker_id, lease_token, error):
        failed.update(
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            error=error,
        )

    monkeypatch.setattr(media_worker, "_process_job", fail_processing)
    monkeypatch.setattr(media_worker, "_fail_job", fail)

    assert media_worker._run_once("http://api", "api-token", "worker-a", [], 900) is True
    assert failed == {
        "job_id": "job-1",
        "worker_id": "worker-a",
        "lease_token": _claimed_job()["lease_token"],
        "error": "processor failed",
    }


def test_run_once_rejects_claim_without_lease_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(media_worker, "_claim_job", lambda *args: _claimed_job(lease_token=None))

    with pytest.raises(RuntimeError, match="deploy the API and worker script together"):
        media_worker._run_once("http://api", "api-token", "worker-a", [], 900)


def test_external_command_uses_argv_and_keeps_job_values_as_single_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    captured: dict = {}
    input_path = tmp_path / "input;touch-not-executed"
    output_path = tmp_path / "output.png"

    def fake_run(command: list[str], *, timeout: int):
        captured["command"] = command
        captured["timeout"] = timeout
        output_path.write_bytes(b"png")
        return media_worker.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setenv("MEDIA_WORKER_COMMAND_TIMEOUT_SECONDS", "42")
    monkeypatch.setattr(media_worker, "_run_command_with_timeout", fake_run)

    media_worker._run_external_command(
        "processor --input {input} --output {output} --job {job_id}",
        job={"job_id": "job;echo-not-executed", "operation": "background_removal"},
        input_path=input_path,
        output_path=output_path,
    )

    assert captured == {
        "command": [
            "processor",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--job",
            "job;echo-not-executed",
        ],
        "timeout": 42,
    }


def test_external_command_requires_input_and_output_placeholders(tmp_path: Path):
    with pytest.raises(RuntimeError, match=r"must contain \{input\} and \{output\}"):
        media_worker._run_external_command(
            "processor --input fixed --output fixed",
            job={},
            input_path=tmp_path / "input",
            output_path=tmp_path / "output",
        )


def test_lease_heartbeat_renews_until_stopped(monkeypatch: pytest.MonkeyPatch):
    renewals = []

    class StopAfterOneRenewal:
        calls = 0

        def wait(self, _interval):
            self.calls += 1
            return self.calls > 1

    def fake_renew(*args):
        renewals.append(args)

    monkeypatch.setattr(media_worker, "_renew_job", fake_renew)
    media_worker._lease_heartbeat(
        stop_event=StopAfterOneRenewal(),
        api_url="http://api",
        token="api-token",
        job_id="job-1",
        worker_id="worker-a",
        lease_token="lease-token-with-at-least-thirty-two-characters",
        lease_seconds=900,
    )

    assert renewals == [
        (
            "http://api",
            "api-token",
            "job-1",
            "worker-a",
            "lease-token-with-at-least-thirty-two-characters",
            900,
        )
    ]
