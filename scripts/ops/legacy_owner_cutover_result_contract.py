"""Fail-closed, secret-free output contract for legacy-owner cutover automation."""

from __future__ import annotations

import json
import re
from typing import Any


DIGEST_RE = re.compile(r"[0-9a-f]{64}")
BINDING_RE = re.compile(r"[0-9a-f]{64}")
PLAN_KEYS = {
    "mode", "ready", "target", "current", "blockers", "changes",
    "plan_digest", "plan_token", "plan_token_max_age_seconds",
}
MUTATION_KEYS = {
    "mode", "ready", "changed", "staff_user_id", "membership_id",
    "system_tenant_id", "system_storefront_id", "auth_mode",
    "legacy_token_version", "plan_digest",
}
VERIFY_KEYS = {
    "mode", "ready", "blockers", "staff_user_id", "membership_id",
    "system_tenant_id", "system_storefront_id", "auth_mode",
    "legacy_token_version", "credential_matches", "can_change_password",
    "auth_source_staff_password", "legacy_jwt_rejected", "legacy_google_auth_rejected",
    "runtime_binding",
}
FORBIDDEN_KEY_FRAGMENTS = (
    "password", "hash", "secret", "username",
)
FORBIDDEN_EXACT_KEYS = {"plan_token", "runtime_binding"}
SAFE_PUBLIC_BOOLEAN_KEYS = {
    "auth_source_staff_password",
    "can_change_password",
    "credential_matches",
}


class WorkflowError(RuntimeError):
    """A reviewed cutover precondition or output contract was violated."""


def load_result(raw: str, *, expected_mode: str) -> dict[str, Any]:
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkflowError("legacy-owner CLI returned invalid JSON") from exc
    if not isinstance(result, dict) or result.get("mode") != expected_mode:
        raise WorkflowError("legacy-owner CLI returned an unexpected result")
    expected = {
        "plan": PLAN_KEYS,
        "execute": MUTATION_KEYS,
        "rollback": MUTATION_KEYS,
        "verify": VERIFY_KEYS,
    }.get(expected_mode)
    if expected is None or set(result) != expected:
        raise WorkflowError("legacy-owner CLI result schema is not reviewed")
    return result


def validate_result_semantics(
    result: dict[str, Any], *, expected_mode: str, remote_status: int
) -> None:
    ready = result["ready"]
    if type(ready) is not bool:
        raise WorkflowError("legacy-owner ready state is invalid")
    if remote_status != (0 if ready else 2):
        raise WorkflowError("legacy-owner exit status disagrees with ready state")
    if expected_mode == "plan":
        _validate_plan(result, ready=ready)
    elif expected_mode == "verify":
        _validate_proof(result, expected_mode=expected_mode, ready=ready)
    else:
        _validate_mutation(result, expected_mode=expected_mode, ready=ready)


def sanitize_plan(result: dict[str, Any]) -> tuple[dict[str, Any], str]:
    token = result.get("plan_token")
    if not isinstance(token, str) or not token or len(token) > 512:
        raise WorkflowError("legacy-owner plan token is invalid")
    sanitized = {key: result[key] for key in sorted(PLAN_KEYS - {"plan_token"})}
    assert_no_forbidden_artifact_keys(sanitized)
    return sanitized, token


def sanitize_verify(result: dict[str, Any]) -> tuple[dict[str, Any], str]:
    binding = result.get("runtime_binding")
    if not isinstance(binding, str) or not BINDING_RE.fullmatch(binding):
        raise WorkflowError("legacy-owner runtime binding is invalid")
    sanitized = {key: result[key] for key in sorted(VERIFY_KEYS - {"runtime_binding"})}
    assert_no_forbidden_artifact_keys(sanitized)
    return sanitized, binding


def assert_no_forbidden_artifact_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if (
                normalized not in SAFE_PUBLIC_BOOLEAN_KEYS
                and (
                    normalized in FORBIDDEN_EXACT_KEYS
                    or any(
                        fragment in normalized
                        for fragment in FORBIDDEN_KEY_FRAGMENTS
                    )
                )
            ):
                raise WorkflowError("operation result contains forbidden secret material")
            assert_no_forbidden_artifact_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_forbidden_artifact_keys(nested)


