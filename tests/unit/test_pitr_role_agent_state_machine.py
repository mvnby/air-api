import ast
import os

import pytest

from scripts.ha import (
    pitr_remote_executors,
    pitr_role_agent_process_attestation,
)


def test_role_agent_process_attestation_is_a_composed_source_module():
    source = pitr_role_agent_process_attestation.REMOTE_ROLE_AGENT_PROCESS_ATTESTATION

    ast.parse(source)
    assert source.strip() in pitr_remote_executors.REMOTE_ROLE_AGENT_EXECUTOR


def test_role_agent_executor_keeps_quiesce_fenced_and_resume_fail_closed():
    source = pitr_remote_executors.REMOTE_ROLE_AGENT_EXECUTOR

    assert 'require_fence(project_dir, transaction_id, allow_finalized=False)' in source
    assert '["/usr/bin/systemctl", "disable", ROLE_AGENT_UNIT]' in source
    assert 'unit_state("is-active") != "inactive"' in source
    assert 'unit_state("is-enabled") != "disabled"' in source
    assert "role_agent._fence_lost_primary(config)" in source
    assert "guard.cancel_project_operations(project_dir)" in source
    assert "execute_attested_module" in source
    assert "sources[OPERATION_GUARD_PATH]" in source
    assert '["/usr/bin/systemctl", "restart", ROLE_AGENT_UNIT]' in source
    assert "snapshot_role_generation(manifest)" in source
    assert "new_start_ticks <= old_start_ticks" in source
    assert "process_start_ns" not in source
    assert 'read_proc_file("/proc/stat"' not in source
    assert "role-agent systemd state is not replay-convergent" in source
    assert source.index(
        '["/usr/bin/systemctl", "stop", ROLE_AGENT_UNIT]'
    ) < source.index('["/usr/bin/systemctl", "disable", ROLE_AGENT_UNIT]')
    assert "open_deploy_lock_bounded(project_dir)" in source
    assert "wait_for_convergence(role_agent, config, expected_role)" in source
    assert '"reset-failed"' not in source


def test_stop_disable_does_not_reset_an_unloaded_inactive_unit():
    namespace = _role_executor_namespace()
    events = []
    state = {"active": "active", "enabled": "enabled"}

    def checked(args, **_kwargs):
        action = args[1]
        events.append(action)
        if action == "stop":
            state["active"] = "inactive"
        elif action == "disable":
            state["enabled"] = "disabled"
        else:
            raise AssertionError(f"unexpected systemctl action: {action}")
        return ""

    namespace["checked"] = checked
    namespace["unit_state"] = lambda kind: state[
        "active" if kind == "is-active" else "enabled"
    ]

    namespace["stop_disable_role_agent"]()

    assert events == ["stop", "disable"]
    assert state == {"active": "inactive", "enabled": "disabled"}


def _role_executor_namespace():
    source = pitr_remote_executors.REMOTE_ROLE_AGENT_EXECUTOR
    prefix = source.rsplit("raise SystemExit(main())", 1)[0]
    namespace = {"__name__": "pitr_role_executor_behavior"}
    exec(compile(prefix, "<pitr-role-executor>", "exec"), namespace)
    return namespace


def test_record_drain_waits_then_reaps_and_cancels_via_attested_guard():
    namespace = _role_executor_namespace()
    events = []
    record = type("Record", (), {"operation_id": "0" * 32})()

    class Guard:
        records = [record]

        def list_records(self, **_kwargs):
            events.append("list")
            return list(self.records)

        def reconcile_project_operations(self, _project):
            events.append("reconcile")
            if self.records:
                raise RuntimeError("active")

        def cancel_project_operations(self, _project):
            events.append("cancel")
            self.records.clear()

    namespace["drain_operations"](
        "/opt/air-api", "0" * 32, Guard(), wait_seconds=0
    )

    assert events == [
        "list", "list", "reconcile", "cancel", "reconcile", "list"
    ]


def test_record_drain_never_reaps_or_cancels_a_foreign_transaction():
    namespace = _role_executor_namespace()
    events = []
    record = type("Record", (), {"operation_id": "f" * 32})()

    class Guard:
        def list_records(self, **_kwargs):
            events.append("list")
            return [record]

        def reconcile_project_operations(self, _project):
            events.append("reconcile")

        def cancel_project_operations(self, _project):
            events.append("cancel")

    with pytest.raises(RuntimeError, match="foreign PITR operation"):
        namespace["drain_operations"](
            "/opt/air-api", "0" * 32, Guard(), wait_seconds=0
        )

    assert events == ["list", "list"]


