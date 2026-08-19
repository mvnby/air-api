#!/usr/bin/env python3
"""Run the tenant-manager CLI on the single healthy Patroni primary.

This controller deliberately exposes no arbitrary remote command option.  It
uses the repository-pinned two-node inventory, validates the complete Patroni
topology, discovers the active immutable API container, and invokes only
``scripts/provision_tenant_manager.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ha.pitr_cluster_topology import (  # noqa: E402
    ClusterTopology,
    discover_cluster_topology,
)
from scripts.ha.pitr_pinned_ssh import (  # noqa: E402
    PATRONI_NODES,
    PatroniNode,
    PinnedSshContext,
    create_context,
    ssh_args,
    ssh_subprocess_environment,
    validate_effective_config,
)
from scripts.ops.tenant_manager_result_contract import (  # noqa: E402
    WorkflowError,
    assert_no_forbidden_artifact_keys as _assert_no_forbidden_artifact_keys,
    load_result as _load_result,
    sanitize_plan,
    validate_result_semantics as _validate_result_semantics,
)


SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
USERNAME_RE = re.compile(r"[a-z][a-z0-9._-]{2,63}")
PHONE_RE = re.compile(r"\+[1-9][0-9]{7,14}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")
IMMUTABLE_BACKEND_RE = re.compile(
    r"ghcr\.io/mvnby/air-api/backend@sha256:[0-9a-f]{64}"
)
MAX_PASSWORD_BYTES = 256
REMOTE_DEPLOY_LOCK_HELPER = Path("/usr/local/libexec/mvn-pitr/safe_deploy_lock.py")
LOCAL_DEPLOY_LOCK_HELPER = REPO_ROOT / "scripts/ha/safe_deploy_lock.py"
@dataclass(frozen=True)
class RuntimeTarget:
    service: str
    container_id: str
    image: str


@dataclass(frozen=True)
class RemoteOutput:
    status: int
    stdout: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision one tenant manager on the current Patroni primary"
    )
    parser.add_argument("operation", choices=("plan", "execute"))
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--storefront-slug", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--phone", required=True)
    parser.add_argument("--reviewed-plan-digest")
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    if not SLUG_RE.fullmatch(args.tenant_slug) or len(args.tenant_slug) > 63:
        raise WorkflowError("tenant slug is invalid")
    if not SLUG_RE.fullmatch(args.storefront_slug) or len(args.storefront_slug) > 63:
        raise WorkflowError("storefront slug is invalid")
    if not USERNAME_RE.fullmatch(args.username):
        raise WorkflowError("username is invalid")
    if not PHONE_RE.fullmatch(args.phone):
        raise WorkflowError("phone must be a complete E.164 number")
    if (
        args.display_name != args.display_name.strip()
        or not 1 <= len(args.display_name) <= 100
        or any(ord(character) < 32 or ord(character) == 127 for character in args.display_name)
    ):
        raise WorkflowError("display name is invalid")
    if args.operation == "plan" and args.reviewed_plan_digest:
        raise WorkflowError("plan does not accept a reviewed plan digest")
    if args.operation == "execute" and not DIGEST_RE.fullmatch(
        args.reviewed_plan_digest or ""
    ):
        raise WorkflowError("execute requires an exact reviewed plan digest")
    _validate_private_file(args.identity_file, description="SSH identity")
    if not args.result_file.is_absolute():
        raise WorkflowError("result file path must be absolute")


def _validate_private_file(path: Path, *, description: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise WorkflowError(f"{description} is missing") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise WorkflowError(f"{description} must be an owner-only regular file")


def _subprocess_runner(
    command: Sequence[str], stdin: str | None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env=ssh_subprocess_environment(),
    )


def _remote_prelude(
    node: PatroniNode, *, expected_runtime: RuntimeTarget | None = None
) -> list[str]:
    compose = shlex.join(
        ["docker", "compose", "-f", node.compose_file, "--profile", "bluegreen"]
    )
    lines = [
        "set -euo pipefail",
        f"cd {shlex.quote(node.project_dir)}",
        "test -f .active-api-slot && test ! -L .active-api-slot",
        "active_slot=$(tr -d '\\r\\n' < .active-api-slot)",
        'case "${active_slot}" in blue|green) active_service="app-${active_slot}" ;; '
        "*) echo 'invalid active API slot' >&2; exit 75 ;; esac",
        (
            "curl -fsS --max-time 5 http://127.0.0.1:8008/leader "
            ">/dev/null"
        ),
        f'container_id="$({compose} ps -q "${{active_service}}")"',
        'test -n "${container_id}"',
        'test "$(docker inspect -f \'{{.State.Running}}\' "${container_id}")" = true',
    ]
    if expected_runtime is not None:
        lines.extend(
            [
                f"test \"${{active_service}}\" = {shlex.quote(expected_runtime.service)}",
                f"test \"${{container_id}}\" = {shlex.quote(expected_runtime.container_id)}",
                (
                    "test \"$(docker inspect -f '{{.Config.Image}}' "
                    f"\"${{container_id}}\")\" = {shlex.quote(expected_runtime.image)}"
                ),
            ]
        )
    return lines


def _runtime_target_command(node: PatroniNode) -> str:
    lines = _remote_prelude(node)
    lines.append(
        "runtime_image=$(docker inspect -f '{{.Config.Image}}' \"${container_id}\")"
    )
    lines.append(
        "printf '%s|%s|%s\\n' \"${active_service}\" "
        '"${container_id}" "${runtime_image}"'
    )
    return "; ".join(lines)


def _parse_runtime_target(raw: str) -> RuntimeTarget:
    fields = raw.split("|")
    if len(fields) != 3:
        raise WorkflowError("active API runtime identity is invalid")
    service, container_id, image = fields
    if service not in {"app-blue", "app-green"}:
        raise WorkflowError("active API service is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", container_id):
        raise WorkflowError("active API container identity is invalid")
    if not IMMUTABLE_BACKEND_RE.fullmatch(image):
        raise WorkflowError("active API container does not use a reviewed immutable image")
    return RuntimeTarget(service=service, container_id=container_id, image=image)


def _runtime_capability_command(
    node: PatroniNode, *, runtime: RuntimeTarget
) -> str:
    lines = _remote_prelude(node, expected_runtime=runtime)
    lines.append(
        f"docker exec -i {shlex.quote(runtime.container_id)} "
        "python3 scripts/provision_tenant_manager.py --help "
        "| grep -F -- '--execution-json-stdin' >/dev/null"
    )
    return "; ".join(lines)


def _provisioning_command(
    node: PatroniNode,
    *,
    runtime: RuntimeTarget,
    operation: str,
    tenant_slug: str,
    storefront_slug: str,
    display_name: str,
    username: str,
    phone: str,
) -> str:
    command = [
        "python3",
        "scripts/provision_tenant_manager.py",
        operation,
        "--tenant-slug",
        tenant_slug,
        "--storefront-slug",
        storefront_slug,
        "--display-name",
        display_name,
        "--username",
        username,
        "--phone",
        phone,
    ]
    if operation == "execute":
        command.append("--execution-json-stdin")
    lines = _remote_prelude(node, expected_runtime=runtime)
    lines.append(
        f"docker exec -i {shlex.quote(runtime.container_id)} {shlex.join(command)}"
    )
    return "; ".join(lines)


def _run_remote(
    node: PatroniNode,
    context: PinnedSshContext,
    command: str,
    *,
    stdin: str | None = None,
    accepted_statuses: frozenset[int] = frozenset({0}),
) -> RemoteOutput:
    helper_digest = _deploy_lock_helper_digest()
    locked_command = shlex.join(
        [
            "env",
            f"API_DEPLOY_LOCK_HELPER_SHA256={helper_digest}",
            "python3",
            str(REMOTE_DEPLOY_LOCK_HELPER),
            "exec",
            f"{node.project_dir}/.deploy.lock",
            "bash",
            "-c",
            command,
        ]
    )
    result = _subprocess_runner(
        [*ssh_args(node, context), locked_command], stdin
    )
    if result.returncode not in accepted_statuses:
        raise WorkflowError(
            f"reviewed operation failed on {node.alias} with status {result.returncode}"
        )
    return RemoteOutput(status=result.returncode, stdout=result.stdout.strip())


def _deploy_lock_helper_digest() -> str:
    metadata = LOCAL_DEPLOY_LOCK_HELPER.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o022
    ):
        raise WorkflowError("local deployment lock helper is unreviewed")
    return hashlib.sha256(LOCAL_DEPLOY_LOCK_HELPER.read_bytes()).hexdigest()


def _assert_target(result: dict[str, Any], args: argparse.Namespace) -> None:
    expected = {
        "tenant_slug": args.tenant_slug,
        "storefront_slug": args.storefront_slug,
        "display_name": args.display_name,
        "username": args.username,
        "phone": args.phone,
    }
    if result.get("target") != expected:
        raise WorkflowError("tenant-manager CLI normalized to an unexpected target")


def _read_password(stream: Any | None = None) -> str:
    source = stream if stream is not None else sys.stdin.buffer
    payload = source.read(MAX_PASSWORD_BYTES + 1)
    if len(payload) > MAX_PASSWORD_BYTES:
        raise WorkflowError("one-time password input is too large")
    if payload.endswith(b"\r\n"):
        payload = payload[:-2]
    elif payload.endswith(b"\n"):
        payload = payload[:-1]
    try:
        password = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkflowError("one-time password must be UTF-8") from exc
    if not password:
        raise WorkflowError("one-time password is required for execute")
    if len(password.encode("utf-8")) > 72:
        raise WorkflowError("one-time password exceeds the bcrypt byte limit")
    return password


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, path)
    path.chmod(0o600)


def execute(args: argparse.Namespace) -> dict[str, Any]:
    validate_arguments(args)
    password = _read_password() if args.operation == "execute" else None
    with tempfile.TemporaryDirectory(prefix="tenant-manager-ssh-") as directory_name:
        directory = Path(directory_name)
        directory.chmod(0o700)
        context = create_context(directory, args.identity_file)
        for node in PATRONI_NODES:
            validate_effective_config(node, context)
        topology: ClusterTopology = discover_cluster_topology(
            context=context,
            runner=_subprocess_runner,
        )
        primary = topology.primary
        runtime = _parse_runtime_target(
            _run_remote(
                primary,
                context,
                _runtime_target_command(primary),
            ).stdout
        )

        _run_remote(
            primary,
            context,
            _runtime_capability_command(primary, runtime=runtime),
        )

        plan_output = _run_remote(
            primary,
            context,
            _provisioning_command(
                primary,
                runtime=runtime,
                operation="plan",
                tenant_slug=args.tenant_slug,
                storefront_slug=args.storefront_slug,
                display_name=args.display_name,
                username=args.username,
                phone=args.phone,
            ),
            accepted_statuses=frozenset({0, 2}),
        )
        plan = _load_result(plan_output.stdout, expected_mode="plan")
        _validate_result_semantics(
            plan,
            expected_mode="plan",
            remote_status=plan_output.status,
        )
        _assert_target(plan, args)
        sanitized_plan, plan_token = sanitize_plan(plan)

        result: dict[str, Any]
        if args.operation == "plan":
            result = sanitized_plan
        else:
            if not plan.get("ready", False):
                raise WorkflowError("fresh provisioning plan is blocked")
            if plan.get("plan_digest") != args.reviewed_plan_digest:
                raise WorkflowError("fresh plan differs from the reviewed plan digest")
            current_topology = discover_cluster_topology(
                context=context,
                runner=_subprocess_runner,
            )
            if current_topology != topology:
                raise WorkflowError(
                    "Patroni topology changed after plan; run a fresh operation"
                )
            execution_payload = json.dumps(
                {"plan_token": plan_token, "password": password},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            execute_output = _run_remote(
                primary,
                context,
                _provisioning_command(
                    primary,
                    runtime=runtime,
                    operation="execute",
                    tenant_slug=args.tenant_slug,
                    storefront_slug=args.storefront_slug,
                    display_name=args.display_name,
                    username=args.username,
                    phone=args.phone,
                ),
                stdin=execution_payload,
            )
            result = _load_result(execute_output.stdout, expected_mode="execute")
            _validate_result_semantics(
                result,
                expected_mode="execute",
                remote_status=execute_output.status,
            )
            _assert_target(result, args)
            _assert_no_forbidden_artifact_keys(result)

        artifact = {
            "schema_version": 1,
            "operation": args.operation,
            "reviewed_main_sha": os.environ.get("GITHUB_SHA", "local"),
            "primary_node": primary.alias,
            "patroni_timeline": topology.timeline,
            "runtime_service": runtime.service,
            "runtime_container_id": runtime.container_id,
            "runtime_image": runtime.image,
            "result": result,
        }
        _assert_no_forbidden_artifact_keys(artifact)
        _write_result(args.result_file, artifact)
        return artifact


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        artifact = execute(args)
    except WorkflowError as exc:
        print(f"tenant_manager_workflow status=blocked error={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except Exception as exc:
        print(
            "tenant_manager_workflow status=error error=unexpected operation failure",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    result = artifact["result"]
    if artifact["operation"] == "plan" and not result.get("ready", False):
        print(
            "tenant_manager_workflow status=blocked operation=plan "
            f"primary={artifact['primary_node']} artifact=written",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print(
        "tenant_manager_workflow "
        f"status=passed operation={artifact['operation']} "
        f"primary={artifact['primary_node']} ready={result.get('ready', False)} "
        f"plan_digest={result.get('plan_digest', 'reviewed')}"
    )


if __name__ == "__main__":
    main()
