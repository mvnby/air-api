import hashlib
import json
from datetime import datetime, timezone

import pytest

from tests.unit.postgres_pitr_restore_test_support import (
    FakeClient,
    FakeConfig,
    OTHER_SYSTEM_IDENTIFIER,
    SYSTEM_IDENTIFIER,
    _manifest_key,
    _manifest_record,
    _minimal_payload,
    pitr_restore,
)


def test_load_python_module_from_path_supports_extensionless_helper(tmp_path):
    helper = tmp_path / "mvn-postgres-pitr-upload"
    helper.write_text(
        "def build_client(config):\n"
        "    return ('client', config)\n"
        "def load_config():\n"
        "    return 'config'\n",
        encoding="utf-8",
    )

    module = pitr_restore._load_python_module_from_path(
        "test_extensionless_pitr_upload_helper",
        helper,
    )

    assert module is not None
    assert module.load_config() == "config"
    assert module.build_client("cfg") == ("client", "cfg")


def test_outer_manifest_accepts_only_the_fixed_v1_schema():
    payload = _minimal_payload()

    manifest = pitr_restore._validate_outer_manifest(
        payload=payload,
        manifest_key=_manifest_key("backup-1"),
        config=FakeConfig,
        expected_system_identifier=SYSTEM_IDENTIFIER,
    )

    assert set(payload) == set(pitr_restore.OUTER_MANIFEST_KEYS)
    assert all(
        set(entry) == set(pitr_restore.OUTER_FILE_KEYS)
        for entry in payload["files"]
    )
    assert manifest.system_identifier == SYSTEM_IDENTIFIER
    assert manifest.timeline == 1
    assert manifest.start_lsn == "0/0"
    assert manifest.end_lsn == "0/800"


@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_outer_manifest_rejects_top_level_schema_drift(mutation):
    payload = _minimal_payload()
    if mutation == "extra":
        payload["unexpected"] = True
    else:
        del payload["source_node"]

    with pytest.raises(SystemExit, match="exact schema"):
        pitr_restore._validate_outer_manifest(
            payload=payload,
            manifest_key=_manifest_key("backup-1"),
            config=FakeConfig,
            expected_system_identifier=SYSTEM_IDENTIFIER,
        )

def test_outer_manifest_rejects_file_entry_schema_drift():
    payload = _minimal_payload()
    payload["files"][0]["etag"] = "untrusted"

    with pytest.raises(SystemExit, match="file entry.*exact schema"):
        pitr_restore._validate_outer_manifest(
            payload=payload,
            manifest_key=_manifest_key("backup-1"),
            config=FakeConfig,
            expected_system_identifier=SYSTEM_IDENTIFIER,
        )


def test_outer_manifest_rejects_wrong_cluster_identity():
    payload = _minimal_payload()

    with pytest.raises(SystemExit, match="expected cluster"):
        pitr_restore._validate_outer_manifest(
            payload=payload,
            manifest_key=_manifest_key("backup-1"),
            config=FakeConfig,
            expected_system_identifier=OTHER_SYSTEM_IDENTIFIER,
        )


def test_outer_manifest_rejects_non_string_source_node_cleanly():
    payload = _minimal_payload()
    payload["source_node"] = ["mvn-api"]

    with pytest.raises(SystemExit, match="source node is invalid"):
        pitr_restore._validate_outer_manifest(
            payload=payload,
            manifest_key=_manifest_key("backup-1"),
            config=FakeConfig,
            expected_system_identifier=SYSTEM_IDENTIFIER,
        )


def test_manifest_inventory_skips_bounded_legacy_v0_and_keeps_valid_v1():
    current = _minimal_payload("current")
    legacy = {
        "backup_id": "legacy",
        "created_at": "2026-07-01T01:00:00+00:00",
        "cluster": "mvn-api",
        "hostname": "old-primary",
        "files": [],
    }
    objects = {
        _manifest_key("legacy"): json.dumps(legacy).encode(),
        _manifest_key("current"): json.dumps(current).encode(),
    }

    manifests = pitr_restore.list_manifests(
        FakeClient(objects, metadata={_manifest_key("current"): {
            "sha256": hashlib.sha256(objects[_manifest_key("current")]).hexdigest()
        }}),
        FakeConfig,
        expected_system_identifier=SYSTEM_IDENTIFIER,
    )

    assert [manifest.backup_id for manifest in manifests] == ["current"]


@pytest.mark.parametrize(
    "legacy",
    [
        {"backup_id": "legacy"},
        {
            "backup_id": "legacy",
            "created_at": "2026-07-01T01:00:00+00:00",
            "cluster": "mvn-api",
            "hostname": "old-primary",
            "files": [{"name": "base.tar.gz"}],
        },
        {
            "backup_id": "other",
            "created_at": "2026-07-01T01:00:00+00:00",
            "cluster": "mvn-api",
            "hostname": "old-primary",
            "files": [],
        },
    ],
)
def test_manifest_inventory_rejects_malformed_unversioned_payload(legacy):
    client = FakeClient({_manifest_key("legacy"): json.dumps(legacy).encode()})

    with pytest.raises(SystemExit, match="historical v0|Historical v0"):
        pitr_restore.list_manifests(client, FakeConfig)


def test_manifest_inventory_rejects_claimed_v1_without_digest_metadata():
    payload = _minimal_payload()
    key = _manifest_key("backup-1")
    client = FakeClient({key: json.dumps(payload).encode()}, metadata={key: {}})

    with pytest.raises(SystemExit, match="Versioned.*no digest metadata"):
        pitr_restore.list_manifests(client, FakeConfig)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(schema_version=2),
        lambda payload: payload.pop("source_node"),
    ],
)
def test_manifest_inventory_never_skips_invalid_claimed_schema(mutation):
    payload = _minimal_payload()
    mutation(payload)
    client = FakeClient({_manifest_key("backup-1"): json.dumps(payload).encode()})

    with pytest.raises(SystemExit, match="schema_version|exact schema"):
        pitr_restore.list_manifests(
            client,
            FakeConfig,
            expected_system_identifier=SYSTEM_IDENTIFIER,
        )


def test_select_manifest_uses_latest_completed_backup_before_target():
    old = _manifest_record(
        backup_id="old",
        completed_at=datetime(2026, 7, 2, 1, tzinfo=timezone.utc),
    )
    future = _manifest_record(
        backup_id="future",
        completed_at=datetime(2026, 7, 2, 3, tzinfo=timezone.utc),
    )

    selected = pitr_restore.select_manifest(
        [old, future],
        target_time=datetime(2026, 7, 2, 2, tzinfo=timezone.utc),
    )

    assert selected.backup_id == "old"
    with pytest.raises(SystemExit, match="Eligible basebackup not found"):
        pitr_restore.select_manifest(
            [old, future],
            backup_id="future",
            target_time=datetime(2026, 7, 2, 2, tzinfo=timezone.utc),
        )