def test_primary_quiesce_refreshes_under_fence_before_disabling_agent():
    namespace = _role_executor_namespace()
    events = []
    state = {"active": "active", "enabled": "enabled"}

    class Guard:
        def reconcile_project_operations(self, _project):
            events.append("reconcile-under-lock")

    class RoleAgent:
        def _fence_lost_primary(self, _config):
            events.append("fence-runtime")

    contract = (
        {"asset": "digest"},
        {"HA_PROJECT_DIR": "/opt/air-api"},
        Guard(),
        RoleAgent(),
        object(),
    )
    namespace["attest_contract"] = lambda *_args: (
        events.append("attest") or contract
    )
    namespace["drain_operations"] = lambda *_args, **_kwargs: events.append(
        "drain"
    )
    namespace["require_fence"] = lambda *_args, **_kwargs: (
        events.append("fence-proof") or "maintenance"
    )
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)
    namespace["open_deploy_lock_bounded"] = lambda *_args, **_kwargs: os.open(
        os.devnull, os.O_RDONLY
    )
    def refresh(*_args, **kwargs):
        assert kwargs == {"expected_enabled": "enabled"}
        events.append("refresh")
        return "generation"

    namespace["refresh_live_process"] = refresh
    namespace["prove_safe_state"] = lambda *_args, **kwargs: events.append(
        "safe-" + kwargs["required"]
    )
    namespace["unit_state"] = lambda kind: state[
        "active" if kind == "is-active" else "enabled"
    ]

    def checked(args, **_kwargs):
        action = args[1]
        events.append(action)
        if action == "disable":
            state["enabled"] = "disabled"
        elif action == "stop":
            state["active"] = "inactive"
        return ""

    namespace["checked"] = checked
    namespace["quiesce"](
        "quiesce-fenced", "/opt/air-api", "0" * 32, "manifest"
    )

    assert events.index("fence-runtime") < events.index("disable")
    assert events.index("safe-fenced") < events.index("disable")
    assert events.index("safe-fenced") < events.index("refresh")
    assert events.index("refresh") < events.index("disable")
    assert "enable" not in events
    assert "start" not in events
    assert events.count("fence-runtime") == 2
    assert events.count("safe-fenced") == 3
    assert events.count("attest") == 2
    assert events.count("drain") == 2


@pytest.mark.parametrize(
    ("active_state", "enabled_state"),
    [("active", "disabled"), ("inactive", "enabled")],
)
def test_quiesce_converges_owned_mixed_systemd_crash_state(
    active_state, enabled_state
):
    namespace = _role_executor_namespace()
    events = []
    state = {"active": active_state, "enabled": enabled_state}

    class RoleAgent:
        def _fence_lost_primary(self, _config):
            events.append("fence-runtime")

    contract = ({}, {}, object(), RoleAgent(), object())
    namespace["attest_contract"] = lambda *_args: contract
    namespace["drain_operations"] = lambda *_args, **_kwargs: None
    namespace["require_fence"] = lambda *_args, **_kwargs: "maintenance"
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)
    namespace["open_deploy_lock_bounded"] = lambda *_args, **_kwargs: os.open(
        os.devnull, os.O_RDONLY
    )
    namespace["unit_state"] = lambda kind: state[
        "active" if kind == "is-active" else "enabled"
    ]
    namespace["prove_safe_state"] = lambda *_args, **kwargs: events.append(
        "safe-" + kwargs["required"]
    )

    def refresh(*_args, **kwargs):
        assert kwargs == {"expected_enabled": "disabled"}
        events.append("refresh")
        return "generation"

    namespace["refresh_live_process"] = refresh

    def checked(args, **_kwargs):
        action = args[1]
        events.append(action)
        if action == "stop":
            state["active"] = "inactive"
        elif action == "disable":
            state["enabled"] = "disabled"
        return ""

    namespace["checked"] = checked
    namespace["quiesce"](
        "quiesce-fenced", "/opt/air-api", "0" * 32, "manifest"
    )

    assert state == {"active": "inactive", "enabled": "disabled"}
    assert events.index("stop") < events.index("disable")
    assert ("refresh" in events) is (active_state == "active")


