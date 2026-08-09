import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.ha import pitr_remote_execution
from scripts.ha import run_postgres_pitr_scheduled as scheduled
from scripts.ha import verify_postgres_pitr_runtime as runtime
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES


REPO_ROOT = Path(__file__).resolve().parents[2]
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


def test_expected_compose_digests_match_reviewed_sources():
    expected_sources = {
        "/opt/air-api/docker-compose.patroni.yml": (
            REPO_ROOT / "deploy/ha/mvn-api/docker-compose.patroni.yml"
        ),
        "/opt/mvn-reserve/docker-compose.patroni.yml": (
            REPO_ROOT / "deploy/ha/zakup/docker-compose.patroni.yml"
        ),
    }
    assert set(runtime.EXPECTED_COMPOSE_DIGESTS) == set(expected_sources)
    for remote_path, source in expected_sources.items():
        assert runtime.EXPECTED_COMPOSE_DIGESTS[remote_path] == hashlib.sha256(
            source.read_bytes()
        ).hexdigest()
    assert set(runtime.EXPECTED_PITR_CLUSTERS.values()) == {"mvn-api"}
    assert PRODUCTION_DESTINATION_FINGERPRINT == (
        "3c6e78da6f79b317f8b62d3f979bb69dba1f2821e473a670be30ec08310f458b"
    )


def test_runtime_contract_accepts_exact_compose_image_and_running_slot(
    tmp_path, monkeypatch
):
    project, digests = _runtime_project(tmp_path)
    calls = _fake_docker(monkeypatch)

    result = runtime.verify_runtime_contract(**_verify_kwargs(project, digests))

    assert result == IMAGE
    assert any("--profile bluegreen" in " ".join(call[0]) for call in calls)


def test_runtime_only_policy_allows_preconfiguration_state(tmp_path, monkeypatch):
    project, digests = _runtime_project(tmp_path)
    (project / ".env").write_text(f"BACKEND_IMAGE={IMAGE}\n", encoding="utf-8")
    (project / "pitr.secrets.env").unlink()
    _fake_docker(monkeypatch)

    assert runtime.verify_runtime_contract(
        **_verify_kwargs(project, digests),
        pitr_env_policy="runtime-only",
    ) == IMAGE


def test_configured_policy_allows_off_but_operational_rejects_it(
    tmp_path,
    monkeypatch,
):
    project, digests = _runtime_project(tmp_path)
    env_file = project / ".env"
    env_file.write_text(
        env_file.read_text(encoding="utf-8").replace(
            "POSTGRES_PITR_ARCHIVE_MODE=on",
            "POSTGRES_PITR_ARCHIVE_MODE=off",
        ),
        encoding="utf-8",
    )
    _fake_docker(
        monkeypatch,
        pitr_override=("POSTGRES_PITR_ARCHIVE_MODE", "off"),
    )
    common = _verify_kwargs(project, digests)

    assert runtime.verify_runtime_contract(
        **common,
        pitr_env_policy="configured",
    ) == IMAGE
    with pytest.raises(RuntimeError, match="archive mode"):
        runtime.verify_runtime_contract(
            **common,
            pitr_env_policy="operational",
        )


@pytest.mark.parametrize(
    ("configured_image", "running_id", "message"),
    [
        ("ghcr.io/mvnby/air-api/backend:latest", IMAGE_ID, "immutable"),
        (IMAGE, "sha256:" + "c" * 64, "does not match"),
    ],
)
def test_runtime_contract_rejects_mutable_or_mismatched_image(
    tmp_path,
    monkeypatch,
    configured_image,
    running_id,
    message,
):
    project, digests = _runtime_project(tmp_path)
    _fake_docker(
        monkeypatch,
        image=configured_image,
        running_id=running_id,
    )

    with pytest.raises(RuntimeError, match=message):
        runtime.verify_runtime_contract(
            **_verify_kwargs(project, digests),
        )


def test_runtime_contract_rejects_compose_digest_drift(tmp_path, monkeypatch):
    project, _digests = _runtime_project(tmp_path)
    _fake_docker(monkeypatch)
    contract = _verify_kwargs(project, _digests)
    contract["expected_compose_digests"] = {
        str(project / "docker-compose.patroni.yml"): "0" * 64
    }

    with pytest.raises(RuntimeError, match="digest mismatch"):
        runtime.verify_runtime_contract(**contract)


