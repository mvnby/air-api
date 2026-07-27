import subprocess
from pathlib import Path

import pytest

from tests.unit.test_patroni_candidate_transactions import (
    PATRONI_RUNNER,
    _patroni_runner_env,
)


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _proxy_case(tmp_path, *, child_exit: int, runtime_state: str, existing=True):
    env, project = _patroni_runner_env(tmp_path, child_exit=child_exit)
    proxy_dir = project / "api-proxy"
    proxy_config = proxy_dir / "nginx.conf"
    proxy_upstream = proxy_dir / "upstream.conf"
    if existing:
        proxy_dir.mkdir()
        proxy_config.write_text("old-config\n", encoding="utf-8")
        proxy_upstream.write_text("active-upstream\n", encoding="utf-8")
    config_source = tmp_path / "new-nginx.conf"
    upstream_source = tmp_path / "new-upstream.conf"
    config_source.write_text("new-config\n", encoding="utf-8")
    upstream_source.write_text("default-upstream\n", encoding="utf-8")
    env.update(
        {
            "API_PROXY_MODE": "container_nginx",
            "PATRONI_PROXY_CONFIG_SOURCE": str(config_source),
            "PATRONI_PROXY_UPSTREAM_SOURCE": str(upstream_source),
            "API_PROXY_CONFIG_FILE": str(proxy_config),
            "API_NGINX_UPSTREAM_FILE": str(proxy_upstream),
            "PROXY_PREVIOUS_RUNTIME_STATE": runtime_state,
        }
    )
    return env, project, proxy_dir, proxy_config, proxy_upstream


@pytest.mark.parametrize("marker_kind", ["file", "symlink"])
def test_patroni_candidate_refuses_pitr_maintenance_before_runtime_mutation(
    tmp_path, marker_kind
):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    marker = tmp_path / "pitr-maintenance"
    if marker_kind == "file":
        marker.write_text("owned\n", encoding="utf-8")
    else:
        marker.symlink_to(tmp_path / "absent-marker-target")
    env["API_PITR_MAINTENANCE_MARKER"] = str(marker)
    proxy_dir = project / "api-proxy"
    proxy_dir.mkdir()
    proxy_config = proxy_dir / "nginx.conf"
    proxy_upstream = proxy_dir / "upstream.conf"
    proxy_config.write_text("old-config\n", encoding="utf-8")
    proxy_upstream.write_text("old-upstream\n", encoding="utf-8")

    result = _run(env)

    assert result.returncode != 0
    assert "PITR release maintenance is active" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert (project / "compose.yml.candidate").read_text(encoding="utf-8") == old
    assert not (tmp_path / "child.log").exists()
    assert not (tmp_path / "reconcile.log").exists()
    assert not (tmp_path / "systemctl.log").read_text(encoding="utf-8")
    assert not (tmp_path / "patroni-commands.log").read_text(encoding="utf-8")
    assert proxy_config.read_text(encoding="utf-8") == "old-config\n"
    assert proxy_upstream.read_text(encoding="utf-8") == "old-upstream\n"


def test_patroni_candidate_rolls_back_proxy_config_and_loaded_runtime(tmp_path):
    env, project, _, proxy_config, proxy_upstream = _proxy_case(
        tmp_path, child_exit=42, runtime_state="running"
    )
    proxy_config.chmod(0o640)
    env["PROXY_RUNTIME_CONFIG"] = str(tmp_path / "loaded-nginx.conf")

    result = _run(env)

    assert result.returncode == 42, result.stderr
    assert proxy_config.read_text(encoding="utf-8") == "old-config\n"
    assert proxy_config.stat().st_mode & 0o777 == 0o640
    assert proxy_upstream.read_text(encoding="utf-8") == "active-upstream\n"
    assert (tmp_path / "loaded-nginx.conf").read_text(encoding="utf-8") == (
        "old-config\n"
    )
    assert not list(project.glob(".patroni-proxy-config.backup.*"))
    commands = (tmp_path / "patroni-commands.log").read_text(encoding="utf-8")
    assert "up -d --no-deps --force-recreate --wait --wait-timeout 60 api-proxy" in commands
    assert "exec -T api-proxy nginx -t" in commands


def test_patroni_candidate_commits_proxy_config_and_preserves_active_upstream(tmp_path):
    env, project, _, proxy_config, proxy_upstream = _proxy_case(
        tmp_path, child_exit=0, runtime_state="running"
    )

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert proxy_config.read_text(encoding="utf-8") == "new-config\n"
    assert proxy_upstream.read_text(encoding="utf-8") == "active-upstream\n"
    assert not list(project.glob(".patroni-proxy-config.backup.*"))