def test_quiesce_replays_after_crash_between_stop_and_disable():
    namespace = _role_executor_namespace()
    state = {"active": "active", "enabled": "enabled"}
    crash = {"disable": True}

    class RoleAgent:
        def _fence_lost_primary(self, _config):
            pass

    contract = ({}, {}, object(), RoleAgent(), object())
    namespace["attest_contract"] = lambda *_args: contract
    namespace["drain_operations"] = lambda *_args, **_kwargs: None
    namespace["require_fence"] = lambda *_args, **_kwargs: "maintenance"
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)
    namespace["open_deploy_lock_bounded"] = lambda *_args, **_kwargs: os.open(
        os.devnull, os.O_RDONLY
    )
    namespace["unit_state"] = lambda kind: state[
        "active" if kind == "is-active" else "enabled"
    ]
    namespace["prove_safe_state"] = lambda *_args, **_kwargs: None
    namespace["refresh_live_process"] = lambda *_args, **_kwargs: "generation"

    def checked(args, **_kwargs):
        action = args[1]
        if action == "stop":
            state["active"] = "inactive"
        elif action == "disable":
            if crash["disable"]:
                raise RuntimeError("simulated crash before disable")
            state["enabled"] = "disabled"
        return ""

    namespace["checked"] = checked
    with pytest.raises(RuntimeError, match="simulated crash"):
        namespace["quiesce"](
            "quiesce-fenced", "/opt/air-api", "0" * 32, "manifest"
        )
    assert state == {"active": "inactive", "enabled": "enabled"}

    crash["disable"] = False
    namespace["quiesce"](
        "quiesce-fenced", "/opt/air-api", "0" * 32, "manifest"
    )
    assert state == {"active": "inactive", "enabled": "disabled"}


def _refresh_behavior_namespace(*, snapshots=("generation", "generation")):
    namespace = _role_executor_namespace()
    state = {"active": "active", "enabled": "enabled"}
    events = []
    identities = iter((("41", 100), ("42", 101)))
    generations = iter(snapshots)
    namespace["snapshot_role_generation"] = lambda _manifest: next(generations)
    namespace["attest_live_process"] = lambda _expected: next(identities)
    namespace["attest_loaded_unit"] = lambda: events.append("unit-proof")
    namespace["unit_state"] = lambda kind: state[
        "active" if kind == "is-active" else "enabled"
    ]
    namespace["checked"] = lambda args, **_kwargs: events.append(args[1])
    return namespace, state, events


def test_controlled_refresh_requires_unchanged_generation_and_newer_start_ticks():
    namespace, _state, events = _refresh_behavior_namespace()

    namespace["refresh_live_process"]({}, {})

    assert events == ["restart", "unit-proof"]


def test_controlled_refresh_rejects_metadata_change_across_restart():
    namespace, _state, _events = _refresh_behavior_namespace(
        snapshots=("before", "after")
    )

    with pytest.raises(RuntimeError, match="generation changed"):
        namespace["refresh_live_process"]({}, {})


def test_controlled_refresh_rejects_nonadvancing_process_start_ticks():
    namespace, _state, _events = _refresh_behavior_namespace()
    identities = iter((("41", 100), ("42", 100)))
    namespace["attest_live_process"] = lambda _expected: next(identities)

    with pytest.raises(RuntimeError, match="did not advance process identity"):
        namespace["refresh_live_process"]({}, {})


@pytest.mark.parametrize(
    ("state_key", "state_value", "message"),
    [
        ("active", "inactive", "is not active"),
        ("enabled", "disabled", "enablement differs"),
    ],
)
def test_controlled_refresh_rejects_systemd_state_mismatch(
    state_key, state_value, message
):
    namespace, state, _events = _refresh_behavior_namespace()
    state[state_key] = state_value

    with pytest.raises(RuntimeError, match=message):
        namespace["refresh_live_process"]({}, {})


def test_started_generation_rejects_metadata_change_across_start():
    namespace = _role_executor_namespace()
    namespace["unit_state"] = lambda kind: (
        "active" if kind == "is-active" else "enabled"
    )
    namespace["attest_loaded_unit"] = lambda: None
    namespace["attest_live_process"] = lambda _expected: ("42", 101)
    namespace["snapshot_role_generation"] = lambda _manifest: "after"

    with pytest.raises(RuntimeError, match="generation changed across maintenance resume"):
        namespace["prove_live_generation"](
            {}, {}, "before", "maintenance resume"
        )


