#!/usr/bin/env python3
"""Fixed reviewed owner consolidation using the established deployment gates."""

import argparse
import json
import os
from pathlib import Path
import secrets
import shlex
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ops import legacy_owner_cutover_workflow as gates


PUBLIC_KEYS = {
    "mode", "ready", "complete", "source_staff_user_id", "target_staff_user_id",
    "blockers", "source_references", "changes", "preserve_target_auth_version", "plan_digest",
}


def parse_result(output, *, action):
    try:
        result = json.loads(output.stdout)
    except (ValueError, TypeError):
        raise gates.WorkflowError("Owner profile result is invalid") from None
    extra = {"plan_token"} if action == "plan" else {"runtime_binding"} if action == "verify" else {"changed"}
    if not isinstance(result, dict) or set(result) != PUBLIC_KEYS | extra or result.get("mode") != action:
        raise gates.WorkflowError("Owner profile result schema is not reviewed")
    if (
        type(result["ready"]) is not bool or type(result["complete"]) is not bool
        or result["source_staff_user_id"] != 1 or result["target_staff_user_id"] != 4
        or result["preserve_target_auth_version"] is not True
        or not gates.DIGEST_RE.fullmatch(str(result["plan_digest"]))
        or output.status != (0 if result["ready"] else 2)
    ):
        raise gates.WorkflowError("Owner profile result semantics are invalid")
    if action == "verify" and not gates.DIGEST_RE.fullmatch(str(result["runtime_binding"])):
        raise gates.WorkflowError("Recovery proof is invalid")
    if action == "plan" and (not isinstance(result["plan_token"], str) or not 1 <= len(result["plan_token"]) <= 512):
        raise gates.WorkflowError("Owner profile plan token is invalid")
    return result


def sanitize(result):
    # Allowlisting prevents any future credential/challenge/token field leaking.
    cleaned = {key: result[key] for key in PUBLIC_KEYS}
    gates.assert_no_forbidden_artifact_keys(cleaned)
    return cleaned


def command(node, runtime, role, action):
    args = ["python3", "scripts/consolidate_owner_profile.py", action]
    if action != "plan":
        args.append("--protected-json-stdin")
    lines = gates._remote_prelude(node, role=role, expected_runtime=runtime)
    lines.append(f"docker exec -i {shlex.quote(runtime.container_id)} {shlex.join(args)}")
    return "; ".join(lines)


def request(node, context, runtime, role, action, payload=None):
    output = gates._run_remote(
        node, context, command(node, runtime, role, action),
        stdin=json.dumps(payload) if payload is not None else None,
        accepted_statuses=frozenset({0, 2}),
    )
    return parse_result(output, action=action)


def prove(context, topology, reviewed_image, challenge, *, complete=None):
    results, bindings = {}, []
    for node, role in ((topology.primary, "primary"), (topology.standby, "standby")):
        runtime = gates._parse_runtime_target(gates._run_remote(
            node, context, gates._runtime_target_command(node, role=role),
        ).stdout)
        if runtime.image != reviewed_image:
            raise gates.WorkflowError("Both active images must match reviewed main")
        result = None
        for attempt in range(10 if role == "standby" else 1):
            result = request(node, context, runtime, role, "verify", {"binding_challenge": challenge})
            if result["ready"] and (complete is None or result["complete"] == complete):
                break
            if role == "standby" and attempt < 9:
                time.sleep(2)
        if not result or not result["ready"] or (complete is not None and result["complete"] != complete):
            raise gates.WorkflowError("Owner profile node verification failed")
        bindings.append(result["runtime_binding"])
        results[node.alias] = sanitize(result)
    if len(set(bindings)) != 1:
        raise gates.WorkflowError("Node emergency credentials disagree")
    return results


def execute(args):
    gates._validate_private_file(args.identity_file, description="SSH identity")
    if not args.result_file.is_absolute():
        raise gates.WorkflowError("Result path must be absolute")
    if args.operation == "execute":
        if not gates.DIGEST_RE.fullmatch(args.reviewed_plan_digest or ""):
            raise gates.WorkflowError("Execute requires reviewed digest")
    elif args.reviewed_plan_digest:
        raise gates.WorkflowError("Plan cannot receive a digest")
    challenge = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="owner-profile-ssh-") as name:
        directory = Path(name)
        directory.chmod(0o700)
        context = gates.create_context(directory, args.identity_file)
        for node in gates.PATRONI_NODES:
            gates.validate_effective_config(node, context)
        topology = gates.discover_cluster_topology(context=context, runner=gates._subprocess_runner)
        reviewed_image = gates._reviewed_backend_image_for_sha(os.environ.get("GITHUB_SHA", ""))
        runtime = gates._parse_runtime_target(gates._run_remote(
            topology.primary, context, gates._runtime_target_command(topology.primary, role="primary"),
        ).stdout)
        if runtime.image != reviewed_image:
            raise gates.WorkflowError("Primary image changed after proof")
        plan = request(topology.primary, context, runtime, "primary", "plan")
        result = plan
        try:
            proof = prove(context, topology, reviewed_image, challenge)
        except gates.WorkflowError:
            # Preserve the sanitized blockers/report for review even when a
            # source change makes the operation (and its proof) unavailable.
            artifact = {
                "operation": args.operation, "outcome": "blocked", "reviewed_main_sha": os.environ.get("GITHUB_SHA"),
                "result": {**sanitize(plan), "ready": False,
                           "blockers": sorted(set(plan["blockers"] + ["dual_node_proof_failed"]))},
            }
            gates.assert_no_forbidden_artifact_keys(artifact)
            gates._write_result(args.result_file, artifact)
            if args.operation == "execute":
                raise gates.WorkflowError("Owner operation preflight proof failed") from None
            return artifact
        if args.operation == "execute":
            if not plan["ready"] or plan["plan_digest"] != args.reviewed_plan_digest:
                raise gates.WorkflowError("Fresh plan differs from reviewed operation")
            if gates.discover_cluster_topology(context=context, runner=gates._subprocess_runner) != topology:
                raise gates.WorkflowError("Topology changed after plan")
            try:
                result = request(topology.primary, context, runtime, "primary", "execute", {"plan_token": plan["plan_token"]})
                if not result["ready"] or not result["complete"]:
                    raise gates.WorkflowError("Owner consolidation did not complete")
                proof = prove(context, topology, reviewed_image, challenge, complete=True)
            except Exception:
                # Auth-only recovery never re-splits the person or rewrites FKs.
                recovery = gates._automatic_rollback(context, topology, reviewed_image, binding_challenge=challenge)
                recovery_artifact = {
                    "operation": args.operation, "outcome": "legacy_restored",
                    "reviewed_main_sha": os.environ.get("GITHUB_SHA"), "proof": recovery,
                }
                gates.assert_no_forbidden_artifact_keys(recovery_artifact)
                gates._write_result(args.result_file, recovery_artifact)
                raise gates.WorkflowError("Consolidation proof failed; emergency authentication restored") from None
        artifact = {
            "operation": args.operation, "outcome": "completed", "reviewed_main_sha": os.environ.get("GITHUB_SHA"),
            "primary_node": topology.primary.alias, "runtime_image": reviewed_image,
            "result": sanitize(result), "proof": proof,
        }
        gates.assert_no_forbidden_artifact_keys(artifact)
        gates._write_result(args.result_file, artifact)
        return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "execute"))
    parser.add_argument("--reviewed-plan-digest")
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        artifact = execute(args)
    except Exception:
        print("owner_profile_workflow status=blocked", file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps({"ready": artifact["result"]["ready"], "operation": args.operation}))
    if not artifact["result"]["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
