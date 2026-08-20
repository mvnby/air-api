#!/usr/bin/env python3
"""Run the fixed legacy-owner shadow cutover on reviewed Patroni runtimes.

The controller has deliberately no target, host, path, image, or command
inputs.  It can only invoke the in-image ``cutover_legacy_owner.py`` command
for the singleton ``mvn/main`` legacy owner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ha.pitr_cluster_topology import ClusterTopology, discover_cluster_topology  # noqa: E402
from scripts.ha.pitr_pinned_ssh import (  # noqa: E402
    PATRONI_NODES, PatroniNode, PinnedSshContext, create_context, ssh_args,
    ssh_subprocess_environment, validate_effective_config,
)
from scripts.ops.legacy_owner_cutover_result_contract import (  # noqa: E402
    WorkflowError, assert_no_forbidden_artifact_keys, load_result, sanitize_plan,
    sanitize_verify, validate_result_semantics,
)
from scripts.ha.verify_patroni_release_image import (  # noqa: E402
    VerificationError,
    verify_provenance,
)


DIGEST_RE = re.compile(r"[0-9a-f]{64}")
IMMUTABLE_BACKEND_RE = re.compile(r"ghcr\.io/mvnby/air-api/backend@sha256:[0-9a-f]{64}")
REVIEWED_SHA_RE = re.compile(r"[0-9a-f]{40}")
REVIEWED_SOURCE = "https://github.com/mvnby/air-api"
REMOTE_DEPLOY_LOCK_HELPER = Path("/usr/local/libexec/mvn-pitr/safe_deploy_lock.py")
LOCAL_DEPLOY_LOCK_HELPER = REPO_ROOT / "scripts/ha/safe_deploy_lock.py"
ARTIFACT_KEYS = {
    "schema_version", "operation", "reviewed_main_sha", "primary_node",
    "patroni_timeline", "runtime", "result", "proof", "outcome", "recovery",
}
MAX_ONE_TIME_CREDENTIAL_BYTES = 256


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
    parser = argparse.ArgumentParser(description="Perform reviewed legacy-owner shadow cutover")
    parser.add_argument("operation", choices=("plan", "execute", "rollback"))
    parser.add_argument("--plan-for", choices=("cutover", "rollback"), default="cutover")
    parser.add_argument("--reviewed-plan-digest")
    parser.add_argument(
        "--credential-stdin",
        action="store_true",
        help="Read the execute-only one-time staff credential from stdin.",
    )
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    if args.operation == "plan":
        if args.reviewed_plan_digest or args.credential_stdin:
            raise WorkflowError("plan does not accept a reviewed plan digest")
    elif args.operation == "execute" and not args.credential_stdin:
        raise WorkflowError("execute requires the protected credential on stdin")
    elif args.operation == "rollback" and args.credential_stdin:
        raise WorkflowError("rollback does not accept a staff credential")
    elif args.plan_for != "cutover":
        raise WorkflowError("mutation does not accept a plan-for override")
    elif not DIGEST_RE.fullmatch(args.reviewed_plan_digest or ""):
        raise WorkflowError("mutation requires an exact reviewed plan digest")
    _validate_private_file(args.identity_file, description="SSH identity")
    if not args.result_file.is_absolute():
        raise WorkflowError("result file path must be absolute")


def _validate_private_file(path: Path, *, description: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise WorkflowError(f"{description} is missing") from exc
    if (stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid() or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) & 0o077):
        raise WorkflowError(f"{description} must be an owner-only regular file")


def _read_one_time_credential(stream: Any | None = None) -> str:
    source = stream if stream is not None else sys.stdin.buffer
    payload = source.read(MAX_ONE_TIME_CREDENTIAL_BYTES + 1)
    if len(payload) > MAX_ONE_TIME_CREDENTIAL_BYTES:
        raise WorkflowError("one-time credential input is too large")
    try:
        credential = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkflowError("one-time credential input is not UTF-8") from exc
    if not credential:
        raise WorkflowError("one-time credential input is empty")
    return credential


def _subprocess_runner(command: Sequence[str], stdin: str | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), input=stdin, text=True, capture_output=True,
                          check=False, env=ssh_subprocess_environment())


def _remote_prelude(
    node: PatroniNode, *, role: str, expected_runtime: RuntimeTarget | None = None
) -> list[str]:
    if role not in {"primary", "standby"}:
        raise WorkflowError("reviewed Patroni runtime role is invalid")
    compose = shlex.join(["docker", "compose", "-f", node.compose_file, "--profile", "bluegreen"])
    lines = [
        "set -euo pipefail", f"cd {shlex.quote(node.project_dir)}",
        "test -f .active-api-slot && test ! -L .active-api-slot",
        "active_slot=$(tr -d '\\r\\n' < .active-api-slot)",
        'case "${active_slot}" in blue|green) active_service="app-${active_slot}" ;; *) exit 75 ;; esac',
        (
            "curl -fsS --max-time 5 http://127.0.0.1:8008/"
            f"{'leader' if role == 'primary' else 'replica'} >/dev/null"
        ),
        f'container_id="$({compose} ps -q "${{active_service}}")"',
        'test -n "${container_id}"',
        'test "$(docker inspect -f \'{{.State.Running}}\' "${container_id}")" = true',
    ]
    if expected_runtime:
        lines.extend([
            f'test "${{active_service}}" = {shlex.quote(expected_runtime.service)}',
            f'test "${{container_id}}" = {shlex.quote(expected_runtime.container_id)}',
            'test "$(docker inspect -f \'{{.Config.Image}}\' "${container_id}")" = '
            + shlex.quote(expected_runtime.image),
        ])
    return lines


def _runtime_target_command(node: PatroniNode, *, role: str) -> str:
    lines = _remote_prelude(node, role=role)
    lines.extend([
        'runtime_image=$(docker inspect -f \'{{.Config.Image}}\' "${container_id}")',
        'printf \'%s|%s|%s\\n\' "${active_service}" "${container_id}" "${runtime_image}"',
    ])
    return "; ".join(lines)


def _parse_runtime_target(raw: str) -> RuntimeTarget:
    fields = raw.split("|")
    if len(fields) != 3:
        raise WorkflowError("active API runtime identity is invalid")
    service, container_id, image = fields
    if service not in {"app-blue", "app-green"} or not re.fullmatch(r"[0-9a-f]{64}", container_id):
        raise WorkflowError("active API runtime identity is invalid")
    if not IMMUTABLE_BACKEND_RE.fullmatch(image):
        raise WorkflowError("active API container does not use a reviewed immutable image")
    return RuntimeTarget(service=service, container_id=container_id, image=image)


def _reviewed_backend_image_for_sha(reviewed_sha: str) -> str:
    if not REVIEWED_SHA_RE.fullmatch(reviewed_sha):
        raise WorkflowError("reviewed main SHA is unavailable for image verification")
    tag = f"ghcr.io/mvnby/air-api/backend:{reviewed_sha}"
    try:
        completed = subprocess.run(
            ["docker", "buildx", "imagetools", "inspect", tag, "--raw"],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise WorkflowError("reviewed backend image tag could not be resolved") from exc
    digest = "sha256:" + hashlib.sha256(completed.stdout).hexdigest()
    image = f"ghcr.io/mvnby/air-api/backend@{digest}"
    if not IMMUTABLE_BACKEND_RE.fullmatch(image):
        raise WorkflowError("reviewed backend image digest is invalid")
    try:
        provenance = subprocess.run(
            [
                "docker", "buildx", "imagetools", "inspect", image,
                "--format", "{{json .Provenance}}",
            ],
            check=True,
            capture_output=True,
            timeout=120,
        ).stdout
        provenance_payload = json.loads(provenance)
        if not isinstance(provenance_payload, dict):
            raise VerificationError("backend image provenance is not an object")
        verify_provenance(
            provenance_payload,
            expected_source=REVIEWED_SOURCE,
            expected_revision=reviewed_sha,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        UnicodeDecodeError,
        json.JSONDecodeError,
        VerificationError,
    ) as exc:
        raise WorkflowError("reviewed backend image provenance does not match main SHA") from exc
    return image


def _cutover_command(
    node: PatroniNode,
    *,
    runtime: RuntimeTarget,
    role: str,
    action: str,
    token: str | None = None,
    prove_credential: bool = False,
) -> str:
    command = ["python3", "scripts/cutover_legacy_owner.py", action]
    if action == "plan" and token:
        command.extend(["--for-action", token])
    elif action in {"execute", "rollback"}:
        command.append("--execution-json-stdin")
    elif action == "verify" and prove_credential:
        command.append("--credential-json-stdin")
    lines = _remote_prelude(node, role=role, expected_runtime=runtime)
    lines.append(f"docker exec -i {shlex.quote(runtime.container_id)} {shlex.join(command)}")
    return "; ".join(lines)


def _capability_command(node: PatroniNode, *, runtime: RuntimeTarget, role: str) -> str:
    lines = _remote_prelude(node, role=role, expected_runtime=runtime)
    lines.append(
        f"docker exec -i {shlex.quote(runtime.container_id)} python3 scripts/cutover_legacy_owner.py --help "
        "| grep -F -- '--execution-json-stdin' >/dev/null "
        "&& docker exec -i "
        f"{shlex.quote(runtime.container_id)} python3 scripts/cutover_legacy_owner.py --help "
        "| grep -F -- '--credential-json-stdin' >/dev/null"
    )
    return "; ".join(lines)


def _run_remote(node: PatroniNode, context: PinnedSshContext, command: str, *, stdin: str | None = None,
                accepted_statuses: frozenset[int] = frozenset({0})) -> RemoteOutput:
    locked = shlex.join([
        "env", f"API_DEPLOY_LOCK_HELPER_SHA256={_deploy_lock_helper_digest()}", "python3",
        str(REMOTE_DEPLOY_LOCK_HELPER), "exec", f"{node.project_dir}/.deploy.lock",
        "bash", "-c", command,
    ])
    result = _subprocess_runner([*ssh_args(node, context), locked], stdin)
    if result.returncode not in accepted_statuses:
        raise WorkflowError(f"reviewed operation failed on {node.alias} with status {result.returncode}")
    return RemoteOutput(status=result.returncode, stdout=result.stdout.strip())


def _deploy_lock_helper_digest() -> str:
    metadata = LOCAL_DEPLOY_LOCK_HELPER.lstat()
    if (stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid() or metadata.st_nlink != 1
            or metadata.st_mode & 0o022):
        raise WorkflowError("local deployment lock helper is unreviewed")
    return hashlib.sha256(LOCAL_DEPLOY_LOCK_HELPER.read_bytes()).hexdigest()


def _fresh_plan(primary: PatroniNode, context: PinnedSshContext, runtime: RuntimeTarget, *, for_action: str) -> tuple[dict[str, Any], str]:
    output = _run_remote(primary, context, _cutover_command(primary, runtime=runtime, role="primary", action="plan", token=for_action),
                         accepted_statuses=frozenset({0, 2}))
    result = load_result(output.stdout, expected_mode="plan")
    validate_result_semantics(result, expected_mode="plan", remote_status=output.status)
    return result, sanitize_plan(result)[1]


def _proof_all_nodes(
    context: PinnedSshContext,
    topology: ClusterTopology,
    *,
    expected_image: str,
    staff_credential: str,
    binding_challenge: str,
) -> dict[str, dict[str, Any]]:
    proof: dict[str, dict[str, Any]] = {}
    bindings: set[str] = set()
    for node in PATRONI_NODES:
        role = "primary" if node == topology.primary else "standby"
        runtime = _parse_runtime_target(
            _run_remote(node, context, _runtime_target_command(node, role=role)).stdout
        )
        if runtime.image != expected_image:
            raise WorkflowError("cutover proof runtime image differs from reviewed primary image")
        payload = json.dumps(
            {
                "binding_challenge": binding_challenge,
                "new_password": staff_credential,
            },
            separators=(",", ":"),
        )
        result = _verify_node(
            node=node,
            context=context,
            runtime=runtime,
            role=role,
            payload=payload,
            expected_modes=frozenset({"staff_shadow", "staff"}),
        )
        sanitized, binding = sanitize_verify(result)
        bindings.add(binding)
        proof[node.alias] = {"runtime_service": runtime.service, "runtime_image": runtime.image, "result": sanitized}
    if set(proof) != {node.alias for node in PATRONI_NODES}:
        raise WorkflowError("cutover proof did not cover both Patroni nodes")
    if len(bindings) != 1:
        raise WorkflowError("cutover proof found different local legacy credential bindings")
    return proof
def _verify_node(
    *, node: PatroniNode, context: PinnedSshContext, runtime: RuntimeTarget,
    role: str, payload: str, expected_modes: frozenset[str],
) -> dict[str, Any]:
    attempts = 10 if role == "standby" else 1
    last_result: dict[str, Any] | None = None
    for attempt in range(attempts):
        output = _run_remote(
            node,
            context,
            _cutover_command(
                node,
                runtime=runtime,
                role=role,
                action="verify",
                prove_credential=True,
            ),
            stdin=payload,
            accepted_statuses=frozenset({0, 2}),
        )
        try:
            result = load_result(output.stdout, expected_mode="verify")
            validate_result_semantics(
                result,
                expected_mode="verify",
                remote_status=output.status,
            )
            last_result = result
            if result["ready"] and result["auth_mode"] in expected_modes:
                return result
        except WorkflowError:
            pass
        if attempt + 1 < attempts:
            time.sleep(2)
    if last_result is not None:
        safe_codes = ",".join(last_result["blockers"]) or "unexpected_mode"
        message = (f"legacy_owner_cutover_verification status=blocked node={node.alias} "
                   f"role={role} auth_mode={last_result['auth_mode']} blockers={safe_codes}")
        print(message, file=sys.stderr)
    raise WorkflowError(f"legacy-owner {role} verification did not reach the reviewed mode")
def _assert_dual_node_runtime_capability(
    context: PinnedSshContext, topology: ClusterTopology, *, expected_image: str
) -> None:
    for node in PATRONI_NODES:
        role = "primary" if node == topology.primary else "standby"
        runtime = _parse_runtime_target(
            _run_remote(node, context, _runtime_target_command(node, role=role)).stdout
        )
        if runtime.image != expected_image:
            raise WorkflowError("cutover runtime image differs from reviewed primary image")
        _run_remote(node, context, _capability_command(node, runtime=runtime, role=role))


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
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
    binding_challenge = secrets.token_hex(32)
    staff_credential = (
        _read_one_time_credential() if args.operation == "execute" else None
    )
    with tempfile.TemporaryDirectory(prefix="legacy-owner-cutover-ssh-") as name:
        directory = Path(name)
        directory.chmod(0o700)
        context = create_context(directory, args.identity_file)
        for node in PATRONI_NODES:
            validate_effective_config(node, context)
        topology = discover_cluster_topology(context=context, runner=_subprocess_runner)
        primary = topology.primary
        runtime = _parse_runtime_target(
            _run_remote(primary, context, _runtime_target_command(primary, role="primary")).stdout
        )
        reviewed_image = _reviewed_backend_image_for_sha(os.environ.get("GITHUB_SHA", ""))
        if runtime.image != reviewed_image:
            raise WorkflowError("active primary image is not bound to the reviewed main SHA")
        _assert_dual_node_runtime_capability(
            context, topology, expected_image=reviewed_image
        )
        plan_action = (
            args.plan_for if args.operation == "plan"
            else "rollback" if args.operation == "rollback" else "cutover"
        )
        plan, plan_token = _fresh_plan(primary, context, runtime, for_action=plan_action)
        sanitized_plan, _ = sanitize_plan(plan)
        result: dict[str, Any] = sanitized_plan
        proof: dict[str, dict[str, Any]] | None = None
        if plan["current"].get("auth_mode") == "legacy":
            try:
                legacy_proof = _verify_legacy_after_rollback(
                    context,
                    topology,
                    expected_image=runtime.image,
                    binding_challenge=binding_challenge,
                )
            except WorkflowError:
                if args.operation != "plan":
                    raise WorkflowError(
                        "cross-node legacy recovery preflight is not proved"
                    )
                result = {
                    **sanitized_plan,
                    "ready": False,
                    "blockers": [
                        *sanitized_plan["blockers"],
                        "cross_node_legacy_recovery_unproved",
                    ],
                    "changes": [],
                }
            else:
                if args.operation == "plan":
                    proof = legacy_proof
        if args.operation != "plan":
            if not plan["ready"]:
                raise WorkflowError("fresh legacy-owner plan is blocked")
            if plan["plan_digest"] != args.reviewed_plan_digest:
                raise WorkflowError("fresh plan differs from the reviewed plan digest")
            if discover_cluster_topology(context=context, runner=_subprocess_runner) != topology:
                raise WorkflowError("Patroni topology changed after plan; run a fresh operation")
            execution_payload: dict[str, str] = {"plan_token": plan_token}
            if args.operation == "execute":
                execution_payload["new_password"] = str(staff_credential or "")
            payload = json.dumps(execution_payload, separators=(",", ":"))
            try:
                output = _run_remote(
                    primary,
                    context,
                    _cutover_command(
                        primary, runtime=runtime, role="primary", action=args.operation
                    ),
                    stdin=payload,
                    accepted_statuses=frozenset({0, 2}),
                )
                result = load_result(output.stdout, expected_mode=args.operation)
                validate_result_semantics(
                    result, expected_mode=args.operation, remote_status=output.status
                )
                if args.operation == "execute":
                    proof = _proof_all_nodes(
                        context,
                        topology,
                        expected_image=runtime.image,
                        staff_credential=str(staff_credential or ""),
                        binding_challenge=binding_challenge,
                    )
                elif args.operation == "rollback":
                    proof = _verify_legacy_after_rollback(
                        context,
                        topology,
                        expected_image=runtime.image,
                        binding_challenge=binding_challenge,
                    )
            except Exception as mutation_error:
                if args.operation != "execute":
                    raise
                try:
                    recovery_proof = _recover_after_uncertain_execute(
                        context,
                        topology,
                        runtime.image,
                        staff_credential=str(staff_credential or ""),
                        binding_challenge=binding_challenge,
                    )
                except Exception as recovery_error:
                    raise WorkflowError(
                        "execute outcome is uncertain and automatic recovery was not proved"
                    ) from recovery_error
                artifact = _artifact(
                    operation=args.operation,
                    topology=topology,
                    runtime=runtime,
                    result=None,
                    proof=recovery_proof,
                    outcome="recovered",
                    recovery="legacy_restored",
                )
                _write_result(args.result_file, artifact)
                raise WorkflowError(
                    "execute output or staff-shadow proof failed; automatic recovery completed"
                ) from mutation_error
        artifact = _artifact(
            operation=args.operation,
            topology=topology,
            runtime=runtime,
            result=result,
            proof=proof,
            outcome="completed",
            recovery=None,
        )
        _write_result(args.result_file, artifact)
        return artifact


def _artifact(
    *, operation: str, topology: ClusterTopology, runtime: RuntimeTarget,
    result: dict[str, Any] | None, proof: dict[str, dict[str, Any]] | None,
    outcome: str, recovery: str | None,
) -> dict[str, Any]:
    artifact = {
        "schema_version": 1, "operation": operation,
        "reviewed_main_sha": os.environ.get("GITHUB_SHA", "local"),
        "primary_node": topology.primary.alias, "patroni_timeline": topology.timeline,
        "runtime": {"service": runtime.service, "image": runtime.image},
        "result": result, "proof": proof, "outcome": outcome, "recovery": recovery,
    }
    if set(artifact) != ARTIFACT_KEYS or outcome not in {"completed", "recovered"}:
        raise WorkflowError("operation artifact schema is not reviewed")
    if (outcome == "recovered") != (recovery == "legacy_restored"):
        raise WorkflowError("operation artifact recovery state is invalid")
    if outcome == "recovered" and not proof:
        raise WorkflowError("recovery artifact lacks the required dual-node proof")
    assert_no_forbidden_artifact_keys(artifact)
    return artifact


def _automatic_rollback(
    context: PinnedSshContext,
    reviewed_topology: ClusterTopology,
    expected_image: str,
    *,
    binding_challenge: str,
) -> dict[str, dict[str, Any]]:
    topology = discover_cluster_topology(context=context, runner=_subprocess_runner)
    if topology != reviewed_topology:
        raise WorkflowError("automatic rollback refused after Patroni topology changed")
    primary = topology.primary
    runtime = _parse_runtime_target(
        _run_remote(primary, context, _runtime_target_command(primary, role="primary")).stdout
    )
    if runtime.image != expected_image:
        raise WorkflowError("automatic rollback refused after reviewed runtime image changed")
    _run_remote(primary, context, _capability_command(primary, runtime=runtime, role="primary"))
    plan, token = _fresh_plan(primary, context, runtime, for_action="rollback")
    if not plan["ready"]:
        raise WorkflowError("automatic rollback plan is blocked")
    payload = json.dumps({"plan_token": token}, separators=(",", ":"))
    output = _run_remote(primary, context, _cutover_command(primary, runtime=runtime, role="primary", action="rollback"), stdin=payload,
                         accepted_statuses=frozenset({0, 2}))
    result = load_result(output.stdout, expected_mode="rollback")
    validate_result_semantics(result, expected_mode="rollback", remote_status=output.status)
    return _verify_legacy_after_rollback(
        context,
        topology,
        expected_image=expected_image,
        binding_challenge=binding_challenge,
    )


def _recover_after_uncertain_execute(
    context: PinnedSshContext,
    reviewed_topology: ClusterTopology,
    expected_image: str,
    *,
    staff_credential: str,
    binding_challenge: str,
) -> dict[str, dict[str, Any]]:
    topology = discover_cluster_topology(context=context, runner=_subprocess_runner)
    if topology != reviewed_topology:
        raise WorkflowError("automatic recovery refused after Patroni topology changed")
    primary = topology.primary
    runtime = _parse_runtime_target(
        _run_remote(primary, context, _runtime_target_command(primary, role="primary")).stdout
    )
    if runtime.image != expected_image:
        raise WorkflowError("automatic recovery refused after reviewed runtime image changed")
    _run_remote(primary, context, _capability_command(primary, runtime=runtime, role="primary"))
    result = _verify_node(
        node=primary,
        context=context,
        runtime=runtime,
        role="primary",
        payload=json.dumps(
            {
                "binding_challenge": binding_challenge,
                "new_password": staff_credential,
            },
            separators=(",", ":"),
        ),
        expected_modes=frozenset({"legacy", "staff_shadow"}),
    )
    if result["auth_mode"] == "legacy":
        return _verify_legacy_after_rollback(
            context,
            topology,
            expected_image=expected_image,
            binding_challenge=binding_challenge,
        )
    if result["auth_mode"] == "staff_shadow":
        return _automatic_rollback(
            context,
            topology,
            expected_image,
            binding_challenge=binding_challenge,
        )
    raise WorkflowError("automatic recovery found an unsupported legacy-owner mode")


def _verify_legacy_after_rollback(
    context: PinnedSshContext,
    topology: ClusterTopology,
    *,
    expected_image: str,
    binding_challenge: str,
) -> dict[str, dict[str, Any]]:
    proof: dict[str, dict[str, Any]] = {}
    bindings: set[str] = set()
    for node in PATRONI_NODES:
        role = "primary" if node == topology.primary else "standby"
        runtime = _parse_runtime_target(
            _run_remote(node, context, _runtime_target_command(node, role=role)).stdout
        )
        if runtime.image != expected_image:
            raise WorkflowError("legacy rollback proof runtime image differs from reviewed primary image")
        result = _verify_node(
            node=node,
            context=context,
            runtime=runtime,
            role=role,
            payload=json.dumps(
                {"binding_challenge": binding_challenge},
                separators=(",", ":"),
            ),
            expected_modes=frozenset({"legacy"}),
        )
        sanitized, binding = sanitize_verify(result)
        bindings.add(binding)
        proof[node.alias] = {
            "runtime_service": runtime.service,
            "runtime_image": runtime.image,
            "result": sanitized,
        }
    if set(proof) != {node.alias for node in PATRONI_NODES}:
        raise WorkflowError("legacy rollback proof did not cover both Patroni nodes")
    if len(bindings) != 1:
        raise WorkflowError("legacy rollback proof found different local credential bindings")
    return proof


def main() -> None:
    args = build_parser().parse_args()
    try:
        artifact = execute(args)
    except WorkflowError as exc:
        print("legacy_owner_cutover_workflow status=blocked", file=sys.stderr)
        raise SystemExit(2) from exc
    result = artifact["result"]
    if args.operation == "plan" and not result.get("ready", False):
        raise SystemExit(2)
    print(f"legacy_owner_cutover_workflow status=passed operation={args.operation} primary={artifact['primary_node']}")


if __name__ == "__main__":
    main()