def test_quiesce_foreign_record_race_fails_before_disabling_agent():
    namespace = _role_executor_namespace()
    events = []
    contract = ({}, {}, object(), object(), object())
    namespace["attest_contract"] = lambda *_args: contract
    namespace["require_fence"] = lambda *_args, **_kwargs: "maintenance"
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)
    namespace["open_deploy_lock_bounded"] = lambda *_args, **_kwargs: os.open(
        os.devnull, os.O_RDONLY
    )
    calls = 0

    def drain(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        events.append("drain")
        if calls == 2:
            raise RuntimeError("foreign PITR operation records remain")

    namespace["drain_operations"] = drain
    namespace["checked"] = lambda *_args, **_kwargs: events.append("systemctl")

    with pytest.raises(RuntimeError, match="foreign PITR operation"):
        namespace["quiesce"](
            "quiesce-standby", "/opt/air-api", "0" * 32, "manifest"
        )

    assert events == ["drain", "drain"]


def test_resume_behavior_holds_lock_for_start_then_reacquires_for_final_proof():
    namespace = _role_executor_namespace()
    events = []
    state = {"active": "inactive", "enabled": "disabled"}

    class Guard:
        def reconcile_project_operations(self, _project):
            events.append("reconcile-under-lock")

    contract = (
        {"asset": "digest"},
        {"HA_PROJECT_DIR": "/opt/air-api"},
        Guard(),
        object(),
        object(),
    )
    namespace["attest_contract"] = lambda *_args: (
        events.append("attest") or contract
    )
    namespace["drain_operations"] = lambda *_args, **_kwargs: events.append(
        "drain"
    )
    namespace["require_fence"] = lambda *_args, **_kwargs: (
        events.append("fence-proof") or "maintenance"
    )
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)

    def deploy_lock(*_args, **_kwargs):
        events.append("deploy-lock")
        return os.open(os.devnull, os.O_RDONLY)

    namespace["open_deploy_lock_bounded"] = deploy_lock
    namespace["attest_live_process"] = lambda *_args: events.append("live-proof")
    namespace["attest_loaded_unit"] = lambda: events.append("unit-proof")
    namespace["snapshot_role_generation"] = lambda _manifest: "generation"
    namespace["wait_for_convergence"] = lambda *_args: events.append("converged")
    namespace["prove_safe_state"] = lambda *_args, **_kwargs: events.append("safe-live")
    namespace["unit_state"] = lambda kind: state[
        "active" if kind == "is-active" else "enabled"
    ]

    def checked(args, **_kwargs):
        action = args[1]
        events.append(action)
        if action == "enable":
            state["enabled"] = "enabled"
        elif action == "start":
            state["active"] = "active"
        return ""

    namespace["checked"] = checked
    namespace["resume"](
        "/opt/air-api", "0" * 32, "manifest", "primary"
    )

    assert events.count("deploy-lock") == 2
    assert events.index("start") < events.index("converged")
    assert events.index("converged") < events.index("safe-live")
    assert events.count("attest") == 3


def test_resume_active_enabled_is_idempotent_after_bundle_finalize():
    namespace = _role_executor_namespace()
    events = []

    contract = (
        {"asset": "digest"},
        {"HA_PROJECT_DIR": "/opt/air-api"},
        object(),
        object(),
        object(),
    )
    namespace["attest_contract"] = lambda *_args: (
        events.append("attest") or contract
    )
    namespace["drain_operations"] = lambda *_args, **_kwargs: events.append(
        "drain"
    )
    namespace["require_fence"] = lambda *_args, **_kwargs: (
        events.append("fence-proof") or "finalized"
    )
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)

    def deploy_lock(*_args, **_kwargs):
        events.append("deploy-lock")
        return os.open(os.devnull, os.O_RDONLY)

    namespace["open_deploy_lock_bounded"] = deploy_lock
    namespace["unit_state"] = lambda kind: (
        "active" if kind == "is-active" else "enabled"
    )
    namespace["prove_safe_state"] = lambda *_args, **_kwargs: events.append(
        "safe-live"
    )
    namespace["refresh_live_process"] = lambda *_args: (
        events.append("refresh") or "generation"
    )
    namespace["wait_for_convergence"] = lambda *_args: events.append("converged")
    namespace["prove_live_generation"] = lambda *_args: events.append(
        "generation-proof"
    )
    namespace["checked"] = lambda *_args, **_kwargs: events.append("systemctl")

    namespace["resume"](
        "/opt/air-api", "0" * 32, "manifest", "primary"
    )

    assert events.count("deploy-lock") == 2
    assert events.count("safe-live") == 3
    assert events.index("refresh") < events.index("converged")
    assert events.index("converged") < events.index("generation-proof")
    assert "systemctl" not in events


