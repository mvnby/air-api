"""Pre-deploy drain failures and nginx refresh after canonical app recovery."""

import os
import subprocess

import pytest

from tests.unit.test_patroni_candidate_release_safety import _proxy_case
from tests.unit.test_patroni_candidate_transactions import (
    PATRONI_RUNNER,
    PREVIOUS_IMAGE,
    REPO_ROOT,
    _executable,
)


@pytest.mark.parametrize("restore_exit", [0, 1])
def test_failed_guard_does_not_arm_runtime_rollback(tmp_path, restore_exit):
    env, project, _, config, upstream = _proxy_case(
        tmp_path, child_exit=0, runtime_state="running"
    )
    shared = tmp_path / "belzakupki"
    shared.mkdir(mode=0o700)
    lifecycle = tmp_path / "guard-lifecycle.sh"
    lifecycle.write_text(
        (REPO_ROOT / "scripts/ha/shared_host_belzakupki_guard_lifecycle.sh")
        .read_text()
        .replace("/opt/belzakupki", str(shared))
    )
    guard = tmp_path / "guard.sh"
    guard_log = tmp_path / "guard.log"
    _executable(
        guard,
        f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == enabled ]]; then printf 'enabled\\n'; exit 0; fi
printf '%s\\n' "$1" >> "$GUARD_LOG"
if [[ "$1" == prepare ]]; then exit 42; fi
exit {restore_exit}
""",
    )
    env.update(
        {
            "API_SHARED_HOST_BELZAKUPKI_GUARD_LIFECYCLE": str(lifecycle),
            "API_SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT": str(guard),
            "GUARD_LOG": str(guard_log),
        }
    )
    canonical = (project / "compose.yml").read_bytes()
    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == (90 if restore_exit else 42), result.stderr
    assert guard_log.read_text().splitlines() == ["prepare", "restore"]
    assert (project / "compose.yml").read_bytes() == canonical
    assert not (project / "compose.yml.candidate").exists()
    assert config.read_text() == "old-config\n"
    assert upstream.read_text() == "active-upstream\n"
    for name in ("child.log", "reconcile.log", "voice-sync.log", "install.log"):
        assert not (tmp_path / name).exists(), name
    assert not (tmp_path / "systemctl.log").read_text()
    commands = (tmp_path / "patroni-commands.log").read_text().splitlines()
    assert not any(
        f" {verb} " in f" {command} "
        for command in commands
        for verb in ("up", "stop", "rm", "exec", "kill")
    ), commands
    assert not list(project.glob(".patroni-*.backup.*"))


def _reconcile(
    tmp_path,
    *,
    mode="container_nginx",
    proxy="running",
    nginx_exit=0,
    transient_health=False,
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "compose.yml").write_text("services: {}\n")
    (project / ".active-api-slot").write_text("green\n")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "commands.log"
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$COMMAND_LOG"
case "$*" in
  *" up -d --no-deps --force-recreate app-green")
    printf 'new-app-ip\n' > "$APP_IP" ;;
  *" ps --status running -q api-proxy")
    [[ "$PROXY_STATE" != running ]] || printf 'existing-proxy\n' ;;
  *" exec -T api-proxy nginx -t") exit "$NGINX_EXIT" ;;
  *" exec -T api-proxy nginx -s reload") cp "$APP_IP" "$PROXY_IP" ;;
  *) exit 91 ;;
esac
""",
    )
    _executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'health\n' >> "$COMMAND_LOG"
if [[ "$PROXY_MODE" == container_nginx && "$PROXY_STATE" == running ]]; then
  cmp -s "$APP_IP" "$PROXY_IP" || exit 22
fi
if [[ "$TRANSIENT_HEALTH" == true && ! -e "$HEALTH_STARTED" ]]; then
  touch "$HEALTH_STARTED"
  exit 22
fi
printf '{"status":"ok"}\n'
""",
    )
    app_ip, proxy_ip = tmp_path / "app-ip", tmp_path / "proxy-ip"
    app_ip.write_text("old-app-ip\n")
    proxy_ip.write_text("old-app-ip\n")
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/reconcile_backend_compose_runtime.sh")],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "API_PROJECT_DIR": str(project),
            "API_COMPOSE_FILE": "compose.yml",
            "API_RECONCILE_BACKEND_IMAGE": PREVIOUS_IMAGE,
            "API_PROXY_MODE": mode,
            "API_HEALTH_ATTEMPTS": "2",
            "COMMAND_LOG": str(log),
            "APP_IP": str(app_ip),
            "PROXY_IP": str(proxy_ip),
            "PROXY_STATE": proxy,
            "PROXY_MODE": mode,
            "NGINX_EXIT": str(nginx_exit),
            "TRANSIENT_HEALTH": str(transient_health).lower(),
            "HEALTH_STARTED": str(tmp_path / "health-started"),
        },
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    return result, log.read_text().splitlines()


def test_canonical_recovery_refreshes_nginx_after_app_ip_changes(tmp_path):
    result, commands = _reconcile(tmp_path)
    assert result.returncode == 0, result.stderr
    assert commands[0].endswith("up -d --no-deps --force-recreate app-green")
    assert commands[2].endswith("exec -T api-proxy nginx -t")
    assert commands[3].endswith("exec -T api-proxy nginx -s reload")
    assert commands[4] == "health"
    assert not any("up " in command and "api-proxy" in command for command in commands)


@pytest.mark.parametrize(
    "mode,proxy",
    [
        ("host_nginx", "running"),
        ("container_nginx", "absent"),
        ("container_nginx", "stopped"),
    ],
)
def test_recovery_does_not_start_or_reload_unmanaged_proxy(tmp_path, mode, proxy):
    result, commands = _reconcile(tmp_path, mode=mode, proxy=proxy)
    assert result.returncode == 0, result.stderr
    assert not any(" exec " in command for command in commands)
    if mode == "host_nginx":
        assert not any("api-proxy" in command for command in commands)


def test_invalid_nginx_config_prevents_reload_and_success(tmp_path):
    result, commands = _reconcile(tmp_path, nginx_exit=42)
    assert result.returncode == 42, result.stderr
    assert not any("nginx -s reload" in command for command in commands)
    assert "health" not in commands


def test_recovery_retries_health_while_nginx_reloads_workers(tmp_path):
    result, commands = _reconcile(tmp_path, transient_health=True)
    assert result.returncode == 0, result.stderr
    assert commands[-2:] == ["health", "health"]
    assert sum("nginx -s reload" in command for command in commands) == 1
