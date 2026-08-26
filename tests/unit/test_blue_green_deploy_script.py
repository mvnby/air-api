from pathlib import Path

import pytest

from tests.unit.blue_green_deploy_harness import (
    NEW_IMAGE,
    OLD_IMAGE,
    SAFETY_SCRIPT,
    SCRIPT,
    configure_active_slot as _configure_active_slot,
    environment as _environment,
    run as _run,
)


def test_scheduler_gate_records_candidate_slot_after_old_service_removal():
    source = SCRIPT.read_text(encoding="utf-8")
    old_remove = source.index('"${COMPOSE[@]}" rm -f "${active_service}"')
    candidate_slot_write = source.index(
        'atomic_write_line "${ACTIVE_SLOT_FILE}" "${candidate_slot}" 600'
    )
    scheduler_gate = source.index("wait_scheduler_running_url", candidate_slot_write)

    assert old_remove < candidate_slot_write < scheduler_gate


def test_rollback_routes_ready_buffer_before_stopping_candidate():
    source = SAFETY_SCRIPT.read_text(encoding="utf-8")
    rollback = source[source.index("rollback_on_error() {") :]
    buffer_start = rollback.index("rollback_buffer_start")
    buffer_route = rollback.index(
        'rollback_route_slot "${rollback_buffer_slot}" "${candidate_slot}"'
    )
    candidate_stop = rollback.index('rollback_stop_service "${candidate_service}"')
    old_start = rollback.index('"${COMPOSE[@]}" up -d --no-deps "${active_service}"')
    old_ready = rollback.index('"rollback_old"')
    old_route = rollback.index('rollback_route_slot "${active_slot}"')
    buffer_stop = rollback.index("rollback_buffer_stop", old_route)

    assert buffer_start < buffer_route < candidate_stop < old_start < old_ready
    assert old_ready < old_route < buffer_stop


@pytest.mark.parametrize("proxy_mode", ["host_nginx", "container_nginx"])
@pytest.mark.parametrize(
    ("active_slot", "candidate_slot", "buffer_slot"),
    [
        ("legacy", "blue", "green"),
        ("blue", "green", "legacy"),
        ("green", "blue", "legacy"),
    ],
)
def test_zero_gap_buffer_covers_every_slot_and_proxy_combination(
    tmp_path,
    proxy_mode,
    active_slot,
    candidate_slot,
    buffer_slot,
):
    env, project, site, command_log = _environment(tmp_path)
    upstream = _configure_active_slot(env, project, site, active_slot, proxy_mode)
    env["FAIL_SCHEDULER_RUNNING"] = "true"
    env["API_SCHEDULER_READY_ATTEMPTS"] = "2"

    result = _run(env)

    assert result.returncode != 0
    lines = command_log.read_text(encoding="utf-8").splitlines()
    services = {"legacy": "app", "blue": "app-blue", "green": "app-green"}
    ports = {"legacy": 8000, "blue": 18001, "green": 18002}
    target = (
        f"127.0.0.1:{ports[buffer_slot]}"
        if proxy_mode == "host_nginx"
        else f"{services[buffer_slot]}:8000"
    )
    old_target = (
        f"127.0.0.1:{ports[active_slot]}"
        if proxy_mode == "host_nginx"
        else f"{services[active_slot]}:8000"
    )
    buffer_route = next(
        index
        for index, line in enumerate(lines)
        if line == f"upstream proxy_pass http://{target};"
    )
    candidate_stop = next(
        index
        for index, line in enumerate(lines[buffer_route + 1 :], start=buffer_route + 1)
        if line.endswith(f" stop -t 5 {services[candidate_slot]}")
    )
    old_start = next(
        index
        for index, line in enumerate(
            lines[candidate_stop + 1 :], start=candidate_stop + 1
        )
        if line.endswith(f" up -d --no-deps {services[active_slot]}")
    )
    old_ready = next(
        index
        for index, line in enumerate(lines[old_start + 1 :], start=old_start + 1)
        if f":{ports[active_slot]}/api/ready" in line
    )
    old_route = next(
        index
        for index, line in enumerate(lines[old_ready + 1 :], start=old_ready + 1)
        if line == f"upstream proxy_pass http://{old_target};"
    )
    buffer_cleanup = next(
        index
        for index, line in enumerate(lines[old_route + 1 :], start=old_route + 1)
        if line.endswith(f" rm -s -f {services[buffer_slot]}")
    )

    assert buffer_route < candidate_stop < old_start < old_ready < old_route
    assert old_route < buffer_cleanup
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    if active_slot == "legacy":
        assert not (project / ".active-api-slot").exists()
    else:
        assert (project / ".active-api-slot").read_text(
            encoding="utf-8"
        ).strip() == active_slot
    assert old_target in upstream.read_text(encoding="utf-8")


