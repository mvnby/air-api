"""Strict, secret-free output contract for tenant-manager automation."""

from __future__ import annotations

import json
import re
from typing import Any


DIGEST_RE = re.compile(r"[0-9a-f]{64}")
PLAN_RESULT_KEYS = {
    "mode",
    "ready",
    "target",
    "current",
    "blockers",
    "changes",
    "plan_digest",
    "plan_token",
    "plan_token_max_age_seconds",
    "reviewed_execute_command",
}
EXECUTE_RESULT_KEYS = {
    "mode",
    "ready",
    "changed",
    "target",
    "staff_user_id",
    "membership_id",
}
FORBIDDEN_ARTIFACT_KEYS = {
    "password",
    "password_hash",
    "plan_token",
    "reviewed_execute_command",
    "secret",
    "credential",
}


class WorkflowError(RuntimeError):
    """A fail-closed workflow precondition was not met."""


def load_result(raw: str, *, expected_mode: str) -> dict[str, Any]:
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkflowError("tenant-manager CLI returned invalid JSON") from exc
    if not isinstance(result, dict) or result.get("mode") != expected_mode:
        raise WorkflowError("tenant-manager CLI returned an unexpected result")
    expected_keys = (
        PLAN_RESULT_KEYS if expected_mode == "plan" else EXECUTE_RESULT_KEYS
    )
    if set(result) != expected_keys:
        raise WorkflowError("tenant-manager CLI result schema is not reviewed")
    return result


def validate_result_semantics(
    result: dict[str, Any], *, expected_mode: str, remote_status: int
) -> None:
    ready = result["ready"]
    if type(ready) is not bool:
        raise WorkflowError("tenant-manager ready state is invalid")
    expected_status = 0 if ready else 2
    if remote_status != expected_status:
        raise WorkflowError("tenant-manager exit status disagrees with ready state")
    _validate_target_shape(result["target"])

    if expected_mode == "plan":
        _validate_plan(result, ready=ready)
        return
    if ready is not True or type(result["changed"]) is not bool:
        raise WorkflowError("tenant-manager execute state is invalid")
    for key in ("staff_user_id", "membership_id"):
        if type(result[key]) is not int or result[key] <= 0:
            raise WorkflowError(f"tenant-manager {key} is invalid")


def _validate_plan(result: dict[str, Any], *, ready: bool) -> None:
    if not isinstance(result["current"], dict):
        raise WorkflowError("tenant-manager current state is invalid")
    _validate_current_state(result["current"])
    if not _is_string_list(result["blockers"]):
        raise WorkflowError("tenant-manager blocker list is invalid")
    if not _is_string_list(result["changes"]):
        raise WorkflowError("tenant-manager change list is invalid")
    reviewed_changes = [
        "create_staff_user",
        "create_active_manager_membership",
    ]
    if result["changes"] not in ([], reviewed_changes):
        raise WorkflowError("tenant-manager change list is not reviewed")
    if not isinstance(result["plan_token"], str) or not result["plan_token"]:
        raise WorkflowError("tenant-manager plan token is invalid")
    if not isinstance(result["plan_digest"], str) or not DIGEST_RE.fullmatch(
        result["plan_digest"]
    ):
        raise WorkflowError("tenant-manager plan digest is invalid")
    if type(result["plan_token_max_age_seconds"]) is not int or not (
        1 <= result["plan_token_max_age_seconds"] <= 3600
    ):
        raise WorkflowError("tenant-manager plan token lifetime is invalid")
    reviewed_command = result["reviewed_execute_command"]
    if ready:
        if not isinstance(reviewed_command, str) or not reviewed_command:
            raise WorkflowError("tenant-manager reviewed command is invalid")
        if result["blockers"]:
            raise WorkflowError("ready plan cannot contain blockers")
    elif reviewed_command is not None or not result["blockers"] or result["changes"]:
        raise WorkflowError("blocked plan semantics are invalid")


def _validate_target_shape(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "tenant_slug",
        "storefront_slug",
        "display_name",
        "username",
        "phone",
    }:
        raise WorkflowError("tenant-manager target shape is invalid")
    if any(not isinstance(item, str) or not item for item in value.values()):
        raise WorkflowError("tenant-manager target value is invalid")


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item) for item in value
    )