@pytest.mark.parametrize(
    ("active_state", "enabled_state"),
    [("active", "disabled"), ("inactive", "enabled")],
)
def test_resume_converges_owned_mixed_active_enabled_crash_state(
    active_state, enabled_state
):
    namespace = _role_executor_namespace()
    events = []
    state = {"active": active_state, "enabled": enabled_state}

    class RoleAgent:
        def _fence_lost_primary(self, _config):
            events.append("fence-runtime")

    contract = ({}, {}, object(), RoleAgent(), object())
    namespace["attest_contract"] = lambda *_args: contract
    namespace["drain_operations"] = lambda *_args, **_kwargs: None
    namespace["require_fence"] = lambda *_args, **_kwargs: "maintenance"
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)
    namespace["open_deploy_lock_bounded"] = lambda *_args, **_kwargs: os.open(
        os.devnull, os.O_RDONLY
    )
    namespace["unit_state"] = lambda kind: (
        state["active" if kind == "is-active" else "enabled"]
    )
    namespace["prove_safe_state"] = lambda *_args, **kwargs: events.append(
        "safe-" + kwargs["required"]
    )
    namespace["snapshot_role_generation"] = lambda _manifest: "generation"
    namespace["prove_live_generation"] = lambda *_args: events.append(
        "generation-proof"
    )
    namespace["wait_for_convergence"] = lambda *_args: events.append("converged")

    def refresh(*_args, **kwargs):
        assert kwargs == {"expected_enabled": "disabled"}
        events.append("refresh")
        return "generation"

    namespace["refresh_live_process"] = refresh

    def checked(args, **_kwargs):
        action = args[1]
        events.append(action)
        if action == "stop":
            state["active"] = "inactive"
        elif action == "disable":
            state["enabled"] = "disabled"
        elif action == "enable":
            state["enabled"] = "enabled"
        elif action == "start":
            state["active"] = "active"
        return ""

    namespace["checked"] = checked

    namespace["resume"](
        "/opt/air-api", "0" * 32, "manifest", "standby"
    )

    assert state == {"active": "active", "enabled": "enabled"}
    assert events.index("stop") < events.index("disable")
    assert events.index("disable") < events.index("enable")
    assert events.index("enable") < events.index("start")
    assert ("refresh" in events) is (active_state == "active")


def test_resume_replays_after_crash_between_enable_and_start():
    namespace = _role_executor_namespace()
    state = {"active": "inactive", "enabled": "disabled"}
    crash = {"start": True}

    class RoleAgent:
        def _fence_lost_primary(self, _config):
            pass

    contract = ({}, {}, object(), RoleAgent(), object())
    namespace["attest_contract"] = lambda *_args: contract
    namespace["drain_operations"] = lambda *_args, **_kwargs: None
    namespace["require_fence"] = lambda *_args, **_kwargs: "maintenance"
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)
    namespace["open_deploy_lock_bounded"] = lambda *_args, **_kwargs: os.open(
        os.devnull, os.O_RDONLY
    )
    namespace["unit_state"] = lambda kind: state[
        "active" if kind == "is-active" else "enabled"
    ]
    namespace["prove_safe_state"] = lambda *_args, **_kwargs: None
    namespace["snapshot_role_generation"] = lambda _manifest: "generation"
    namespace["prove_live_generation"] = lambda *_args: None
    namespace["wait_for_convergence"] = lambda *_args: None
    namespace["refresh_live_process"] = lambda *_args, **_kwargs: pytest.fail(
        "inactive+enabled replay must normalize without a live refresh"
    )

    def checked(args, **_kwargs):
        action = args[1]
        if action == "stop":
            state["active"] = "inactive"
        elif action == "disable":
            state["enabled"] = "disabled"
        elif action == "enable":
            state["enabled"] = "enabled"
        elif action == "start":
            if crash["start"]:
                raise RuntimeError("simulated crash before start")
            state["active"] = "active"
        return ""

    namespace["checked"] = checked
    with pytest.raises(RuntimeError, match="simulated crash"):
        namespace["resume"](
            "/opt/air-api", "0" * 32, "manifest", "standby"
        )
    assert state == {"active": "inactive", "enabled": "enabled"}

    crash["start"] = False
    namespace["resume"](
        "/opt/air-api", "0" * 32, "manifest", "standby"
    )
    assert state == {"active": "active", "enabled": "enabled"}


def test_primary_convergence_never_accepts_unavailable_local_role_proof():
    namespace = _role_executor_namespace()

    class RoleAgent:
        def _fetch_configured_patroni_role(self, _config):
            raise RuntimeError("local Patroni proof unavailable")

    with pytest.raises(RuntimeError, match="local Patroni proof unavailable"):
        namespace["prove_safe_state"](
            RoleAgent(),
            object(),
            required="live",
            expected_role="primary",
        )