def test_first_deploy_activates_blue_without_touching_database(tmp_path):
    env, project, site, command_log = _environment(tmp_path)

    result = _run(env)

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "pull gotenberg" in commands
    assert "up -d --no-deps --wait --wait-timeout 90 gotenberg" in commands
    assert "pull app-blue" in commands
    assert "run -T --rm --no-deps app-blue alembic upgrade head" in commands
    assert "up -d --no-deps --force-recreate app-blue" in commands
    assert "up -d --no-deps --force-recreate bot" not in commands
    assert "stop -t 5 app" in commands
    assert "rm -f app" in commands
    candidate_ready_calls = [
        line for line in commands.splitlines() if ":18001/api/ready" in line
    ]
    assert len(candidate_ready_calls) >= 7
    lines = commands.splitlines()
    old_remove = next(
        index for index, line in enumerate(lines) if line.endswith(" rm -f app")
    )
    post_stop_scheduler_samples = [
        index
        for index, line in enumerate(lines)
        if index > old_remove and ":18001/api/ready" in line
    ]
    assert len(post_stop_scheduler_samples) >= 6
    assert " pull db" not in commands
    assert " up -d db" not in commands
    assert commands.index("pull gotenberg") < commands.index("pull app-blue")
    assert commands.index(
        "up -d --no-deps --wait --wait-timeout 90 gotenberg"
    ) < commands.index("up -d --no-deps --force-recreate app-blue")
    assert (project / ".active-api-slot").read_text(encoding="utf-8").strip() == "blue"
    assert (project / ".previous-backend-image").read_text(
        encoding="utf-8"
    ).strip() == OLD_IMAGE
    assert f"BACKEND_IMAGE={NEW_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    assert "proxy_pass http://127.0.0.1:18001;" in (
        tmp_path / "nginx/snippets/mvn-api-upstream.conf"
    ).read_text(encoding="utf-8")
    assert "listen 127.0.0.1:18080;" in Path(env["API_NGINX_INTERNAL_FILE"]).read_text(
        encoding="utf-8"
    )
    assert "include " in site.read_text(encoding="utf-8")


def test_deploy_refuses_low_capacity_before_proxy_or_container_mutation(tmp_path):
    env, project, site, command_log = _environment(tmp_path)
    Path(env["API_DEPLOY_MEMINFO_FILE"]).write_text(
        "MemAvailable: 200000 kB\nSwapTotal: 524288 kB\nSwapFree: 1000 kB\n",
        encoding="utf-8",
    )
    original_site = site.read_text(encoding="utf-8")

    result = _run(env)

    assert result.returncode != 0
    assert "insufficient memory headroom" in result.stderr
    assert site.read_text(encoding="utf-8") == original_site
    assert not (project / ".active-api-slot").exists()
    commands = command_log.read_text(encoding="utf-8")
    assert " pull " not in commands
    assert " up " not in commands
    assert "systemctl reload nginx" not in commands


