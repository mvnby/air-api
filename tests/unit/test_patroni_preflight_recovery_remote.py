import base64
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import patroni_preflight_recovery_remote as remote
from scripts.ha.patroni_rollout_schema import NODE_CONTRACTS
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES


MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "deploy/ha/patroni/incidents/1053e46eb933ebaaffed042ac1b73170.json"
)


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="ascii"))


def _remote_namespace():
    definitions = remote.REMOTE_EXECUTOR.rsplit("\ntry:\n    main()", 1)[0]
    namespace = {"__name__": "patroni_preflight_recovery_remote_test"}
    exec(compile(definitions, "<preflight-recovery-remote>", "exec"), namespace)
    return namespace


def test_remote_executor_compiles_and_accepts_only_exact_reviewed_payloads():
    compile(remote.REMOTE_EXECUTOR, "<preflight-recovery-remote>", "exec")
    namespace = _remote_namespace()
    manifest = _manifest()
    node = PATRONI_NODES[0]
    payload = json.loads(
        remote.build_payload(
            manifest=manifest,
            node=node,
            recovery_deploy_sha="a" * 40,
        )
    )

    namespace["validate_payload"](
        payload, node.alias, str(manifest["transaction_id"])
    )
    namespace["load_transformer"](payload, node.alias)

    extra = {**payload, "unreviewed": True}
    with pytest.raises(RuntimeError, match="payload fields are not exact"):
        namespace["validate_payload"](
            extra, node.alias, str(manifest["transaction_id"])
        )

    drifted = dict(payload)
    drifted["recovery_deploy_sha"] = "a" * 39
    with pytest.raises(RuntimeError, match="generation identity is invalid"):
        namespace["validate_payload"](
            drifted, node.alias, str(manifest["transaction_id"])
        )


@pytest.mark.parametrize(
    "command",
    [
        ["docker", "compose", "up", "-d", "db"],
        ["docker", "compose", "config", "up", "-d", "db"],
        ["docker", "pull", "patroni:latest"],
        ["docker", "exec", "db", "patronictl", "edit-config"],
        ["systemctl", "start", "mvn-postgres-wal-upload.service"],
        ["curl", "-X", "PATCH", "http://127.0.0.1:8008/config"],
        ["rm", "-f", "/opt/air-api/.env"],
    ],
)
def test_remote_executor_rejects_runtime_database_and_dcs_mutation_commands(
    command, monkeypatch
):
    namespace = _remote_namespace()
    monkeypatch.setattr(
        namespace["subprocess"],
        "run",
        lambda *_args, **_kwargs: pytest.fail("forbidden command reached subprocess"),
    )

    with pytest.raises(RuntimeError, match="outside the read-only allowlist"):
        namespace["run"](command)


def test_remote_executor_source_contains_no_reviewed_runtime_mutation_primitive():
    forbidden = (
        '"up"',
        '"pull"',
        "patronictl",
        "edit-config",
        "pg_switch_wal",
        "set_env_image",
        '["systemctl", "start"',
        '["systemctl", "restart"',
        '["systemctl", "enable"',
    )

    assert not any(value in remote.REMOTE_EXECUTOR for value in forbidden)


def _root_owned_lstat(real_lstat, path, root):
    metadata = real_lstat(path)
    return SimpleNamespace(
        st_mode=metadata.st_mode,
        st_uid=root,
        st_gid=root,
        st_nlink=metadata.st_nlink,
        st_size=metadata.st_size,
    )


def test_remote_executor_safely_creates_a_missing_receipt_root(tmp_path, monkeypatch):
    namespace = _remote_namespace()
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    receipt_root = state_root / "transactions-receipts"
    namespace["STATE_ROOT"] = str(state_root)
    namespace["RECEIPT_ROOT"] = str(receipt_root)
    namespace["ROOT"] = os.geteuid()
    real_lstat = os.lstat
    monkeypatch.setattr(
        namespace["os"],
        "lstat",
        lambda path: _root_owned_lstat(real_lstat, path, namespace["ROOT"]),
    )

    namespace["ensure_receipt_root"]()
    namespace["ensure_receipt_root"]()

    assert receipt_root.is_dir()
    assert receipt_root.stat().st_mode & 0o777 == 0o700


