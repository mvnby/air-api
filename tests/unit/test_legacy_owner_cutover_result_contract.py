import json

import pytest

from scripts.ops import legacy_owner_cutover_result_contract as contract


def _plan(*, ready: bool = True) -> dict:
    return {
        "mode": "plan", "ready": ready,
        "target": {"system_tenant_slug": "mvn", "system_storefront_slug": "main"},
        "current": {"auth_mode": "legacy"}, "blockers": [] if ready else ["blocked"],
        "changes": ["stage_staff_shadow"] if ready else [], "plan_digest": "a" * 64,
        "plan_token": "signed-token", "plan_token_max_age_seconds": 900,
    }


def _verify(*, mode: str = "staff_shadow") -> dict:
    return {
        "mode": "verify", "ready": True, "blockers": [],
        "staff_user_id": 1, "membership_id": 2,
        "system_tenant_id": 3, "system_storefront_id": 4, "auth_mode": mode,
        "legacy_token_version": 2, "credential_matches": True, "can_change_password": True,
        "auth_source_staff_password": True,
        "legacy_jwt_rejected": True, "legacy_google_auth_rejected": True,
        "runtime_binding": "b" * 64,
    }


def test_plan_sanitizer_removes_replay_token_and_preserves_only_allowed_keys():
    sanitized, token = contract.sanitize_plan(_plan())
    assert token == "signed-token"
    assert "plan_token" not in sanitized
    assert "signed-token" not in json.dumps(sanitized)
    contract.assert_no_forbidden_artifact_keys(sanitized)


def test_schema_drift_and_secret_material_fail_closed():
    bad = _plan()
    bad["debug"] = "unsafe"
    with pytest.raises(contract.WorkflowError, match="schema is not reviewed"):
        contract.load_result(json.dumps(bad), expected_mode="plan")
    with pytest.raises(contract.WorkflowError, match="forbidden secret"):
        contract.assert_no_forbidden_artifact_keys({"state": {"password_hash": "no"}})
    contract.assert_no_forbidden_artifact_keys(
        {"credential_matches": True, "can_change_password": True}
    )


def test_verification_requires_real_staff_proofs_not_just_shape():
    value = _verify()
    contract.validate_result_semantics(value, expected_mode="verify", remote_status=0)
    value["credential_matches"] = False
    with pytest.raises(contract.WorkflowError, match="proof is incomplete"):
        contract.validate_result_semantics(value, expected_mode="verify", remote_status=0)


def test_blocked_verification_preserves_only_safe_reason_codes():
    value = _verify()
    value.update(
        ready=False,
        blockers=["staff_credential_unproved"],
        credential_matches=False,
        auth_source_staff_password=False,
        legacy_jwt_rejected=False,
        legacy_google_auth_rejected=False,
    )
    contract.validate_result_semantics(value, expected_mode="verify", remote_status=2)
    sanitized, _ = contract.sanitize_verify(value)
    assert sanitized["blockers"] == ["staff_credential_unproved"]


def test_legacy_rollback_verification_is_allowed_only_with_env_credential_proof():
    value = _verify(mode="legacy")
    value.update(
        can_change_password=False,
        auth_source_staff_password=False,
        legacy_jwt_rejected=False,
        legacy_google_auth_rejected=False,
    )
    contract.validate_result_semantics(value, expected_mode="verify", remote_status=0)
    value["credential_matches"] = False
    with pytest.raises(contract.WorkflowError, match="proof is incomplete"):
        contract.validate_result_semantics(value, expected_mode="verify", remote_status=0)


def test_initial_legacy_verification_allows_no_bound_staff_identity():
    value = _verify(mode="legacy")
    value.update(
        staff_user_id=None,
        membership_id=None,
        can_change_password=False,
        auth_source_staff_password=False,
        legacy_jwt_rejected=False,
        legacy_google_auth_rejected=False,
    )
    contract.validate_result_semantics(
        value,
        expected_mode="verify",
        remote_status=0,
    )
    value["membership_id"] = 2
    with pytest.raises(contract.WorkflowError, match="identity proof is invalid"):
        contract.validate_result_semantics(
            value,
            expected_mode="verify",
            remote_status=0,
        )


def test_runtime_binding_is_compared_in_memory_and_never_survives_sanitization():
    sanitized, binding = contract.sanitize_verify(_verify())
    assert binding == "b" * 64
    assert "runtime_binding" not in sanitized
    contract.assert_no_forbidden_artifact_keys(sanitized)
