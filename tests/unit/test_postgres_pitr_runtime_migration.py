import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.ha import verify_postgres_pitr_runtime as runtime


IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "a" * 64
IMAGE_ID = "sha256:" + "b" * 64
PRODUCTION_DESTINATION_FINGERPRINT = runtime.EXPECTED_DESTINATION_FINGERPRINT
PITR_VALUES = {
    "POSTGRES_PITR_CLUSTER": "mvn-api",
    "POSTGRES_PITR_S3_BUCKET": "mvn-postgres-pitr",
    "POSTGRES_PITR_S3_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
    "POSTGRES_PITR_S3_REGION": "auto",
    "POSTGRES_PITR_S3_ACCESS_KEY_ID": "access-key",
    "POSTGRES_PITR_S3_SECRET_ACCESS_KEY": "secret-key",
    "POSTGRES_PITR_S3_KEY_PREFIX": "postgres/pitr",
    "POSTGRES_PITR_ARCHIVE_MODE": "on",
    "POSTGRES_PITR_ARCHIVE_TIMEOUT": "300s",
}
PITR_DESTINATION_FINGERPRINT = hashlib.sha256(
    (
        "\n".join(
            PITR_VALUES[key]
            for key in (
                "POSTGRES_PITR_S3_BUCKET",
                "POSTGRES_PITR_S3_ENDPOINT_URL",
                "POSTGRES_PITR_S3_REGION",
                "POSTGRES_PITR_S3_KEY_PREFIX",
            )
        )
        + "\n"
    ).encode("utf-8")
).hexdigest()


@pytest.fixture(autouse=True)
def _use_test_destination_fingerprint(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "EXPECTED_DESTINATION_FINGERPRINT",
        PITR_DESTINATION_FINGERPRINT,
    )