def test_runtime_contract_rejects_resolved_alternate_cluster(
    tmp_path,
    monkeypatch,
):
    project, digests = _runtime_project(tmp_path)
    secrets_file = project / "pitr.secrets.env"
    secrets_file.write_text(
        secrets_file.read_text(encoding="utf-8").replace(
            "POSTGRES_PITR_CLUSTER=mvn-api",
            "POSTGRES_PITR_CLUSTER=zakup",
        ),
        encoding="utf-8",
    )
    _fake_docker(monkeypatch)

    with pytest.raises(RuntimeError, match="logical namespace"):
        runtime.verify_runtime_contract(**_verify_kwargs(project, digests))


def test_runtime_contract_rejects_role_env_pitr_destination_override(
    tmp_path,
    monkeypatch,
):
    project, digests = _runtime_project(tmp_path)
    _fake_docker(
        monkeypatch,
        pitr_override=("POSTGRES_PITR_S3_BUCKET", "different-private-bucket"),
    )

    with pytest.raises(RuntimeError, match="exposes private"):
        runtime.verify_runtime_contract(**_verify_kwargs(project, digests))


def test_runtime_contract_rejects_unreviewed_canonical_destination(
    tmp_path,
    monkeypatch,
):
    project, digests = _runtime_project(tmp_path)
    secrets_file = project / "pitr.secrets.env"
    secrets_file.write_text(
        secrets_file.read_text(encoding="utf-8").replace(
            "POSTGRES_PITR_S3_BUCKET=mvn-postgres-pitr",
            "POSTGRES_PITR_S3_BUCKET=different-private-bucket",
        ),
        encoding="utf-8",
    )
    _fake_docker(monkeypatch)

    with pytest.raises(RuntimeError, match="reviewed archive"):
        runtime.verify_runtime_contract(**_verify_kwargs(project, digests))


@pytest.mark.parametrize(
    "replacement",
    [
        "POSTGRES_PITR_CLUSTER=zakup",
        "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=",
        "POSTGRES_PITR_CLUSTER=mvn-api\nPOSTGRES_PITR_CLUSTER=mvn-api",
        "MVN_RESERVE_ENV_FILE=/tmp/unreviewed.env",
    ],
)
def test_runtime_contract_rejects_wrong_incomplete_or_duplicate_pitr_env(
    tmp_path,
    monkeypatch,
    replacement,
):
    project, digests = _runtime_project(tmp_path)
    if replacement.startswith("MVN_RESERVE_ENV_FILE="):
        env_file = project / ".env"
        env_file.write_text(
            env_file.read_text(encoding="utf-8") + replacement + "\n",
            encoding="utf-8",
        )
    else:
        env_file = project / "pitr.secrets.env"
        lines = [
            line
            for line in env_file.read_text(encoding="utf-8").splitlines()
            if not (
                line.startswith("POSTGRES_PITR_CLUSTER=")
                or line.startswith("POSTGRES_PITR_S3_SECRET_ACCESS_KEY=")
            )
        ]
        lines.append(replacement)
        if "POSTGRES_PITR_CLUSTER=" not in replacement:
            lines.append("POSTGRES_PITR_CLUSTER=mvn-api")
        if "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=" not in replacement:
            lines.append("POSTGRES_PITR_S3_SECRET_ACCESS_KEY=secret-key")
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _fake_docker(monkeypatch)

    with pytest.raises(RuntimeError, match="PITR|cluster|duplicate|canonical"):
        runtime.verify_runtime_contract(**_verify_kwargs(project, digests))


