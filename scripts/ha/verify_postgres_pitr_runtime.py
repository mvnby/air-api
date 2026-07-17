#!/usr/bin/env python3
"""Fail-closed runtime contract for host PostgreSQL PITR jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


BACKEND_IMAGE_RE = re.compile(
    r"^ghcr\.io/mvnby/air-api/backend@sha256:[0-9a-f]{64}$"
)
APP_SERVICES = ("app", "app-blue", "app-green")
RUNTIME_SERVICES = (*APP_SERVICES, "bot")
PUBLIC_PITR_ENV_POLICIES = ("runtime-only", "configured", "operational")
MIGRATION_PITR_ENV_POLICIES = ("legacy-migration", "migration-files-clean")
PITR_ENV_POLICIES = (*PUBLIC_PITR_ENV_POLICIES, *MIGRATION_PITR_ENV_POLICIES)
SECRETS_FILE = Path("/etc/mvn-postgres-pitr.secrets.env")
EXPECTED_COMPOSE_DIGESTS = {
    "/opt/air-api/docker-compose.patroni.yml": (
        "2d30b640b36eb3081ee439215d923388d2e542d40ce9c55d0502b4b11682282e"
    ),
    "/opt/mvn-reserve/docker-compose.patroni.yml": (
        "af02921ab9b4490017002aa08699d758486d858f16a741b72eef33feca27fff4"
    ),
}
EXPECTED_PITR_CLUSTERS = {
    "/opt/air-api/docker-compose.patroni.yml": "mvn-api",
    "/opt/mvn-reserve/docker-compose.patroni.yml": "mvn-api",
}
EXPECTED_DESTINATION_FINGERPRINT = (
    "3c6e78da6f79b317f8b62d3f979bb69dba1f2821e473a670be30ec08310f458b"
)
SECRET_PITR_KEYS = {
    "POSTGRES_PITR_CLUSTER",
    "POSTGRES_PITR_S3_BUCKET",
    "POSTGRES_PITR_S3_ENDPOINT_URL",
    "POSTGRES_PITR_S3_REGION",
    "POSTGRES_PITR_S3_ACCESS_KEY_ID",
    "POSTGRES_PITR_S3_SECRET_ACCESS_KEY",
    "POSTGRES_PITR_S3_KEY_PREFIX",
}
PROJECT_PITR_KEYS = {
    "POSTGRES_PITR_ARCHIVE_MODE",
    "POSTGRES_PITR_ARCHIVE_TIMEOUT",
}
KNOWN_PITR_KEYS = SECRET_PITR_KEYS | PROJECT_PITR_KEYS
FORBIDDEN_WAL_ARCHIVE_TARGET = "/postgres-wal-archive"
FORBIDDEN_WAL_ARCHIVE_MARKER = "postgres-wal-archive"
DOTENV_LINE_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
DOCKER_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "DOCKER_CONTEXT": "default",
}


@dataclass(frozen=True)
class ProjectEnvState:
    secret_values: Mapping[str, str]
    runtime_values: Mapping[str, str]


def _read_controlled_file(
    path: Path,
    *,
    mode: int,
    label: str,
    expected_uid: int = 0,
) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("required file protection is unavailable")
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} is missing") from exc
    def unsafe(value: os.stat_result) -> bool:
        return (
            not stat.S_ISREG(value.st_mode)
            or value.st_uid != expected_uid
            or value.st_nlink != 1
            or stat.S_IMODE(value.st_mode) != mode
        )

    if (
        stat.S_ISLNK(metadata.st_mode)
        or unsafe(metadata)
    ):
        raise RuntimeError(f"{label} metadata is unsafe")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if unsafe(opened) or (opened.st_dev, opened.st_ino) != (
            metadata.st_dev,
            metadata.st_ino,
        ):
            raise RuntimeError(f"{label} changed during validation")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, 131072)
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > 1024 * 1024:
                raise RuntimeError(f"{label} is unexpectedly large")
        finished = os.fstat(descriptor)
        if (
            finished.st_dev,
            finished.st_ino,
            finished.st_size,
            finished.st_mtime_ns,
            finished.st_ctime_ns,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ):
            raise RuntimeError(f"{label} changed during validation")
        if len(payload) != opened.st_size:
            raise RuntimeError(f"{label} changed during validation")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _parse_env_values(
    raw_env: bytes,
    *,
    allowed_names: set[str],
    label: str,
    reject_unknown: bool = False,
    reject_unknown_pitr: bool = False,
) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = raw_env.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{label} is not valid UTF-8") from exc
    for line in text.splitlines():
        match = DOTENV_LINE_RE.match(line.strip())
        if not match:
            continue
        name = match.group(1)
        if name not in allowed_names:
            if reject_unknown_pitr and name.startswith("POSTGRES_PITR_"):
                raise RuntimeError(f"{label} contains an unexpected PITR key")
            if reject_unknown:
                raise RuntimeError(f"{label} contains an unexpected key")
            continue
        key, raw_value = match.groups()
        if key in values:
            raise RuntimeError(f"{label} contains duplicate {key}")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value.strip()
    return values


def _validate_secret_values(
    values: Mapping[str, str],
    *,
    expected_cluster: str,
    expected_destination_fingerprint: str,
    label: str,
) -> dict[str, str]:
    missing = sorted(key for key in SECRET_PITR_KEYS if not values.get(key))
    if missing or set(values) != SECRET_PITR_KEYS:
        raise RuntimeError(f"{label} does not contain the exact secret key set")
    if values["POSTGRES_PITR_CLUSTER"] != expected_cluster:
        raise RuntimeError(f"{label} uses an unreviewed logical namespace")
    destination = "\n".join(
        values[key]
        for key in (
            "POSTGRES_PITR_S3_BUCKET",
            "POSTGRES_PITR_S3_ENDPOINT_URL",
            "POSTGRES_PITR_S3_REGION",
            "POSTGRES_PITR_S3_KEY_PREFIX",
        )
    ) + "\n"
    if hashlib.sha256(destination.encode("utf-8")).hexdigest() != (
        expected_destination_fingerprint
    ):
        raise RuntimeError(f"{label} uses an unreviewed archive destination")
    return dict(values)


def _validate_project_env(
    raw_env: bytes,
    *,
    policy: str,
    expected_cluster: str,
    expected_destination_fingerprint: str,
) -> ProjectEnvState:
    values = _parse_env_values(
        raw_env,
        allowed_names={*KNOWN_PITR_KEYS, "MVN_RESERVE_ENV_FILE"},
        label="project env",
        reject_unknown_pitr=True,
    )
    if values.get("MVN_RESERVE_ENV_FILE", ".env") != ".env":
        raise RuntimeError("reserve app does not use the canonical project env")
    secret_values = {
        key: values[key] for key in SECRET_PITR_KEYS if key in values
    }
    if policy == "legacy-migration":
        secret_values = _validate_secret_values(
            secret_values,
            expected_cluster=expected_cluster,
            expected_destination_fingerprint=expected_destination_fingerprint,
            label="legacy project env",
        )
    elif secret_values:
        raise RuntimeError("project env exposes private PITR settings to API/bot")
    if policy == "runtime-only":
        return ProjectEnvState(secret_values={}, runtime_values={})
    missing = sorted(key for key in PROJECT_PITR_KEYS if not values.get(key))
    if missing:
        raise RuntimeError("project env is missing PITR archive runtime settings")
    allowed_archive_modes = {"on"} if policy == "operational" else {"on", "off"}
    if values["POSTGRES_PITR_ARCHIVE_MODE"] not in allowed_archive_modes:
        raise RuntimeError("project PITR archive mode is not the reviewed value")
    if values["POSTGRES_PITR_ARCHIVE_TIMEOUT"] != "300s":
        raise RuntimeError("project PITR archive timeout is not the reviewed value")
    return ProjectEnvState(
        secret_values=secret_values,
        runtime_values={key: values[key] for key in PROJECT_PITR_KEYS},
    )


def _validate_secrets_env(
    raw_env: bytes,
    *,
    expected_cluster: str,
    expected_destination_fingerprint: str,
) -> dict[str, str]:
    values = _parse_env_values(
        raw_env,
        allowed_names=SECRET_PITR_KEYS,
        label="PITR secrets file",
        reject_unknown=True,
    )
    return _validate_secret_values(
        values,
        expected_cluster=expected_cluster,
        expected_destination_fingerprint=expected_destination_fingerprint,
        label="PITR secrets file",
    )


def _run_checked(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
) -> str:
    try:
        result = subprocess.run(
            list(args),
            cwd=cwd,
            env=DOCKER_ENV,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Docker runtime contract command timed out") from exc
    if result.returncode != 0:
        raise RuntimeError("Docker runtime contract command failed")
    return result.stdout.strip()


def _parse_runtime_environment(raw_values: object, *, label: str) -> dict[str, str]:
    if not isinstance(raw_values, list):
        raise RuntimeError(f"{label} environment is invalid")
    values: dict[str, str] = {}
    for entry in raw_values:
        if not isinstance(entry, str) or "=" not in entry:
            raise RuntimeError(f"{label} environment is invalid")
        name, value = entry.split("=", 1)
        if not name or name in values:
            raise RuntimeError(f"{label} environment is ambiguous")
        if name.startswith("POSTGRES_PITR_") and name not in KNOWN_PITR_KEYS:
            raise RuntimeError(f"{label} environment contains an unexpected PITR key")
        values[name] = value
    return values


def _validate_runtime_secret_exposure(
    environment: Mapping[str, str],
    *,
    policy: str,
    expected_secrets: Mapping[str, str],
    label: str,
    canonical_compose: bool,
) -> None:
    exposed = {
        key: environment[key] for key in SECRET_PITR_KEYS if key in environment
    }
    if policy == "legacy-migration":
        if not exposed and not canonical_compose:
            return
        if exposed != expected_secrets or set(exposed) != SECRET_PITR_KEYS:
            raise RuntimeError(f"{label} does not expose the exact reviewed legacy secrets")
        return
    if not exposed:
        return
    if policy == "migration-files-clean" and not canonical_compose:
        if exposed != expected_secrets or set(exposed) != SECRET_PITR_KEYS:
            raise RuntimeError(f"{label} does not match the committed PITR secrets")
        return
    raise RuntimeError(f"{label} exposes private PITR settings")


def _mount_references_wal_archive(mount: object) -> bool:
    if isinstance(mount, str):
        candidates = (mount,)
    elif isinstance(mount, dict):
        candidates = tuple(
            str(mount.get(name) or "")
            for name in ("source", "target", "Source", "Destination", "Name")
        )
    else:
        raise RuntimeError("API/bot mount definition is invalid")
    return any(
        value == FORBIDDEN_WAL_ARCHIVE_TARGET
        or FORBIDDEN_WAL_ARCHIVE_MARKER in value
        for value in candidates
    )


def _validate_no_wal_archive_mounts(mounts: object, *, label: str) -> None:
    if mounts is None:
        return
    if not isinstance(mounts, list):
        raise RuntimeError(f"{label} mount inventory is invalid")
    if any(_mount_references_wal_archive(mount) for mount in mounts):
        raise RuntimeError(f"{label} mounts the PostgreSQL WAL archive")


def _validate_runtime_wal_archive_mounts(
    mounts: object,
    *,
    label: str,
    project_dir: Path,
    policy: str,
) -> None:
    if mounts is None:
        return
    if not isinstance(mounts, list):
        raise RuntimeError(f"{label} mount inventory is invalid")

    archive_mounts = [
        mount for mount in mounts if _mount_references_wal_archive(mount)
    ]
    if not archive_mounts:
        return
    if policy not in MIGRATION_PITR_ENV_POLICIES:
        raise RuntimeError(f"{label} mounts the PostgreSQL WAL archive")

    expected_source = str(project_dir / FORBIDDEN_WAL_ARCHIVE_MARKER)
    if len(archive_mounts) != 1:
        raise RuntimeError(f"{label} has ambiguous PostgreSQL WAL archive mounts")
    mount = archive_mounts[0]
    if (
        not isinstance(mount, dict)
        or mount.get("Source") != expected_source
        or mount.get("Destination") != FORBIDDEN_WAL_ARCHIVE_TARGET
        or mount.get("Type") != "bind"
        or mount.get("RW") is not True
        or mount.get("source") not in {None, ""}
        or mount.get("target") not in {None, ""}
        or mount.get("Name") not in {None, ""}
    ):
        raise RuntimeError(f"{label} has an unreviewed PostgreSQL WAL archive mount")


def _configured_backend_image(
    project_dir: Path,
    compose_file: str,
    *,
    policy: str,
    expected_secrets: Mapping[str, str],
) -> str:
    raw_config = _run_checked(
        [
            "docker",
            "compose",
            "--profile",
            "bluegreen",
            "-f",
            compose_file,
            "config",
            "--format",
            "json",
        ],
        cwd=project_dir,
    )
    try:
        config = json.loads(raw_config)
        services = config["services"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("canonical Compose config is invalid") from exc
    if not isinstance(services, dict) or "app" not in services:
        raise RuntimeError("canonical Compose config has no app service")
    for name in RUNTIME_SERVICES:
        service = services.get(name)
        if not isinstance(service, dict):
            raise RuntimeError("canonical Compose config is missing an API/bot service")
        environment = service.get("environment") or {}
        if not isinstance(environment, dict):
            raise RuntimeError("resolved API/bot environment is invalid")
        for environment_name in environment:
            if (
                str(environment_name).startswith("POSTGRES_PITR_")
                and environment_name not in KNOWN_PITR_KEYS
            ):
                raise RuntimeError("resolved API/bot environment has an unexpected PITR key")
        _validate_runtime_secret_exposure(
            {str(key): str(value) for key, value in environment.items()},
            policy=policy,
            expected_secrets=expected_secrets,
            label="resolved API/bot environment",
            canonical_compose=True,
        )
        _validate_no_wal_archive_mounts(
            service.get("volumes"),
            label="resolved API/bot service",
        )
    images = {str(services[name].get("image") or "") for name in RUNTIME_SERVICES}
    if len(images) != 1:
        raise RuntimeError("PITR app services do not resolve to one backend image")
    image = images.pop()
    if not BACKEND_IMAGE_RE.fullmatch(image):
        raise RuntimeError("backend image is not an immutable reviewed GHCR digest")
    return image


def _inspect_runtime_containers(
    *,
    project_dir: Path,
    compose_file: str,
    backend_image: str,
    expected_image_id: str,
    policy: str,
    expected_secrets: Mapping[str, str],
) -> None:
    container_output = _run_checked(
        [
            "docker",
            "compose",
            "--profile",
            "bluegreen",
            "-f",
            compose_file,
            "ps",
            "--all",
            "-q",
            *RUNTIME_SERVICES,
        ],
        cwd=project_dir,
    )
    container_ids = [line for line in container_output.splitlines() if line]
    if not container_ids or len(container_ids) != len(set(container_ids)):
        raise RuntimeError("all-state API/bot container set is empty or ambiguous")

    seen_services: set[str] = set()
    running_services: set[str] = set()
    for container_id in container_ids:
        raw_inspection = _run_checked(
            ["docker", "inspect", "--format", "{{json .}}", container_id]
        )
        try:
            inspection = json.loads(raw_inspection)
            config = inspection["Config"]
            labels = config["Labels"]
            state = inspection["State"]
            running_id = str(inspection["Image"])
            configured_ref = str(config["Image"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("API/bot container inspection is invalid") from exc
        if not isinstance(config, dict) or not isinstance(labels, dict):
            raise RuntimeError("API/bot container inspection is invalid")
        if not isinstance(state, dict) or not isinstance(state.get("Running"), bool):
            raise RuntimeError("API/bot container state is invalid")
        service = labels.get("com.docker.compose.service")
        if service not in RUNTIME_SERVICES or service in seen_services:
            raise RuntimeError("all-state API/bot service identity is unexpected or ambiguous")
        seen_services.add(service)

        if not BACKEND_IMAGE_RE.fullmatch(configured_ref):
            raise RuntimeError("API/bot container image is not an immutable reviewed digest")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", running_id):
            raise RuntimeError("API/bot container image ID is invalid")
        if state["Running"]:
            running_services.add(service)
        if state["Running"] or policy in MIGRATION_PITR_ENV_POLICIES:
            if configured_ref != backend_image or running_id != expected_image_id:
                raise RuntimeError("API/bot container does not match the resolved image")

        environment = _parse_runtime_environment(
            config.get("Env"),
            label="API/bot container",
        )
        _validate_runtime_secret_exposure(
            environment,
            policy=policy,
            expected_secrets=expected_secrets,
            label="API/bot container",
            canonical_compose=False,
        )
        _validate_runtime_wal_archive_mounts(
            inspection.get("Mounts"),
            label="API/bot container",
            project_dir=project_dir,
            policy=policy,
        )
    if not set(APP_SERVICES).intersection(running_services):
        raise RuntimeError("no reviewed API slot is running")


def verify_runtime_contract(
    *,
    project_dir: Path,
    compose_file: str,
    expected_compose_digests: Mapping[str, str] = EXPECTED_COMPOSE_DIGESTS,
    expected_pitr_clusters: Mapping[str, str] = EXPECTED_PITR_CLUSTERS,
    expected_destination_fingerprint: str | None = None,
    pitr_env_policy: str = "operational",
    secrets_file: Path = SECRETS_FILE,
    expected_uid: int = 0,
) -> str:
    if os.geteuid() != expected_uid:
        raise RuntimeError("root execution is required")
    if compose_file != "docker-compose.patroni.yml":
        raise RuntimeError("only docker-compose.patroni.yml is accepted")
    if pitr_env_policy not in PITR_ENV_POLICIES:
        raise RuntimeError("unsupported PITR environment policy")
    destination_fingerprint = (
        EXPECTED_DESTINATION_FINGERPRINT
        if expected_destination_fingerprint is None
        else expected_destination_fingerprint
    )
    if not re.fullmatch(r"[0-9a-f]{64}", destination_fingerprint):
        raise RuntimeError("reviewed PITR destination fingerprint is invalid")
    if not project_dir.is_absolute() or project_dir.resolve() != project_dir:
        raise RuntimeError("project directory must be an exact absolute path")

    compose_path = project_dir / compose_file
    expected_digest = expected_compose_digests.get(str(compose_path))
    expected_cluster = expected_pitr_clusters.get(str(compose_path))
    if expected_digest is None or expected_cluster is None:
        raise RuntimeError("unreviewed Patroni project directory")
    compose_payload = _read_controlled_file(
        compose_path,
        mode=0o644,
        label="canonical Compose file",
        expected_uid=expected_uid,
    )
    if hashlib.sha256(compose_payload).hexdigest() != expected_digest:
        raise RuntimeError("canonical Compose file digest mismatch")
    env_payload = _read_controlled_file(
        project_dir / ".env",
        mode=0o600,
        label="project env file",
        expected_uid=expected_uid,
    )
    project_state = _validate_project_env(
        env_payload,
        policy=pitr_env_policy,
        expected_cluster=expected_cluster,
        expected_destination_fingerprint=destination_fingerprint,
    )
    secrets_present = secrets_file.exists() or secrets_file.is_symlink()
    if pitr_env_policy == "legacy-migration" and secrets_present:
        raise RuntimeError("legacy migration requires the root PITR secrets file to be absent")
    secrets_values: Mapping[str, str] = {}
    if pitr_env_policy not in {"runtime-only", "legacy-migration"} or secrets_present:
        secrets_payload = _read_controlled_file(
            secrets_file,
            mode=0o600,
            label="PITR secrets file",
            expected_uid=expected_uid,
        )
        secrets_values = _validate_secrets_env(
            secrets_payload,
            expected_cluster=expected_cluster,
            expected_destination_fingerprint=destination_fingerprint,
        )
    expected_runtime_secrets = (
        project_state.secret_values
        if pitr_env_policy == "legacy-migration"
        else secrets_values
    )

    endpoint = _run_checked(
        [
            "docker",
            "context",
            "inspect",
            "default",
            "--format",
            "{{.Endpoints.docker.Host}}",
        ]
    )
    if endpoint != "unix:///var/run/docker.sock":
        raise RuntimeError("Docker default context is not the local system socket")

    backend_image = _configured_backend_image(
        project_dir,
        compose_file,
        policy=pitr_env_policy,
        expected_secrets=expected_runtime_secrets,
    )
    expected_image_id = _run_checked(
        ["docker", "image", "inspect", "--format", "{{.Id}}", backend_image]
    )
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image_id):
        raise RuntimeError("resolved backend image ID is invalid")

    _inspect_runtime_containers(
        project_dir=project_dir,
        compose_file=compose_file,
        backend_image=backend_image,
        expected_image_id=expected_image_id,
        policy=pitr_env_policy,
        expected_secrets=expected_runtime_secrets,
    )
    return backend_image


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--compose-file", required=True)
    parser.add_argument(
        "--pitr-env-policy",
        choices=PITR_ENV_POLICIES,
        default="operational",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        image = verify_runtime_contract(
            project_dir=Path(args.project_dir),
            compose_file=args.compose_file,
            pitr_env_policy=args.pitr_env_policy,
        )
    except (OSError, RuntimeError) as exc:
        print(f"PITR runtime contract: {exc}", file=sys.stderr)
        return 1
    print(image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
