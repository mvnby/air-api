import base64
import hashlib
import json

import pytest

from scripts.ha.pitr_cluster_migration import migrate_cluster
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES
from scripts.ha.pitr_remote_execution import prepare_host_release_bundles
from scripts.ha.pitr_target_compose import validate_target_compose_bundles
from tests.unit.test_pitr_cluster_migration import (
    ENV_TEXT,
    TXID,
    FakeOperations,
    _context,
    _unused_runner,
)


def _compose(
    *,
    enabled='"false"',
    allow_all='"false"',
    missing_service=None,
    worker_image="'${BACKEND_IMAGE:?set immutable BACKEND_IMAGE in .env}'",
):
    image = "'${BACKEND_IMAGE:?set immutable BACKEND_IMAGE in .env}'"
    services = {
        "app": f"  app:\n    image: {image}\n",
        "app-blue": f"  app-blue:\n    image: {image}\n",
        "app-green": f"  app-green:\n    image: {image}\n",
        "communications-worker": (
            "  communications-worker:\n"
            f"    image: {worker_image}\n"
            "    depends_on:\n"
            "      db:\n"
            "        condition: service_healthy\n"
            "    env_file:\n"
            "      - .env\n"
            "      - .ha-app-role.env\n"
            "    environment:\n"
            f"      COMMUNICATIONS_WORKER_ENABLED: {enabled}\n"
            f"      COMMUNICATIONS_WORKER_ALLOW_ALL_MODE: {allow_all}\n"
            "    command: python -m services.communications.runtime\n"
        ),
    }
    return (
        "services:\n"
        + "  db: {}\n"
        + "".join(
            value for name, value in services.items() if name != missing_service
        )
    ).encode("utf-8")


def _bundle(node, compose):
    compose_path = f"{node.project_dir}/{node.compose_file}"
    descriptor = {
        "content": base64.b64encode(compose).decode("ascii"),
        "mode": 0o644,
        "path": compose_path,
        "sha256": hashlib.sha256(compose).hexdigest(),
    }
    body = {
        "files": [descriptor],
        "project_dir": node.project_dir,
        "version": 1,
    }
    bundle = {
        **body,
        "release_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest(),
    }
    return json.dumps(bundle, sort_keys=True, separators=(",", ":"))


def _bundles(first, second):
    return {
        PATRONI_NODES[0].project_dir: _bundle(PATRONI_NODES[0], first),
        PATRONI_NODES[1].project_dir: _bundle(PATRONI_NODES[1], second),
    }


@pytest.mark.parametrize(
    ("enabled", "allow_all", "profile"),
    [
        ('"false"', '"false"', "dormant"),
        ('"true"', '"false"', "canary"),
        ('"true"', '"true"', "active"),
    ],
)
def test_target_compose_accepts_only_closed_profiles(
    enabled,
    allow_all,
    profile,
):
    compose = _compose(enabled=enabled, allow_all=allow_all)
    assert validate_target_compose_bundles(
        PATRONI_NODES,
        _bundles(compose, compose),
    ) == profile


@pytest.mark.parametrize(
    ("enabled", "allow_all"),
    [
        ('"false"', '"true"'),
        ('"TRUE"', '"false"'),
        ('"false"', '"FALSE"'),
        ("true", "false"),
        ("false", "false"),
    ],
)
def test_target_compose_rejects_invalid_uppercase_or_boolean_gates(
    enabled,
    allow_all,
):
    compose = _compose(enabled=enabled, allow_all=allow_all)
    with pytest.raises(RuntimeError, match="profile is not reviewed"):
        validate_target_compose_bundles(
            PATRONI_NODES,
            _bundles(compose, compose),
        )


@pytest.mark.parametrize(
    "missing_service",
    ["app", "app-blue", "app-green", "communications-worker"],
)
def test_target_compose_rejects_missing_reviewed_service(missing_service):
    compose = _compose(missing_service=missing_service)
    with pytest.raises(RuntimeError):
        validate_target_compose_bundles(
            PATRONI_NODES,
            _bundles(compose, compose),
        )


def test_target_compose_rejects_api_worker_image_mismatch():
    compose = _compose(worker_image="'different-image'")
    with pytest.raises(RuntimeError, match="image mismatch"):
        validate_target_compose_bundles(
            PATRONI_NODES,
            _bundles(compose, compose),
        )


def test_target_compose_rejects_cross_node_profile_mismatch():
    dormant = _compose()
    active = _compose(enabled='"true"', allow_all='"true"')
    with pytest.raises(RuntimeError, match="differ across cluster nodes"):
        validate_target_compose_bundles(
            PATRONI_NODES,
            _bundles(dormant, active),
        )


def test_tracked_production_compose_sources_share_same_reviewed_profile():
    bundles = prepare_host_release_bundles(PATRONI_NODES)
    assert validate_target_compose_bundles(PATRONI_NODES, bundles) in {
        "dormant",
        "canary",
        "active",
    }


def test_target_compose_rejection_precedes_every_remote_mutation(tmp_path):
    operations = FakeOperations()
    operations.target_compose_failure = True

    with pytest.raises(RuntimeError, match="target Compose failure"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert operations.events == [("topology",)]
