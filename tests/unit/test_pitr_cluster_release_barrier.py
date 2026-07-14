import pytest

from scripts.ha.pitr_cluster_migration import migrate_cluster
from tests.unit.test_pitr_cluster_migration import (
    ENV_TEXT,
    TXID,
    FakeOperations,
    _context,
    _unused_runner,
)


def test_role_swap_mismatch_aborts_barrier_before_any_fresh_apply(tmp_path):
    operations = FakeOperations()
    operations.release_failure = ("inspect", "mvn-api")

    with pytest.raises(RuntimeError, match="simulated release failure"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert [event for event in operations.events if event[0] == "release"] == [
        ("release", "inspect", "zakup", TXID),
        ("release", "inspect", "mvn-api", TXID),
    ]


def test_matching_existing_release_is_applied_before_fresh_peer(tmp_path):
    operations = FakeOperations()
    operations.release_results[("inspect", "mvn-api")] = "matching-active"
    operations.release_results[("apply", "mvn-api")] = "resumed"

    migrate_cluster(
        context=_context(tmp_path),
        env_text=ENV_TEXT,
        transaction_id=TXID,
        runner=_unused_runner,
        dependencies=operations.dependencies(),
    )

    release_events = [event for event in operations.events if event[0] == "release"]
    assert release_events[:4] == [
        ("release", "inspect", "zakup", TXID),
        ("release", "inspect", "mvn-api", TXID),
        ("release", "apply", "mvn-api", TXID),
        ("release", "apply", "zakup", TXID),
    ]
    for alias in ("mvn-api", "zakup"):
        payloads = [
            payload
            for action, node_alias, payload in operations.release_payloads
            if node_alias == alias and action in {"inspect", "apply"}
        ]
        assert payloads == [f"pinned:{alias}", f"pinned:{alias}"]