def test_remote_executor_rejects_an_unsafe_existing_receipt_root(tmp_path, monkeypatch):
    namespace = _remote_namespace()
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    receipt_root = state_root / "transactions-receipts"
    receipt_root.mkdir(mode=0o755)
    namespace["STATE_ROOT"] = str(state_root)
    namespace["RECEIPT_ROOT"] = str(receipt_root)
    namespace["ROOT"] = os.geteuid()
    real_lstat = os.lstat
    monkeypatch.setattr(
        namespace["os"],
        "lstat",
        lambda path: _root_owned_lstat(real_lstat, path, namespace["ROOT"]),
    )

    with pytest.raises(RuntimeError, match="unsafe incident recovery directory"):
        namespace["ensure_receipt_root"]()


def _recovery_compose_case(node):
    namespace = _remote_namespace()
    contract = NODE_CONTRACTS[node.alias]
    project = str(contract["project_dir"])
    image = "ghcr.io/mvnby/air-api/patroni@sha256:" + "1" * 64
    source = b"reviewed compose bytes"
    contract_digest = "2" * 64
    config = {
        "name": contract["compose_project"],
        "services": {
            "db": {
                "image": image,
                "volumes": [
                    {
                        "type": "volume",
                        "source": "postgres_data",
                        "target": "/var/lib/postgresql/data",
                    }
                ],
            }
        },
        "volumes": {
            "postgres_data": {
                "external": True,
                "name": contract["data_volume"],
            }
        },
    }
    namespace["stable_file"] = lambda *_args, **_kwargs: source

    def fake_run(args, **_kwargs):
        if args[:3] == ["/usr/bin/python3", "-I", "-c"]:
            return contract_digest
        return json.dumps(config)

    namespace["run"] = fake_run
    payload = {
        "compose_contract_sha256": contract_digest,
        "compose_source_sha256": hashlib.sha256(source).hexdigest(),
        "contract_helper_b64": base64.b64encode(b"pass").decode("ascii"),
        "current_image": image,
    }
    arguments = (
        project,
        str(contract["compose_file"]),
        str(contract["compose_project"]),
        str(contract["data_volume"]),
        payload,
    )
    return namespace, config, arguments


def _mutate_pgdata_identity(config, mutation):
    mount = config["services"]["db"]["volumes"][0]
    if mutation == "duplicate-pgdata":
        config["services"]["db"]["volumes"].append(copy.deepcopy(mount))
    elif mutation == "bind-pgdata":
        mount["type"] = "bind"
    elif mutation == "top-name":
        config["volumes"]["postgres_data"]["name"] = "wrong-postgres-data"
    elif mutation == "external-false":
        config["volumes"]["postgres_data"]["external"] = False
    elif mutation == "wrong-source":
        mount["source"] = config["volumes"]["postgres_data"]["name"]
    else:
        raise AssertionError(f"unknown mutation: {mutation}")


@pytest.mark.parametrize("node", PATRONI_NODES, ids=lambda node: node.alias)
def test_recovery_compose_proof_accepts_exact_logical_pgdata_identity(node):
    namespace, _config, arguments = _recovery_compose_case(node)

    namespace["prove_compose"](*arguments)


@pytest.mark.parametrize("node", PATRONI_NODES, ids=lambda node: node.alias)
@pytest.mark.parametrize(
    "mutation",
    (
        "duplicate-pgdata",
        "bind-pgdata",
        "top-name",
        "external-false",
        "wrong-source",
    ),
)
def test_recovery_compose_proof_rejects_pgdata_identity_drift(node, mutation):
    namespace, config, arguments = _recovery_compose_case(node)
    _mutate_pgdata_identity(config, mutation)

    with pytest.raises(RuntimeError, match="resolved Compose identity drifted"):
        namespace["prove_compose"](*arguments)