def test_canonical_pitr_marker_has_only_narrow_attested_scrub_exception():
    deploy_source = SCRIPT.read_text(encoding="utf-8")
    safety_source = SAFETY_SCRIPT.read_text(encoding="utf-8")

    assert (
        'PITR_MAINTENANCE_MARKER="/run/mvn-postgres-pitr-maintenance"' in deploy_source
    )
    assert "API_PITR_MAINTENANCE_MARKER:-" not in deploy_source
    lock_verify = deploy_source.index(
        'python3 "${DEPLOY_LOCK_HELPER}" verify "${DEPLOY_LOCK_FILE}" "${DEPLOY_LOCK_FD}"'
    )
    marker_gate = deploy_source.index(
        "require_pitr_maintenance_clear_or_attested_scrub"
    )
    assert lock_verify < marker_gate
    pre_source_gate = deploy_source.index(
        "verify_pitr_maintenance_marker.py pre-source"
    )
    safety_source_load = deploy_source.index('source "${SAFETY_HELPER}"')
    capacity_source_load = deploy_source.index('source "${CAPACITY_HELPER}"')
    assert pre_source_gate < safety_source_load < capacity_source_load < lock_verify
    assert 'if [[ -z "${transaction_id}" ]]' in safety_source
    for pinned_path in (
        "deploy_backend_blue_green.sh",
        "deploy_backend_blue_green_safety.sh",
        "safe_deploy_lock.py",
        "require_deploy_capacity.sh",
        "verify_pitr_maintenance_marker.py",
    ):
        assert f'"${{pinned_root}}/{pinned_path}"' in safety_source
    assert '"${DEPLOY_LOCK_FD}" == "9"' in safety_source
    assert (
        'python3 "${PITR_MARKER_VALIDATOR}" marker "${transaction_id}"' in safety_source
    )


@pytest.mark.parametrize(
    "stop_timeout",
    ["0", "11", "not-an-int", "999999999999999999999999999999999999999"],
)
def test_service_stop_timeout_must_preserve_fencing_window(tmp_path, stop_timeout):
    env, _, _, command_log = _environment(tmp_path)
    env["API_SERVICE_STOP_TIMEOUT_SECONDS"] = stop_timeout

    result = _run(env)

    assert result.returncode != 0
    assert "must be an integer from 1 to 10" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert " ps -q " not in commands
    assert " pull " not in commands
    assert " up " not in commands