def _validate_current_state(current: dict[str, Any]) -> None:
    if set(current) != {"tenant", "storefront", "staff_users", "memberships"}:
        raise WorkflowError("tenant-manager current state schema is not reviewed")
    _validate_tenant_state(current["tenant"])
    _validate_storefront_state(current["storefront"])
    if not isinstance(current["staff_users"], list) or not isinstance(
        current["memberships"], list
    ):
        raise WorkflowError("tenant-manager identity state is invalid")
    for user in current["staff_users"]:
        _validate_staff_user_state(user)
    for membership in current["memberships"]:
        _validate_membership_state(membership)


def _validate_tenant_state(tenant: Any) -> None:
    if tenant is None:
        return
    if not isinstance(tenant, dict) or set(tenant) != {
        "id",
        "status",
        "is_system",
    }:
        raise WorkflowError("tenant-manager tenant state is invalid")
    if (
        type(tenant["id"]) is not int
        or tenant["id"] <= 0
        or not isinstance(tenant["status"], str)
        or type(tenant["is_system"]) is not bool
    ):
        raise WorkflowError("tenant-manager tenant state is invalid")


def _validate_storefront_state(storefront: Any) -> None:
    if storefront is None:
        return
    if not isinstance(storefront, dict) or set(storefront) != {
        "id",
        "tenant_id",
        "status",
        "is_default",
    }:
        raise WorkflowError("tenant-manager storefront state is invalid")
    if (
        any(
            type(storefront[key]) is not int or storefront[key] <= 0
            for key in ("id", "tenant_id")
        )
        or not isinstance(storefront["status"], str)
        or type(storefront["is_default"]) is not bool
    ):
        raise WorkflowError("tenant-manager storefront state is invalid")


def _validate_staff_user_state(user: Any) -> None:
    expected = {
        "id",
        "username",
        "display_name",
        "phone",
        "status",
        "primary_role",
        "roles",
        "legacy_installer_id",
        "telegram_id",
        "telegram_username",
    }
    if not isinstance(user, dict) or set(user) != expected:
        raise WorkflowError("tenant-manager staff-user state is invalid")
    if type(user["id"]) is not int or user["id"] <= 0:
        raise WorkflowError("tenant-manager staff-user identity is invalid")
    for key in ("username", "display_name", "phone", "status", "primary_role"):
        if user[key] is not None and not isinstance(user[key], str):
            raise WorkflowError("tenant-manager staff-user value is invalid")
    if not isinstance(user["roles"], list) or not all(
        isinstance(role, str) for role in user["roles"]
    ):
        raise WorkflowError("tenant-manager staff-user roles are invalid")
    for key in ("legacy_installer_id", "telegram_id"):
        if user[key] is not None and type(user[key]) is not int:
            raise WorkflowError("tenant-manager staff-user link is invalid")
    if user["telegram_username"] is not None and not isinstance(
        user["telegram_username"], str
    ):
        raise WorkflowError("tenant-manager Telegram username is invalid")


def _validate_membership_state(membership: Any) -> None:
    if not isinstance(membership, dict) or set(membership) != {
        "id",
        "tenant_id",
        "role",
        "status",
    }:
        raise WorkflowError("tenant-manager membership state is invalid")
    if any(
        type(membership[key]) is not int or membership[key] <= 0
        for key in ("id", "tenant_id")
    ) or any(
        not isinstance(membership[key], str) or not membership[key]
        for key in ("role", "status")
    ):
        raise WorkflowError("tenant-manager membership state is invalid")


def sanitize_plan(result: dict[str, Any]) -> tuple[dict[str, Any], str]:
    plan_token = result.get("plan_token")
    plan_digest = result.get("plan_digest")
    if not isinstance(plan_token, str) or not plan_token:
        raise WorkflowError("tenant-manager plan did not issue a plan token")
    if not isinstance(plan_digest, str) or not DIGEST_RE.fullmatch(plan_digest):
        raise WorkflowError("tenant-manager plan digest is invalid")
    sanitized = {
        key: result[key]
        for key in sorted(
            PLAN_RESULT_KEYS - {"plan_token", "reviewed_execute_command"}
        )
    }
    assert_no_forbidden_artifact_keys(sanitized)
    return sanitized, plan_token


def assert_no_forbidden_artifact_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_ARTIFACT_KEYS:
                raise WorkflowError("operation result contains forbidden secret material")
            assert_no_forbidden_artifact_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_forbidden_artifact_keys(nested)