def test_docker_commands_always_use_literal_clean_environment(monkeypatch):
    captured = {}

    def fake_subprocess(args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(runtime.subprocess, "run", fake_subprocess)
    assert runtime._run_checked(["docker", "version"]) == "ok"
    assert captured["env"] == runtime.DOCKER_ENV
    assert "DOCKER_HOST" not in captured["env"]
    assert "BACKEND_IMAGE" not in captured["env"]
    assert "PYTHONPATH" not in captured["env"]


def test_remote_manifest_attests_node_compose_and_runtime_checker():
    for node in PATRONI_NODES:
        manifest = json.loads(
            pitr_remote_execution.render_host_asset_manifest(node)
        )
        compose_path = f"{node.project_dir}/{node.compose_file}"
        assert manifest[compose_path] == hashlib.sha256(
            node.compose_source.read_bytes()
        ).hexdigest()
        assert "/usr/local/sbin/mvn-postgres-pitr-runtime-check" in manifest
        assert "/usr/local/sbin/mvn-postgres-pitr-scheduled-runner" in manifest


def test_remote_executors_lock_before_node_specific_attestation():
    for source in (
        pitr_remote_execution.REMOTE_SECRET_EXECUTOR,
        pitr_remote_execution.REMOTE_MAINTENANCE_EXECUTOR,
    ):
        assert source.index("fcntl.flock") < source.index("attest_assets(asset_manifest")
        assert "attest_assets(asset_manifest, project_dir, compose_file)" in source
        assert '"DOCKER_CONTEXT": "default"' in source


def test_timer_units_and_wrappers_use_clean_pinned_execution():
    for name in ("mvn-postgres-wal-upload", "mvn-postgres-basebackup"):
        unit = (
            REPO_ROOT / f"deploy/ha/systemd/{name}.service"
        ).read_text(encoding="utf-8")
        assert "ExecStart=/usr/bin/env -i " in unit
        assert "/usr/local/sbin/mvn-postgres-pitr-scheduled-runner" in unit
        if name == "mvn-postgres-wal-upload":
            assert "SuccessExitStatus=75" in unit
            assert "Restart=on-failure" not in unit
        else:
            assert "SuccessExitStatus=75" not in unit
            assert "Restart=on-failure" in unit
            assert "RestartSec=5min" in unit
        assert "TimeoutStartSec=" in unit
        assert "TimeoutStopSec=" in unit
        assert "KillMode=control-group" in unit
        assert "EnvironmentFile=-" not in unit

    wrappers = (
        "upload_postgres_pitr_wal.sh",
        "create_postgres_pitr_basebackup.sh",
        "check_postgres_pitr_status.sh",
        "restore_postgres_pitr_drill.sh",
    )
    for name in wrappers:
        source = (REPO_ROOT / "scripts/ha" / name).read_text(encoding="utf-8")
        assert "mvn-postgres-pitr-runtime-check" in source
        assert "mvn-postgres-pitr-tool-runner" in source
    for name in ("create_postgres_pitr_basebackup.sh", "restore_postgres_pitr_drill.sh"):
        source = (REPO_ROOT / "scripts/ha" / name).read_text(encoding="utf-8")
        assert "--pull never" in source
    restore_source = (
        REPO_ROOT / "scripts/ha/restore_postgres_pitr_drill.sh"
    ).read_text(encoding="utf-8")
    assert ":ro" in restore_source


def test_pitr_preflight_prefetches_the_pinned_basebackup_image():
    source = (REPO_ROOT / "scripts/ha/bootstrap_postgres_pitr.sh").read_text(
        encoding="utf-8"
    )

    assert 'PITR_BASEBACKUP_IMAGE="postgres:15.18-alpine@sha256:' in source
    assert 'docker pull --platform linux/amd64 "${PITR_BASEBACKUP_IMAGE}"' in source
    assert 'docker image inspect "${PITR_BASEBACKUP_IMAGE}"' in source
    assert source.index("ensure_basebackup_image") < source.index("preflight()")
    preflight = source[source.index("preflight()") : source.index("provision_node()")]
    assert '  ensure_basebackup_image\n' in preflight


def test_pitr_status_distinguishes_historical_archiver_failures_from_live_ones():
    source = (REPO_ROOT / "scripts/ha/check_postgres_pitr_status.sh").read_text(
        encoding="utf-8"
    )

    assert "WHEN last_failed_time > last_archived_time THEN 'true'" in source
    assert '[[ "${unresolved_archive_failure}" == "true" ]]' in source
    assert "is historical; a newer WAL archive succeeded" in source


def test_explicit_upload_helper_precedes_image_package_import():
    for name in (
        "check_postgres_pitr_remote.py",
        "restore_postgres_pitr_from_s3.py",
    ):
        source = (REPO_ROOT / "scripts/ha" / name).read_text(encoding="utf-8")
        explicit = source.index('explicit = os.getenv("POSTGRES_PITR_UPLOAD_HELPER"')
        image_import = source.index("from scripts.ha.upload_postgres_pitr_to_s3 import")
        assert explicit < image_import


def test_scheduled_runner_locks_before_validation_and_uses_literal_env(
    tmp_path,
    monkeypatch,
):
    descriptor = os.open(tmp_path / "lock", os.O_CREAT | os.O_RDWR, 0o600)
    deploy_descriptor = os.open(
        tmp_path / "deploy.lock", os.O_CREAT | os.O_RDWR, 0o600
    )
    calls = []
    validations = []
    ordering = []
    monkeypatch.setattr(scheduled.os, "geteuid", lambda: 0)
    monkeypatch.setattr(scheduled, "_open_lock", lambda _path: descriptor)
    monkeypatch.setattr(
        scheduled,
        "_open_owned_lock",
        lambda path, **_kwargs: ordering.append(("deploy-lock", path))
        or deploy_descriptor,
    )
    monkeypatch.setattr(
        scheduled,
        "_reject_maintenance_marker",
        lambda: ordering.append(("maintenance", None)),
    )
    monkeypatch.setattr(
        scheduled,
        "reconcile_project_operations",
        lambda project: ordering.append(("reconcile", project)),
    )
    monkeypatch.setattr(
        scheduled,
        "_attest_finalized_release",
        lambda project, compose: ordering.append(("attest", (project, compose))),
    )
    monkeypatch.setattr(
        scheduled,
        "_validate_helper",
        lambda path: validations.append(path),
    )

    def fake_run(args, **kwargs):
        os.fstat(descriptor)
        os.fstat(deploy_descriptor)
        ordering.append(("child", None))
        calls.append((list(args), kwargs))
        return 0

    monkeypatch.setattr(scheduled, "run_guarded_process", fake_run)

    source = Path(scheduled.__file__).read_text(encoding="utf-8")
    assert source.index("descriptor = _open_lock") < source.index(
        "for path in (*COMMON_HELPERS, helper)"
    )

    assert scheduled.run_scheduled(
        phase="wal-upload",
        project_dir="/opt/air-api",
        compose_file="docker-compose.patroni.yml",
        lock_path=tmp_path / "lock",
    ) == 0
    assert validations[-1] == scheduled.PHASE_HELPERS["wal-upload"]
    assert ordering == [
        ("deploy-lock", Path("/opt/air-api/.deploy.lock")),
        ("maintenance", None),
        ("reconcile", "/opt/air-api"),
        ("attest", ("/opt/air-api", "docker-compose.patroni.yml")),
        ("child", None),
    ]
    args, kwargs = calls[0]
    assert args == ["/bin/bash", str(scheduled.PHASE_HELPERS["wal-upload"])]
    assert kwargs["environment"] == {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/root",
        "LANG": "C",
        "LC_ALL": "C",
        "DOCKER_CONTEXT": "default",
        "PROJECT_DIR": "/opt/air-api",
        "COMPOSE_FILE": "docker-compose.patroni.yml",
    }
    assert kwargs["phase"] == "wal-upload"
    assert kwargs["kind"] == "scheduled"
    assert kwargs["unit"] == "mvn-postgres-wal-upload.service"
    assert kwargs["timeout_seconds"] is None
    with pytest.raises(OSError):
        os.fstat(descriptor)
    with pytest.raises(OSError):
        os.fstat(deploy_descriptor)


def test_scheduled_runner_reports_lock_collision_as_intentional_skip(
    monkeypatch,
    capsys,
):
    umask_calls = []
    monkeypatch.setattr(scheduled.os, "umask", umask_calls.append)
    monkeypatch.setattr(
        scheduled,
        "run_scheduled",
        lambda **_kwargs: (_ for _ in ()).throw(scheduled.LockBusyError("busy")),
    )

    result = scheduled.main(
        [
            "--phase",
            "wal-upload",
            "--project-dir",
            "/opt/air-api",
            "--compose-file",
            "docker-compose.patroni.yml",
        ]
    )

    assert result == 75
    assert umask_calls == [0o077]
    assert "busy" in capsys.readouterr().err