def test_bootstrap_only_installs_stable_proxy_without_container_changes(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    env["API_BLUE_GREEN_BOOTSTRAP_ONLY"] = "true"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert " pull " not in commands
    assert " up " not in commands
    assert " stop " not in commands
    assert not (project / ".active-api-slot").exists()
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    assert "listen 127.0.0.1:18080;" in Path(env["API_NGINX_INTERNAL_FILE"]).read_text(
        encoding="utf-8"
    )


def test_next_deploy_uses_green_and_stops_blue(tmp_path):
    env, project, site, command_log = _environment(tmp_path)
    upstream = Path(env["API_NGINX_UPSTREAM_FILE"])
    upstream.parent.mkdir(parents=True, exist_ok=True)
    upstream.write_text("proxy_pass http://127.0.0.1:18001;\n", encoding="utf-8")
    site.write_text(
        f"server {{\n    location / {{\n        include {upstream};\n    }}\n}}\n",
        encoding="utf-8",
    )
    (project / ".active-api-slot").write_text("blue\n", encoding="utf-8")
    env["FAKE_RUNTIME_APP_BLUE_IMAGE"] = OLD_IMAGE

    result = _run(env)

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "pull app-green" in commands
    assert "up -d --no-deps --force-recreate app-green" in commands
    assert "stop -t 5 app-blue" in commands
    assert "rm -f app-blue" in commands
    assert (project / ".active-api-slot").read_text(encoding="utf-8").strip() == "green"
    assert "proxy_pass http://127.0.0.1:18002;" in upstream.read_text(encoding="utf-8")


def test_container_proxy_switches_by_service_name_without_host_nginx(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    proxy_dir = project / "api-proxy"
    proxy_dir.mkdir()
    (proxy_dir / "nginx.conf").write_text("events {}\nhttp {}\n", encoding="utf-8")
    upstream = proxy_dir / "upstream.conf"
    upstream.write_text("proxy_pass http://app:8000;\n", encoding="utf-8")
    env.update(
        {
            "API_PROXY_MODE": "container_nginx",
            "API_PROXY_CONFIG_FILE": str(proxy_dir / "nginx.conf"),
            "API_NGINX_UPSTREAM_FILE": str(upstream),
        }
    )

    result = _run(env)

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "up -d --no-deps api-proxy" in commands
    assert "run -T --rm --no-deps api-proxy nginx -t" not in commands
    assert "up -d --no-deps --force-recreate api-proxy" not in commands
    assert "exec -T api-proxy nginx -t" in commands
    assert "exec -T api-proxy nginx -s reload" in commands
    lines = commands.splitlines()
    proxy_reload = max(
        index
        for index, line in enumerate(lines)
        if "exec -T api-proxy nginx -s reload" in line
    )
    candidate_start = next(
        index
        for index, line in enumerate(lines)
        if "up -d --no-deps --force-recreate app-blue" in line
    )
    old_stop = next(
        index for index, line in enumerate(lines) if line.endswith(" stop -t 5 app")
    )
    assert candidate_start < proxy_reload < old_stop
    assert "proxy_pass http://app-blue:8000;" in upstream.read_text(encoding="utf-8")
    assert (project / ".active-api-slot").read_text(encoding="utf-8").strip() == "blue"


def test_runtime_image_reconciles_env_and_remains_rollback_source_of_truth(tmp_path):
    env, project, site, command_log = _environment(tmp_path)
    upstream = _configure_active_slot(env, project, site, "blue", "host_nginx")
    (project / ".env").write_text(
        f"POSTGRES_USER=postgres\nBACKEND_IMAGE={NEW_IMAGE}\n", encoding="utf-8"
    )
    env.update(
        {
            "API_PUBLIC_READY_URL": "https://public.test/api/ready",
            "FAIL_PUBLIC_READY": "true",
        }
    )

    result = _run(env)

    assert result.returncode != 0
    assert "requested image is already active" not in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "pull app-green" in commands
    assert "stop -t 5 app-green" in commands
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    assert "proxy_pass http://127.0.0.1:18001;" in upstream.read_text(encoding="utf-8")
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=rolled_back" in summary
    assert f"failed_candidate={NEW_IMAGE}" in summary


def test_external_bot_runtime_does_not_affect_api_already_active_shortcut(tmp_path):
    env, project, site, command_log = _environment(tmp_path)
    _configure_active_slot(env, project, site, "blue", "host_nginx")
    env["BACKEND_IMAGE"] = OLD_IMAGE
    env["FAKE_RUNTIME_BOT_IMAGE"] = NEW_IMAGE

    result = _run(env)

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "pull gotenberg" in commands
    assert "up -d --no-deps --wait --wait-timeout 90 gotenberg" in commands
    assert "pull app-blue" not in commands
    assert "pull app-green" not in commands
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=already_active" in summary


def test_matching_api_runtime_can_use_already_active_shortcut(tmp_path):
    env, project, site, command_log = _environment(tmp_path)
    _configure_active_slot(env, project, site, "blue", "host_nginx")
    env["BACKEND_IMAGE"] = OLD_IMAGE

    result = _run(env)

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "pull gotenberg" in commands
    assert "up -d --no-deps --wait --wait-timeout 90 gotenberg" in commands
    assert "pull app-blue" not in commands
    assert "pull app-green" not in commands
    summary = Path(env["API_BLUE_GREEN_SUMMARY_FILE"]).read_text(encoding="utf-8")
    assert "status=already_active" in summary


def test_bootstrap_only_refuses_env_runtime_drift_without_mutation(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    (project / ".env").write_text(
        f"POSTGRES_USER=postgres\nBACKEND_IMAGE={NEW_IMAGE}\n", encoding="utf-8"
    )
    env["API_BLUE_GREEN_BOOTSTRAP_ONLY"] = "true"

    result = _run(env)

    assert result.returncode != 0
    assert f"BACKEND_IMAGE={NEW_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    commands = command_log.read_text(encoding="utf-8")
    assert " up " not in commands
    assert "systemctl reload nginx" not in commands


@pytest.mark.parametrize(
    "runtime_image",
    ["", "ghcr.io/mvnby/air-api/backend:latest", f"{OLD_IMAGE}\n{NEW_IMAGE}"],
)
def test_active_runtime_image_must_be_unique_and_immutable(tmp_path, runtime_image):
    env, project, _, command_log = _environment(tmp_path)
    env["FAKE_RUNTIME_APP_IMAGE"] = runtime_image

    result = _run(env)

    assert result.returncode != 0
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(
        encoding="utf-8"
    )
    commands = command_log.read_text(encoding="utf-8")
    assert " pull " not in commands
    assert " up " not in commands
    assert "systemctl reload nginx" not in commands
