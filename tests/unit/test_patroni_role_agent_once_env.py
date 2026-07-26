import hashlib
import os
from pathlib import Path

import pytest

from scripts.ha import patroni_role_agent_once_env as once_env


def _write_environment(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()),
        encoding="utf-8",
    )
    path.chmod(0o600)


def test_expected_environment_is_node_specific():
    api = once_env.expected_role_environment("/opt/air-api")
    reserve = once_env.expected_role_environment("/opt/mvn-reserve")

    assert api["HA_PROJECT_DIR"] == "/opt/air-api"
    assert api["HA_PATRONI_NAME"] == "mvn-api"
    assert reserve["HA_PROJECT_DIR"] == "/opt/mvn-reserve"
    assert reserve["HA_PATRONI_NAME"] == "zakup"
    assert api["HA_COMPOSE_FILE"] == reserve["HA_COMPOSE_FILE"]
    assert api["HA_COMPOSE_FILE"] == "docker-compose.patroni.yml"


def test_environment_attestation_accepts_exact_reviewed_contract(tmp_path):
    path = tmp_path / "role-agent.env"
    expected = once_env.expected_role_environment("/opt/mvn-reserve")
    _write_environment(path, expected)

    actual = once_env.attest_role_environment(
        "/opt/mvn-reserve",
        path=path,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert actual == expected


@pytest.mark.parametrize(
    "mutation",
    (
        lambda values: values.__setitem__("HA_PATRONI_NAME", "mvn-api"),
        lambda values: values.__setitem__("EXTRA_SETTING", "unsafe"),
        lambda values: values.pop("HA_PROJECT_DIR"),
    ),
)
def test_environment_attestation_rejects_contract_drift(tmp_path, mutation):
    path = tmp_path / "role-agent.env"
    values = once_env.expected_role_environment("/opt/mvn-reserve")
    mutation(values)
    _write_environment(path, values)

    with pytest.raises(ValueError, match="differs from the reviewed"):
        once_env.attest_role_environment(
            "/opt/mvn-reserve",
            path=path,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_environment_attestation_rejects_symlink(tmp_path):
    target = tmp_path / "target.env"
    link = tmp_path / "role-agent.env"
    _write_environment(
        target,
        once_env.expected_role_environment("/opt/mvn-reserve"),
    )
    link.symlink_to(target)

    with pytest.raises(OSError):
        once_env.attest_role_environment(
            "/opt/mvn-reserve",
            path=link,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_environment_attestation_rejects_unsafe_mode(tmp_path):
    path = tmp_path / "role-agent.env"
    _write_environment(
        path,
        once_env.expected_role_environment("/opt/mvn-reserve"),
    )
    path.chmod(0o644)

    with pytest.raises(ValueError, match="unsafe role-agent asset"):
        once_env.attest_role_environment(
            "/opt/mvn-reserve",
            path=path,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_run_once_executes_agent_with_attested_clean_environment(
    tmp_path, monkeypatch
):
    environment_path = tmp_path / "role-agent.env"
    agent_path = tmp_path / "mvn-patroni-role-agent"
    python_path = Path("/usr/bin/python3")
    expected = once_env.expected_role_environment("/opt/mvn-reserve")
    _write_environment(environment_path, expected)
    agent_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    agent_path.chmod(0o755)
    agent_digest = hashlib.sha256(agent_path.read_bytes()).hexdigest()
    captured: dict[str, object] = {}

    def fake_execve(path, arguments, environment):
        captured.update(
            path=path,
            arguments=arguments,
            environment=environment,
        )
        raise RuntimeError("exec captured")

    monkeypatch.setattr(os, "execve", fake_execve)

    with pytest.raises(RuntimeError, match="exec captured"):
        once_env.run_once(
            "/opt/mvn-reserve",
            agent_digest,
            environment_path=environment_path,
            agent_path=agent_path,
            python_path=python_path,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )

    assert captured["path"] == python_path
    assert captured["arguments"] == [
        str(python_path),
        str(agent_path),
        "--once",
    ]
    assert captured["environment"] == {
        **once_env.BASE_EXEC_ENVIRONMENT,
        **expected,
    }


def test_run_once_rejects_unreviewed_agent_digest(tmp_path):
    environment_path = tmp_path / "role-agent.env"
    agent_path = tmp_path / "mvn-patroni-role-agent"
    expected = once_env.expected_role_environment("/opt/mvn-reserve")
    _write_environment(environment_path, expected)
    agent_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    agent_path.chmod(0o755)

    with pytest.raises(ValueError, match="digest differs"):
        once_env.run_once(
            "/opt/mvn-reserve",
            "0" * 64,
            environment_path=environment_path,
            agent_path=agent_path,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