def _validate_plan(result: dict[str, Any], *, ready: bool) -> None:
    target = result["target"]
    if target != {"system_tenant_slug": "mvn", "system_storefront_slug": "main"}:
        raise WorkflowError("legacy-owner target is not the canonical system scope")
    if not isinstance(result["current"], dict):
        raise WorkflowError("legacy-owner current state is invalid")
    for list_key in ("blockers", "changes"):
        if not _string_list(result[list_key]):
            raise WorkflowError(f"legacy-owner {list_key} is invalid")
    if not isinstance(result["plan_digest"], str) or not DIGEST_RE.fullmatch(result["plan_digest"]):
        raise WorkflowError("legacy-owner plan digest is invalid")
    if not isinstance(result["plan_token"], str) or not result["plan_token"]:
        raise WorkflowError("legacy-owner plan token is invalid")
    lifetime = result["plan_token_max_age_seconds"]
    if type(lifetime) is not int or not 1 <= lifetime <= 3600:
        raise WorkflowError("legacy-owner plan token lifetime is invalid")
    if ready and result["blockers"]:
        raise WorkflowError("ready plan cannot contain blockers")
    if not ready and not result["blockers"]:
        raise WorkflowError("blocked plan must name blockers")


def _validate_mutation(result: dict[str, Any], *, expected_mode: str, ready: bool) -> None:
    if ready is not True or type(result["changed"]) is not bool:
        raise WorkflowError("legacy-owner mutation state is invalid")
    _validate_ids(result)
    if result["auth_mode"] != ("legacy" if expected_mode == "rollback" else "staff_shadow"):
        raise WorkflowError("legacy-owner mutation mode is invalid")
    if type(result["legacy_token_version"]) is not int or result["legacy_token_version"] < 1:
        raise WorkflowError("legacy-owner token version is invalid")
    if not isinstance(result["plan_digest"], str) or not DIGEST_RE.fullmatch(result["plan_digest"]):
        raise WorkflowError("legacy-owner plan digest is invalid")


def _validate_proof(result: dict[str, Any], *, expected_mode: str, ready: bool) -> None:
    blockers = result["blockers"]
    if not _string_list(blockers) or ready == bool(blockers):
        raise WorkflowError("legacy-owner verification blockers are invalid")
    if result["auth_mode"] not in {"legacy", "staff_shadow", "staff"}:
        raise WorkflowError("legacy-owner verification mode is invalid")
    _validate_scope_ids(result)
    if result["auth_mode"] == "legacy":
        identity_ids = (result["staff_user_id"], result["membership_id"])
        if identity_ids != (None, None) and not all(
            type(value) is int and value > 0 for value in identity_ids
        ):
            raise WorkflowError("legacy-owner identity proof is invalid")
    else:
        _validate_identity_ids(result)
    if type(result["legacy_token_version"]) is not int or result["legacy_token_version"] < 1:
        raise WorkflowError("legacy-owner token version is invalid")
    if any(type(result[key]) is not bool for key in (
        "credential_matches", "can_change_password", "auth_source_staff_password",
        "legacy_jwt_rejected", "legacy_google_auth_rejected",
    )):
        raise WorkflowError("legacy-owner verification flags are invalid")
    # In legacy mode this means the retained local canonical ADMIN_* credential
    # is present.  It intentionally does not mean policy compliance or equality with
    # the retained StaffUser bcrypt hash: that hash can change before a later
    # manual rollback and must not make the legacy recovery unverifiable.
    if ready and not result["credential_matches"]:
        raise WorkflowError("legacy-owner verification proof is incomplete")
    if ready and result["auth_mode"] in {"staff_shadow", "staff"} and not all(
        result[key] for key in ("can_change_password", "legacy_jwt_rejected", "legacy_google_auth_rejected")
    ):
        raise WorkflowError("legacy-owner verification proof is incomplete")
    if ready and result["auth_mode"] in {"staff_shadow", "staff"} and result["auth_source_staff_password"] is not True:
        raise WorkflowError("legacy-owner verification did not prove staff password authentication")
    if not isinstance(result["runtime_binding"], str) or not BINDING_RE.fullmatch(result["runtime_binding"]):
        raise WorkflowError("legacy-owner runtime binding is invalid")


def _validate_ids(result: dict[str, Any]) -> None:
    _validate_identity_ids(result)
    _validate_scope_ids(result)


def _validate_identity_ids(result: dict[str, Any]) -> None:
    for key in ("staff_user_id", "membership_id"):
        if type(result[key]) is not int or result[key] <= 0:
            raise WorkflowError(f"legacy-owner {key} is invalid")


def _validate_scope_ids(result: dict[str, Any]) -> None:
    for key in ("system_tenant_id", "system_storefront_id"):
        if type(result[key]) is not int or result[key] <= 0:
            raise WorkflowError(f"legacy-owner {key} is invalid")


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)
