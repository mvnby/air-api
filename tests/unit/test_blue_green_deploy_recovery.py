import time
from pathlib import Path

import pytest

from tests.unit.blue_green_deploy_harness import (
    NEW_IMAGE,
    OLD_IMAGE,
    environment as _environment,
    run as _run,
)


def test_failed_candidate_keeps_legacy_active(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_CANDIDATE_READY"] = "true"

    result = _run(env)

    assert result.returncode != 0
    assert not (project / ".active-api-slot").exists()
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(encoding="utf-8")
    assert "proxy_pass http://127.0.0.1:8000;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    commands = command_log.read_text(encoding="utf-8")
    assert "stop -t 5 app-blue" in commands
    assert not any(line.endswith(" stop -t 5 app") for line in commands.splitlines())


def test_pre_stop_rollback_keeps_candidate_live_when_old_route_restore_fails(
    tmp_path,
):
    env, project, _, command_log = _environment(tmp_path)
    env.update(
        {
            "API_PUBLIC_READY_URL": "https://public.test/api/ready",
            "FAIL_PUBLIC_READY": "true",
            "FAIL_ROLLBACK_OLD_ROUTE": "true",
        }
    )

    result = _run(env)

    assert result.returncode != 0
    commands = command_log.read_text(encoding="utf-8")
    assert not any(
        line.endswith(" stop -t 5 app-blue") for line in commands.splitlines()
    )
    assert (project / ".active-api-slot").read_text(encoding="utf-8").strip() == "blue"
    assert "proxy_pass http://127.0.0.1:18001;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    assert f"BACKEND_IMAGE={NEW_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rollback_failed" in summary
    assert "old_route_confirmed=false" in summary
    assert "candidate_preserved=true" in summary


def test_same_image_retry_does_not_accept_candidate_without_scheduler_ownership(
    tmp_path,
):
    env, _, _, command_log = _environment(tmp_path)
    env.update(
        {
            "API_PUBLIC_READY_URL": "https://public.test/api/ready",
            "FAIL_PUBLIC_READY": "true",
            "FAIL_ROLLBACK_OLD_ROUTE": "true",
        }
    )

    first = _run(env)

    assert first.returncode != 0
    env.pop("FAIL_PUBLIC_READY")
    env.pop("FAIL_ROLLBACK_OLD_ROUTE")
    env["FAKE_RUNTIME_APP_BLUE_IMAGE"] = NEW_IMAGE
    env["FAKE_RUNTIME_BOT_IMAGE"] = NEW_IMAGE
    env["FAIL_SCHEDULER_AFTER_ROUTE_FAILURE"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "2"
    second = _run(env)

    assert second.returncode != 0
    assert "requested image is already active" not in second.stdout
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=already_active" not in summary
    assert not any(
        line.endswith(" stop -t 5 app")
        for line in command_log.read_text(encoding="utf-8").splitlines()
    )


def test_pre_stop_rollback_requires_confirmed_candidate_stop(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    env.update(
        {
            "API_PUBLIC_READY_URL": "https://public.test/api/ready",
            "FAIL_PUBLIC_READY": "true",
            "FAIL_CANDIDATE_STOP": "true",
        }
    )

    result = _run(env)

    assert result.returncode != 0
    commands = command_log.read_text(encoding="utf-8")
    assert any(
        line.endswith(" stop -t 5 app-blue") for line in commands.splitlines()
    )
    assert "proxy_pass http://127.0.0.1:8000;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    assert not (project / ".active-api-slot").exists()
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    assert f"bot_image {OLD_IMAGE}" in commands
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rollback_failed" in summary
    assert "old_route_confirmed=true" in summary
    assert "candidate_stop_confirmed=false" in summary


@pytest.mark.parametrize("health_delay", ["0", "1"])
def test_scheduler_gate_requires_monotonic_stability_despite_delay_override(
    tmp_path,
    health_delay,
):
    env, _, _, _ = _environment(tmp_path)
    env.pop("API_SCHEDULER_STABILITY_SECONDS")
    env["API_HEALTH_DELAY_SECONDS"] = health_delay
    env["API_SCHEDULER_READY_ATTEMPTS"] = "6"

    started = time.monotonic()
    result = _run(env)
    elapsed = time.monotonic() - started

    assert result.returncode != 0
    assert elapsed < 2
    assert "did not remain running for 6 consecutive samples and at least 9s" in (
        result.stdout
    )


def test_scheduler_activation_timeout_rolls_back_after_old_service_stop(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_SCHEDULER_RUNNING"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "2"

    result = _run(env)

    assert result.returncode != 0
    commands = command_log.read_text(encoding="utf-8")
    lines = commands.splitlines()
    assert any(line.endswith(" stop -t 5 app") for line in lines)
    assert "up -d --no-deps app" in commands
    assert "stop -t 5 app-blue" in commands
    assert "rm -f app-blue" in commands
    candidate_stop = next(
        index
        for index, line in enumerate(lines)
        if line.endswith(" stop -t 5 app-blue")
    )
    buffer_ready = next(
        index for index, line in enumerate(lines) if ":18002/api/ready" in line
    )
    buffer_route = next(
        index
        for index, line in enumerate(lines)
        if line == "upstream proxy_pass http://127.0.0.1:18002;"
    )
    old_start = next(
        index for index, line in enumerate(lines) if line.endswith(" up -d --no-deps app")
    )
    rollback_ready = next(
        index for index, line in enumerate(lines) if ":8000/api/ready" in line
    )
    assert buffer_ready < buffer_route < candidate_stop < old_start < rollback_ready
    assert "rm -s -f app-green" in commands
    assert f'override     image: "{OLD_IMAGE}"' in commands
    assert "override     restart: unless-stopped" in commands
    assert 'override       DB_BOOTSTRAP_ENABLED: "false"' in commands
    assert 'override       SCHEDULER_ENABLED: "false"' in commands
    assert 'override       BOT_ENABLED: "false"' in commands
    assert 'override       API_READY_ENABLED: "true"' in commands
    assert not (project / ".active-api-slot").exists()
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )


def test_uncertain_initial_active_stop_uses_buffer_before_candidate_stop(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_INITIAL_ACTIVE_STOP"] = "true"

    result = _run(env)

    assert result.returncode != 0
    lines = command_log.read_text(encoding="utf-8").splitlines()
    initial_stop = next(
        index for index, line in enumerate(lines) if line.endswith(" stop -t 5 app")
    )
    buffer_route = next(
        index
        for index, line in enumerate(lines[initial_stop + 1 :], start=initial_stop + 1)
        if line == "upstream proxy_pass http://127.0.0.1:18002;"
    )
    candidate_stop = next(
        index
        for index, line in enumerate(lines[buffer_route + 1 :], start=buffer_route + 1)
        if line.endswith(" stop -t 5 app-blue")
    )
    old_start = next(
        index
        for index, line in enumerate(lines[candidate_stop + 1 :], start=candidate_stop + 1)
        if line.endswith(" up -d --no-deps app")
    )
    assert initial_stop < buffer_route < candidate_stop < old_start
    assert "proxy_pass http://127.0.0.1:8000;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rolled_back" in summary


def test_ready_old_slot_reports_failed_rollback_when_image_state_sync_fails(
    tmp_path,
):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_SCHEDULER_RUNNING"] = "true"
    env["FAIL_PREVIOUS_ENV_WRITE"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "2"

    result = _run(env)

    assert result.returncode != 0
    commands = command_log.read_text(encoding="utf-8")
    assert "proxy_pass http://127.0.0.1:8000;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    assert "rm -s -f app-green" in commands
    assert f"BACKEND_IMAGE={NEW_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rollback_failed" in summary
    assert "previous_image_state_synced=false" in summary


def test_failed_old_readiness_serves_buffer_until_candidate_is_stable(
    tmp_path,
):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_SCHEDULER_BEFORE_FALLBACK"] = "true"
    env["FAIL_ROLLBACK_OLD_READY"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "6"

    result = _run(env)

    assert result.returncode != 0
    commands = command_log.read_text(encoding="utf-8")
    lines = commands.splitlines()
    candidate_stop = next(
        index
        for index, line in enumerate(lines)
        if line.endswith(" stop -t 5 app-blue")
    )
    old_start = next(
        index for index, line in enumerate(lines) if line.endswith(" up -d --no-deps app")
    )
    old_stop = next(
        index
        for index, line in enumerate(lines[old_start + 1 :], start=old_start + 1)
        if line.endswith(" stop -t 5 app")
    )
    fallback_start = next(
        index
        for index, line in enumerate(lines[old_stop + 1 :], start=old_stop + 1)
        if line.endswith(" up -d --no-deps --force-recreate app-blue")
    )
    buffer_ready = next(
        index for index, line in enumerate(lines) if ":18002/api/ready" in line
    )
    buffer_stop = next(
        index
        for index, line in enumerate(lines[fallback_start + 1 :], start=fallback_start + 1)
        if line.endswith(" rm -s -f app-green")
    )
    assert buffer_ready < candidate_stop < old_start < old_stop < fallback_start
    assert fallback_start < buffer_stop
    assert sum(line.endswith(" stop -t 5 app-blue") for line in lines) == 1
    assert (project / ".active-api-slot").read_text(encoding="utf-8").strip() == "blue"
    assert f"BACKEND_IMAGE={NEW_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    assert "proxy_pass http://127.0.0.1:18001;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rollback_failed" in summary
    assert "old_slot_ready=false" in summary
    assert "candidate_api_fallback_ready=true" in summary


def test_candidate_recovery_does_not_route_when_requested_image_sync_fails(
    tmp_path,
):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_SCHEDULER_BEFORE_FALLBACK"] = "true"
    env["FAIL_ROLLBACK_OLD_READY"] = "true"
    env["FAIL_REQUESTED_ENV_WRITE_AFTER_OLD_STOP"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "6"

    result = _run(env)

    assert result.returncode != 0
    commands = command_log.read_text(encoding="utf-8")
    assert sum(
        line.endswith(" up -d --no-deps --force-recreate app-blue")
        for line in commands.splitlines()
    ) == 1
    assert "proxy_pass http://127.0.0.1:18002;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    assert (project / ".rollback-api-buffer.compose.yml").exists()
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rollback_buffer_active" in summary
    assert "candidate_image_state_synced=false" in summary
    assert "candidate_api_fallback_ready=false" in summary
    assert "rollback_buffer_routed=true" in summary


def test_candidate_stop_failure_keeps_buffer_live_and_never_starts_old(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_SCHEDULER_RUNNING"] = "true"
    env["FAIL_CANDIDATE_STOP"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "2"

    result = _run(env)

    assert result.returncode != 0
    commands = command_log.read_text(encoding="utf-8")
    assert "upstream proxy_pass http://127.0.0.1:18002;" in commands
    assert not any(
        line.endswith(" up -d --no-deps app") for line in commands.splitlines()
    )
    assert "proxy_pass http://127.0.0.1:18002;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    marker = project / ".rollback-api-buffer.compose.yml"
    assert marker.exists()
    assert f'image: "{OLD_IMAGE}"' in marker.read_text(encoding="utf-8")
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rollback_buffer_active" in summary
    assert "candidate_stop_confirmed=false" in summary
    assert "rollback_buffer_routed=true" in summary


@pytest.mark.parametrize("retry_image", [NEW_IMAGE, OLD_IMAGE])
def test_preserved_routed_buffer_syncs_image_and_same_image_retry_deploys(
    tmp_path,
    retry_image,
):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_SCHEDULER_RUNNING"] = "true"
    env["FAIL_CANDIDATE_STOP"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "2"

    first = _run(env)

    assert first.returncode != 0
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    first_commands = command_log.read_text(encoding="utf-8")
    assert f"bot_image {OLD_IMAGE}" in first_commands
    assert (project / ".active-api-slot").read_text(encoding="utf-8").strip() == "green"
    first_summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(
        encoding="utf-8"
    )
    assert "rollback_buffer_image_state_synced=true" in first_summary
    assert f"rollback_buffer_image={OLD_IMAGE}" in first_summary

    env.pop("FAIL_SCHEDULER_RUNNING")
    env.pop("FAIL_CANDIDATE_STOP")
    env["FAKE_RUNTIME_APP_GREEN_IMAGE"] = OLD_IMAGE
    env["FAKE_RUNTIME_BOT_IMAGE"] = OLD_IMAGE
    env["BACKEND_IMAGE"] = retry_image
    env["API_SCHEDULER_READY_ATTEMPTS"] = "6"
    second = _run(env)

    assert second.returncode == 0, second.stderr
    second_summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(
        encoding="utf-8"
    )
    assert "status=activated" in second_summary
    assert "status=already_active" not in second_summary
    assert (project / ".active-api-slot").read_text(encoding="utf-8").strip() == "blue"
    assert f"BACKEND_IMAGE={retry_image}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    assert not (project / ".rollback-api-buffer.compose.yml").exists()


def test_buffer_cleanup_failure_is_preserved_as_managed_state(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_SCHEDULER_RUNNING"] = "true"
    env["FAIL_BUFFER_REMOVE"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "2"

    result = _run(env)

    assert result.returncode != 0
    commands = command_log.read_text(encoding="utf-8")
    assert "rm -s -f app-green" in commands
    assert "proxy_pass http://127.0.0.1:8000;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    assert (project / ".rollback-api-buffer.compose.yml").exists()
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rolled_back" in summary
    assert "rollback_buffer_cleanup=false" in summary
    assert "rollback_buffer_routed=false" in summary


def test_partial_buffer_start_is_cleaned_without_stopping_candidate(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_SCHEDULER_RUNNING"] = "true"
    env["FAIL_BUFFER_START"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "2"

    result = _run(env)

    assert result.returncode != 0
    lines = command_log.read_text(encoding="utf-8").splitlines()
    buffer_start = next(
        index
        for index, line in enumerate(lines)
        if "rollback-api-buffer.compose.yml" in line
        and line.endswith(" up -d --no-deps --force-recreate app-green")
    )
    buffer_cleanup = next(
        index
        for index, line in enumerate(lines[buffer_start + 1 :], start=buffer_start + 1)
        if line.endswith(" rm -s -f app-green")
    )
    assert buffer_start < buffer_cleanup
    assert not any(line.endswith(" stop -t 5 app-blue") for line in lines)
    assert "proxy_pass http://127.0.0.1:18001;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    assert not (project / ".rollback-api-buffer.compose.yml").exists()
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rollback_failed" in summary
    assert "candidate_preserved=true" in summary


def test_unhealthy_old_stop_failure_keeps_buffer_and_refuses_candidate_restart(
    tmp_path,
):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_SCHEDULER_BEFORE_FALLBACK"] = "true"
    env["FAIL_ROLLBACK_OLD_READY"] = "true"
    env["FAIL_OLD_STOP"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "6"

    result = _run(env)

    assert result.returncode != 0
    commands = command_log.read_text(encoding="utf-8")
    assert sum(
        line.endswith(" up -d --no-deps --force-recreate app-blue")
        for line in commands.splitlines()
    ) == 1
    assert "proxy_pass http://127.0.0.1:18002;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    assert (project / ".rollback-api-buffer.compose.yml").exists()
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rollback_buffer_active" in summary
    assert "old_slot_stop_confirmed=false" in summary
    assert "rollback_buffer_routed=true" in summary


def test_preserved_buffer_marker_is_removed_only_after_successful_activation(
    tmp_path,
):
    failed_root = tmp_path / "failed"
    failed_root.mkdir()
    failed_env, failed_project, _, _ = _environment(failed_root)
    failed_marker = failed_project / ".rollback-api-buffer.compose.yml"
    failed_marker.write_text("preserved\n", encoding="utf-8")
    failed_env["FAIL_CANDIDATE_READY"] = "true"

    failed = _run(failed_env)

    assert failed.returncode != 0
    assert failed_marker.read_text(encoding="utf-8") == "preserved\n"

    success_root = tmp_path / "success"
    success_root.mkdir()
    success_env, success_project, _, _ = _environment(success_root)
    success_marker = success_project / ".rollback-api-buffer.compose.yml"
    success_marker.write_text("preserved\n", encoding="utf-8")

    succeeded = _run(success_env)

    assert succeeded.returncode == 0, succeeded.stderr
    assert not success_marker.exists()

    rollback_root = tmp_path / "rollback"
    rollback_root.mkdir()
    rollback_env, rollback_project, _, _ = _environment(rollback_root)
    rollback_marker = rollback_project / ".rollback-api-buffer.compose.yml"
    rollback_marker.write_text("preserved\n", encoding="utf-8")
    rollback_env["FAIL_SCHEDULER_RUNNING"] = "true"
    rollback_env["API_SCHEDULER_READY_ATTEMPTS"] = "2"

    rolled_back = _run(rollback_env)

    assert rolled_back.returncode != 0
    assert not rollback_marker.exists()