def _runtime_project(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    project = (tmp_path / "project").resolve()
    project.mkdir()
    compose = project / "docker-compose.patroni.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    compose.chmod(0o644)
    env_file = project / ".env"
    env_file.write_text(
        "\n".join(
            (
                f"BACKEND_IMAGE={IMAGE}",
                *(
                    f"{key}={PITR_VALUES[key]}"
                    for key in sorted(runtime.PROJECT_PITR_KEYS)
                ),
                "",
            )
        ),
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    secrets_file = project / "pitr.secrets.env"
    secrets_file.write_text(
        "\n".join(
            f"{key}={PITR_VALUES[key]}" for key in sorted(runtime.SECRET_PITR_KEYS)
        )
        + "\n",
        encoding="utf-8",
    )
    secrets_file.chmod(0o600)
    digest = hashlib.sha256(compose.read_bytes()).hexdigest()
    return project, {str(compose): digest}


def _verify_kwargs(project: Path, digests: dict[str, str]) -> dict[str, object]:
    return {
        "project_dir": project,
        "compose_file": "docker-compose.patroni.yml",
        "expected_compose_digests": digests,
        "expected_pitr_clusters": {
            str(project / "docker-compose.patroni.yml"): "mvn-api"
        },
        "secrets_file": project / "pitr.secrets.env",
        "expected_uid": os.geteuid(),
    }


def _fake_docker(
    monkeypatch,
    *,
    image: str = IMAGE,
    running_id: str = IMAGE_ID,
    pitr_override: tuple[str, str] | None = None,
    compose_secrets: dict[str, str] | None = None,
    compose_mounts: list[object] | None = None,
    containers: dict[str, dict[str, object]] | None = None,
):
    calls = []
    if containers is None:
        containers = {
            "container-blue": {
                "service": "app-blue",
                "running": True,
                "environment": {
                    key: PITR_VALUES[key] for key in runtime.PROJECT_PITR_KEYS
                },
                "mounts": [],
                "image": image,
                "image_id": running_id,
            }
        }

    def fake_run(args, *, cwd=None, timeout=30):
        calls.append((list(args), cwd, timeout))
        rendered = " ".join(args)
        if args[:3] == ["docker", "context", "inspect"]:
            return "unix:///var/run/docker.sock"
        if " config --format json" in rendered:
            environment = {
                key: PITR_VALUES[key] for key in runtime.PROJECT_PITR_KEYS
            }
            environment.update(compose_secrets or {})
            if pitr_override is not None:
                environment[pitr_override[0]] = pitr_override[1]
            return json.dumps(
                {
                    "services": {
                        name: {
                            "image": image,
                            "environment": environment,
                            "volumes": compose_mounts or [],
                        }
                        for name in runtime.APP_SERVICES
                    }
                    | {
                        "bot": {
                            "image": image,
                            "environment": environment,
                            "volumes": compose_mounts or [],
                        }
                    },
                }
            )
        if args[:3] == ["docker", "image", "inspect"]:
            return IMAGE_ID
        if " ps --all -q " in rendered:
            return "\n".join(containers)
        if args[:4] == ["docker", "inspect", "--format", "{{json .}}"]:
            container = containers[args[-1]]
            environment = container.get("environment", {})
            return json.dumps(
                {
                    "Image": container.get("image_id", IMAGE_ID),
                    "Config": {
                        "Image": container.get("image", image),
                        "Labels": {
                            "com.docker.compose.service": container["service"]
                        },
                        "Env": [f"{key}={value}" for key, value in environment.items()],
                    },
                    "State": {"Running": container.get("running", False)},
                    "Mounts": container.get("mounts", []),
                }
            )
        raise AssertionError(args)

    monkeypatch.setattr(runtime, "_run_checked", fake_run)
    return calls




def _enable_legacy_project_state(project: Path) -> None:
    (project / "pitr.secrets.env").unlink()
    env_file = project / ".env"
    env_file.write_text(
        env_file.read_text(encoding="utf-8")
        + "".join(
            f"{key}={PITR_VALUES[key]}\n" for key in sorted(runtime.SECRET_PITR_KEYS)
        ),
        encoding="utf-8",
    )


def _container(
    service: str,
    *,
    running: bool,
    secrets: dict[str, str] | None = None,
    mounts: list[object] | None = None,
    image: str = IMAGE,
    image_id: str = IMAGE_ID,
) -> dict[str, object]:
    return {
        "service": service,
        "running": running,
        "environment": {
            **{key: PITR_VALUES[key] for key in runtime.PROJECT_PITR_KEYS},
            **(secrets or {}),
        },
        "mounts": mounts or [],
        "image": image,
        "image_id": image_id,
    }


def _legacy_wal_mount(project: Path) -> dict[str, object]:
    return {
        "Source": str(project / runtime.FORBIDDEN_WAL_ARCHIVE_MARKER),
        "Destination": runtime.FORBIDDEN_WAL_ARCHIVE_TARGET,
        "Type": "bind",
        "RW": True,
    }


def test_legacy_migration_requires_exact_reviewed_secrets_across_all_state(
    tmp_path,
    monkeypatch,
):
    project, digests = _runtime_project(tmp_path)
    _enable_legacy_project_state(project)
    containers = {
        "blue": _container("app-blue", running=True, secrets=dict(PITR_VALUES)),
        "bot": _container("bot", running=False, secrets=dict(PITR_VALUES)),
        "clean-green": _container("app-green", running=False),
    }
    calls = _fake_docker(
        monkeypatch,
        compose_secrets={key: PITR_VALUES[key] for key in runtime.SECRET_PITR_KEYS},
        containers=containers,
    )

    assert runtime.verify_runtime_contract(
        **_verify_kwargs(project, digests),
        pitr_env_policy="legacy-migration",
    ) == IMAGE
    assert any(" ps --all -q " in " ".join(call[0]) for call in calls)


@pytest.mark.parametrize(
    "policy",
    ["legacy-migration", "migration-files-clean"],
)
def test_migration_policies_allow_exact_legacy_runtime_wal_bind(
    tmp_path,
    monkeypatch,
    policy,
):
    project, digests = _runtime_project(tmp_path)
    compose_secrets = None
    if policy == "legacy-migration":
        _enable_legacy_project_state(project)
        compose_secrets = {
            key: PITR_VALUES[key] for key in runtime.SECRET_PITR_KEYS
        }
    container_secrets = {
        key: PITR_VALUES[key] for key in runtime.SECRET_PITR_KEYS
    }
    _fake_docker(
        monkeypatch,
        compose_secrets=compose_secrets,
        containers={
            "blue": _container(
                "app-blue",
                running=True,
                secrets=container_secrets,
                mounts=[_legacy_wal_mount(project)],
            )
        },
    )

    assert runtime.verify_runtime_contract(
        **_verify_kwargs(project, digests),
        pitr_env_policy=policy,
    ) == IMAGE


@pytest.mark.parametrize(
    "policy",
    ["legacy-migration", "migration-files-clean"],
)
def test_canonical_compose_always_rejects_legacy_wal_mount(
    tmp_path,
    monkeypatch,
    policy,
):
    project, digests = _runtime_project(tmp_path)
    compose_secrets = None
    if policy == "legacy-migration":
        _enable_legacy_project_state(project)
        compose_secrets = {
            key: PITR_VALUES[key] for key in runtime.SECRET_PITR_KEYS
        }
    _fake_docker(
        monkeypatch,
        compose_secrets=compose_secrets,
        compose_mounts=[
            {
                "source": str(project / runtime.FORBIDDEN_WAL_ARCHIVE_MARKER),
                "target": runtime.FORBIDDEN_WAL_ARCHIVE_TARGET,
                "type": "bind",
            }
        ],
    )

    with pytest.raises(RuntimeError, match="WAL archive"):
        runtime.verify_runtime_contract(
            **_verify_kwargs(project, digests),
            pitr_env_policy=policy,
        )


@pytest.mark.parametrize(
    "policy",
    ["legacy-migration", "migration-files-clean"],
)
@pytest.mark.parametrize(
    "invalid_case",
    ["wrong-source", "wrong-type", "read-only", "additional-archive-mount"],
)
def test_migration_policies_reject_unreviewed_runtime_wal_mounts(
    tmp_path,
    monkeypatch,
    policy,
    invalid_case,
):
    project, digests = _runtime_project(tmp_path)
    compose_secrets = None
    if policy == "legacy-migration":
        _enable_legacy_project_state(project)
        compose_secrets = {
            key: PITR_VALUES[key] for key in runtime.SECRET_PITR_KEYS
        }
    mount = _legacy_wal_mount(project)
    mounts = [mount]
    if invalid_case == "wrong-source":
        mount["Source"] = "/srv/postgres-wal-archive"
    elif invalid_case == "wrong-type":
        mount["Type"] = "volume"
    elif invalid_case == "read-only":
        mount["RW"] = False
    else:
        mounts.append(
            {
                "Source": "/srv/postgres-wal-archive-old",
                "Destination": "/postgres-wal-archive-old",
                "Type": "bind",
                "RW": True,
            }
        )
    container_secrets = {
        key: PITR_VALUES[key] for key in runtime.SECRET_PITR_KEYS
    }
    _fake_docker(
        monkeypatch,
        compose_secrets=compose_secrets,
        containers={
            "blue": _container(
                "app-blue",
                running=True,
                secrets=container_secrets,
                mounts=mounts,
            )
        },
    )

    with pytest.raises(RuntimeError, match="WAL archive"):
        runtime.verify_runtime_contract(
            **_verify_kwargs(project, digests),
            pitr_env_policy=policy,
        )


@pytest.mark.parametrize("policy", ["configured", "operational"])
def test_steady_state_policies_reject_exact_legacy_runtime_wal_bind(
    tmp_path,
    monkeypatch,
    policy,
):
    project, digests = _runtime_project(tmp_path)
    _fake_docker(
        monkeypatch,
        containers={
            "blue": _container(
                "app-blue",
                running=True,
                mounts=[_legacy_wal_mount(project)],
            )
        },
    )

    with pytest.raises(RuntimeError, match="WAL archive"):
        runtime.verify_runtime_contract(
            **_verify_kwargs(project, digests),
            pitr_env_policy=policy,
        )


@pytest.mark.parametrize(
    "bad_secrets",
    [
        {"POSTGRES_PITR_CLUSTER": "mvn-api"},
        {**PITR_VALUES, "POSTGRES_PITR_S3_SECRET_ACCESS_KEY": "wrong"},
        {**PITR_VALUES, "POSTGRES_PITR_S3_SESSION_TOKEN": "unexpected"},
    ],
)
def test_legacy_migration_rejects_partial_mismatched_or_extra_container_secrets(
    tmp_path,
    monkeypatch,
    bad_secrets,
):
    project, digests = _runtime_project(tmp_path)
    _enable_legacy_project_state(project)
    _fake_docker(
        monkeypatch,
        compose_secrets={key: PITR_VALUES[key] for key in runtime.SECRET_PITR_KEYS},
        containers={"blue": _container("app-blue", running=True, secrets=bad_secrets)},
    )

    with pytest.raises(RuntimeError, match="PITR|legacy secrets|committed"):
        runtime.verify_runtime_contract(
            **_verify_kwargs(project, digests),
            pitr_env_policy="legacy-migration",
        )


def test_files_clean_allows_only_exact_pre_scrub_container_secrets(
    tmp_path,
    monkeypatch,
):
    project, digests = _runtime_project(tmp_path)
    dirty = {key: PITR_VALUES[key] for key in runtime.SECRET_PITR_KEYS}
    _fake_docker(
        monkeypatch,
        containers={
            "blue": _container("app-blue", running=True, secrets=dirty),
            "old-bot": _container("bot", running=False, secrets=dirty),
        },
    )

    assert runtime.verify_runtime_contract(
        **_verify_kwargs(project, digests),
        pitr_env_policy="migration-files-clean",
    ) == IMAGE

    dirty["POSTGRES_PITR_S3_SECRET_ACCESS_KEY"] = "wrong"
    _fake_docker(
        monkeypatch,
        containers={"blue": _container("app-blue", running=True, secrets=dirty)},
    )
    with pytest.raises(RuntimeError, match="committed PITR secrets"):
        runtime.verify_runtime_contract(
            **_verify_kwargs(project, digests),
            pitr_env_policy="migration-files-clean",
        )


def test_normal_policy_rejects_secrets_in_stopped_container(tmp_path, monkeypatch):
    project, digests = _runtime_project(tmp_path)
    _fake_docker(
        monkeypatch,
        containers={
            "blue": _container("app-blue", running=True),
            "stopped-bot": _container(
                "bot",
                running=False,
                secrets={key: PITR_VALUES[key] for key in runtime.SECRET_PITR_KEYS},
            ),
        },
    )

    with pytest.raises(RuntimeError, match="exposes private PITR"):
        runtime.verify_runtime_contract(**_verify_kwargs(project, digests))

@pytest.mark.parametrize("at_compose_level", [True, False])
def test_runtime_contract_rejects_wal_archive_mounts_in_compose_or_stopped_slot(
    tmp_path,
    monkeypatch,
    at_compose_level,
):
    project, digests = _runtime_project(tmp_path)
    forbidden = [{"source": "/srv/postgres-wal-archive", "target": "/archive"}]
    containers = {"blue": _container("app-blue", running=True)}
    if not at_compose_level:
        containers["green"] = _container(
            "app-green", running=False, mounts=forbidden
        )
    _fake_docker(
        monkeypatch,
        compose_mounts=forbidden if at_compose_level else None,
        containers=containers,
    )

    with pytest.raises(RuntimeError, match="WAL archive"):
        runtime.verify_runtime_contract(**_verify_kwargs(project, digests))