def test_patroni_candidate_rollback_preserves_absent_proxy_runtime_and_directory(
    tmp_path,
):
    env, _, proxy_dir, _, _ = _proxy_case(
        tmp_path, child_exit=42, runtime_state="absent", existing=False
    )
    env["PROXY_RUNTIME_CONFIG"] = str(tmp_path / "loaded-nginx.conf")

    result = _run(env)

    assert result.returncode == 42, result.stderr
    assert not proxy_dir.exists()
    assert not (tmp_path / "loaded-nginx.conf").exists()
    commands = (tmp_path / "patroni-commands.log").read_text(encoding="utf-8")
    assert "rm -s -f api-proxy" in commands
    assert "up -d --no-deps --force-recreate --wait" not in commands


def test_patroni_candidate_rollback_keeps_previously_stopped_proxy_stopped(tmp_path):
    env, _, _, proxy_config, _ = _proxy_case(
        tmp_path, child_exit=42, runtime_state="stopped"
    )

    result = _run(env)

    assert result.returncode == 42, result.stderr
    assert proxy_config.read_text(encoding="utf-8") == "old-config\n"
    commands = (tmp_path / "patroni-commands.log").read_text(encoding="utf-8")
    assert "stop api-proxy" in commands
    assert "ps --status running -q api-proxy" in commands
    assert "up -d --no-deps --force-recreate --wait" not in commands


def test_patroni_candidate_rejects_writable_proxy_target_metadata(tmp_path):
    env, project, _, proxy_config, _ = _proxy_case(
        tmp_path, child_exit=0, runtime_state="running"
    )
    old = (project / "compose.yml").read_text(encoding="utf-8")
    proxy_config.chmod(0o666)

    result = _run(env)

    assert result.returncode != 0
    assert "proxy target metadata is unsafe" in result.stderr
    assert proxy_config.read_text(encoding="utf-8") == "old-config\n"
    assert proxy_config.stat().st_mode & 0o777 == 0o666
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()


def test_patroni_candidate_promotes_only_after_success(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    new = (project / "compose.yml.candidate").read_text(encoding="utf-8")

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == new
    assert not (project / "compose.yml.candidate").exists()
    assert not (tmp_path / "reconcile.log").exists()
    assert Path(env["PATRONI_ROLE_IDENTITY_TARGET"]).read_text() == (
        "# new identity helper\n"
    )


def test_patroni_candidate_stages_bundle_compose_only_after_maintenance_guard(
    tmp_path,
):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    candidate = project / "compose.yml.candidate"
    source = tmp_path / "verified-compose-source.yml"
    candidate.replace(source)
    env["PATRONI_CANDIDATE_COMPOSE_SOURCE"] = str(source)
    marker = tmp_path / "pitr-maintenance"
    marker.write_text("owned\n", encoding="utf-8")
    env["API_PITR_MAINTENANCE_MARKER"] = str(marker)

    result = _run(env)

    assert result.returncode != 0
    assert "PITR release maintenance is active" in result.stderr
    assert source.is_file()
    assert not candidate.exists()


def test_patroni_candidate_atomically_stages_verified_bundle_source(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    candidate = project / "compose.yml.candidate"
    source = tmp_path / "verified-compose-source.yml"
    expected = candidate.read_text(encoding="utf-8")
    candidate.replace(source)
    env["PATRONI_CANDIDATE_COMPOSE_SOURCE"] = str(source)

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == expected
    assert source.is_file()
    assert not candidate.exists()


@pytest.mark.parametrize("source_kind", ["symlink", "preexisting-target"])
def test_patroni_candidate_rejects_unowned_bundle_staging_paths(
    tmp_path, source_kind
):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    candidate = project / "compose.yml.candidate"
    original_candidate = candidate.read_text(encoding="utf-8")
    source = tmp_path / "verified-compose-source.yml"
    if source_kind == "symlink":
        source.symlink_to(candidate)
    else:
        source.write_text("services: {}\n", encoding="utf-8")
    env["PATRONI_CANDIDATE_COMPOSE_SOURCE"] = str(source)

    result = _run(env)

    assert result.returncode != 0
    expected = (
        "source is missing or unsafe"
        if source_kind == "symlink"
        else "target already exists"
    )
    assert expected in result.stderr
    assert candidate.read_text(encoding="utf-8") == original_candidate
    assert not (tmp_path / "child.log").exists()
