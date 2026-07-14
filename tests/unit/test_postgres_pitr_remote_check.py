import hashlib
import importlib.util
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/ha/check_postgres_pitr_remote.py"
SPEC = importlib.util.spec_from_file_location("check_postgres_pitr_remote", MODULE_PATH)
assert SPEC and SPEC.loader
pitr_remote = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pitr_remote
SPEC.loader.exec_module(pitr_remote)


class FakePaginator:
    def __init__(self, pages, expected_prefix=None):
        self.pages = pages
        self.expected_prefix = expected_prefix

    def paginate(self, **kwargs):
        assert kwargs["Bucket"] == "private"
        if self.expected_prefix is not None:
            assert kwargs["Prefix"] == self.expected_prefix
        yield from self.pages


class FakeClient:
    def __init__(self, pages):
        self.pages = pages

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self.pages)


class PrefixClient:
    def __init__(self, pages_by_prefix, *, heads=None, bodies=None):
        self.pages_by_prefix = pages_by_prefix
        self.heads = heads or {}
        self.bodies = bodies or {}
        self.head_calls = []
        self.get_calls = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        pages_by_prefix = self.pages_by_prefix

        class PrefixPaginator:
            def paginate(self, **kwargs):
                assert kwargs["Bucket"] == "private"
                yield from pages_by_prefix.get(kwargs["Prefix"], [])

        return PrefixPaginator()

    def head_object(self, *, Bucket, Key):
        assert Bucket == "private"
        self.head_calls.append(Key)
        if Key not in self.heads:
            raise MissingObject
        return self.heads[Key]

    def get_object(self, *, Bucket, Key):
        assert Bucket == "private"
        self.get_calls.append(Key)
        payload = self.bodies[Key]
        return {"ContentLength": len(payload), "Body": io.BytesIO(payload)}


class MissingObject(Exception):
    response = {
        "Error": {"Code": "NoSuchKey"},
        "ResponseMetadata": {"HTTPStatusCode": 404},
    }


SYSTEM_IDENTIFIER = "7423456789012345678"


def _manifest_payload(*, backup_id="backup-1"):
    prefix = f"postgres/pitr/mvn-api/basebackups/{backup_id}"
    return {
        "schema_version": 1,
        "backup_id": backup_id,
        "cluster": "mvn-api",
        "system_identifier": SYSTEM_IDENTIFIER,
        "timeline": 7,
        "start_lsn": "0/A000000",
        "end_lsn": "0/B000000",
        "started_at": "2026-07-14T01:00:00Z",
        "completed_at": "2026-07-14T01:05:00Z",
        "source_node": "mvn-api",
        "files": [
            {
                "name": "backup_manifest",
                "key": f"{prefix}/backup_manifest",
                "size_bytes": 512,
                "sha256": "a" * 64,
            },
            {
                "name": "base.tar.gz",
                "key": f"{prefix}/base.tar.gz",
                "size_bytes": 4096,
                "sha256": "b" * 64,
            },
        ],
    }


def _manifest_client(payload, *, uploaded_by="mvn-postgres-pitr", digest=None):
    raw = json.dumps(payload, sort_keys=True).encode()
    key = (
        "postgres/pitr/mvn-api/basebackups/"
        f"{payload.get('backup_id', 'backup-1')}/manifest.json"
    )
    metadata_digest = digest or hashlib.sha256(raw).hexdigest()
    client = PrefixClient(
        {},
        heads={
            key: {
                "ContentLength": len(raw),
                "LastModified": datetime(2026, 7, 14, 1, 6, tzinfo=timezone.utc),
                "Metadata": {
                    "sha256": metadata_digest,
                    "uploaded-by": uploaded_by,
                },
            }
        },
        bodies={key: raw},
    )
    return client, key, raw


def test_load_python_module_from_path_supports_extensionless_helper(tmp_path):
    helper = tmp_path / "mvn-postgres-pitr-upload"
    helper.write_text(
        "def build_client(config):\n"
        "    return ('client', config)\n"
        "def load_config():\n"
        "    return 'config'\n",
        encoding="utf-8",
    )

    module = pitr_remote._load_python_module_from_path(
        "test_extensionless_pitr_remote_upload_helper",
        helper,
    )

    assert module is not None
    assert module.load_config() == "config"
    assert module.build_client("cfg") == ("client", "cfg")


def test_latest_object_picks_newest_matching_key():
    older = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc)
    client = FakeClient(
        [
            {
                "Contents": [
                    {"Key": "postgres/pitr/mvn-api/wal/00000001/old", "LastModified": older, "Size": 16},
                    {"Key": "postgres/pitr/mvn-api/wal/00000001/new", "LastModified": newer, "Size": 16},
                ]
            }
        ]
    )

    item = pitr_remote._latest_object(client, "private", "postgres/pitr/mvn-api/wal/")

    assert item["Key"] == "postgres/pitr/mvn-api/wal/00000001/new"


def test_latest_object_filters_suffix_and_directory_markers():
    older = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc)
    client = FakeClient(
        [
            {
                "Contents": [
                    {"Key": "postgres/pitr/mvn-api/wal/dir/", "LastModified": newer, "Size": 0},
                    {"Key": "postgres/pitr/mvn-api/wal/base.tar.gz", "LastModified": newer, "Size": 32},
                    {"Key": "postgres/pitr/mvn-api/wal/manifest.json", "LastModified": older, "Size": 64},
                ]
            }
        ]
    )

    item = pitr_remote._latest_object(
        client,
        "private",
        "postgres/pitr/mvn-api/wal/",
        suffix="manifest.json",
    )

    assert item["Key"] == "postgres/pitr/mvn-api/wal/manifest.json"


def test_latest_object_rejects_ambiguous_equal_timestamps():
    modified = datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc)
    client = FakeClient(
        [
            {
                "Contents": [
                    {"Key": "prefix/backup-a/manifest.json", "LastModified": modified},
                    {"Key": "prefix/backup-b/manifest.json", "LastModified": modified},
                ]
            }
        ]
    )

    with pytest.raises(pitr_remote.StatusProofError, match="ambiguous"):
        pitr_remote._latest_object(
            client,
            "private",
            "prefix/",
            suffix="/manifest.json",
        )


def test_latest_wal_filters_junk_but_keeps_canonical_partial():
    older = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc)
    prefix = "postgres/pitr/mvn-api/wal/"
    partial = "00000007000000000000004B.partial"
    client = FakeClient(
        [
            {
                "Contents": [
                    {"Key": prefix + "junk/newest", "LastModified": newer},
                    {
                        "Key": f"{prefix}00000007/{partial}",
                        "LastModified": older,
                        "Size": pitr_remote.WAL_SEGMENT_BYTES,
                    },
                ]
            }
        ]
    )

    item = pitr_remote._latest_object(
        client, "private", prefix, canonical_wal=True
    )

    assert item["Key"] == f"{prefix}00000007/{partial}"


def test_latest_wal_does_not_treat_history_as_a_restorable_segment():
    prefix = "postgres/pitr/mvn-api/wal/"
    client = FakeClient(
        [
            {
                "Contents": [
                    {
                        "Key": prefix + "00000008/00000008.history",
                        "LastModified": datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
                        "Size": 42,
                    },
                    {
                        "Key": prefix + "00000008/00000008000000000000004B",
                        "LastModified": datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc),
                        "Size": pitr_remote.WAL_SEGMENT_BYTES,
                    },
                ]
            }
        ]
    )

    item = pitr_remote._latest_object(
        client, "private", prefix, canonical_wal=True
    )
    assert item["Key"].endswith("00000008000000000000004B")


def test_latest_wal_preserves_equal_timestamp_ambiguity_after_filtering():
    modified = datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc)
    prefix = "postgres/pitr/mvn-api/wal/"
    client = FakeClient(
        [
            {
                "Contents": [
                    {
                        "Key": prefix + "00000007/00000007000000000000004B.partial",
                        "LastModified": modified,
                        "Size": pitr_remote.WAL_SEGMENT_BYTES,
                    },
                    {
                        "Key": prefix + "00000008/00000008000000000000004B",
                        "LastModified": modified,
                        "Size": pitr_remote.WAL_SEGMENT_BYTES,
                    },
                ]
            }
        ]
    )

    with pytest.raises(pitr_remote.StatusProofError, match="ambiguous"):
        pitr_remote._latest_object(
            client, "private", prefix, canonical_wal=True
        )


@pytest.mark.parametrize(
    "size",
    [pitr_remote.WAL_SEGMENT_BYTES - 1, pitr_remote.WAL_SEGMENT_BYTES + 1],
)
def test_latest_wal_rejects_noncanonical_segment_size(size):
    prefix = "postgres/pitr/mvn-api/wal/"
    client = FakeClient(
        [
            {
                "Contents": [
                    {
                        "Key": prefix + "00000007/00000007000000000000004B.partial",
                        "LastModified": datetime(2026, 7, 1, tzinfo=timezone.utc),
                        "Size": size,
                    }
                ]
            }
        ]
    )

    with pytest.raises(pitr_remote.StatusProofError, match="size is not canonical"):
        pitr_remote._latest_object(
            client, "private", prefix, canonical_wal=True
        )


def test_manifest_proof_downloads_bounded_body_and_validates_exact_schema():
    payload = _manifest_payload()
    client, key, raw = _manifest_client(payload)

    proof, size = pitr_remote._load_manifest_proof(
        client,
        bucket="private",
        key=key,
        key_prefix="postgres/pitr",
        cluster="mvn-api",
        expected_system_identifier=SYSTEM_IDENTIFIER,
    )

    assert proof.backup_id == "backup-1"
    assert proof.timeline == 7
    assert proof.file_count == 2
    assert size == len(raw)
    assert client.head_calls == [key]
    assert client.get_calls == [key]


def test_manifest_proof_rejects_extra_top_level_field():
    payload = _manifest_payload()
    payload["created_at"] = "2026-07-14T01:05:00Z"
    client, key, _raw = _manifest_client(payload)

    with pytest.raises(pitr_remote.StatusProofError, match="top-level schema"):
        pitr_remote._load_manifest_proof(
            client,
            bucket="private",
            key=key,
            key_prefix="postgres/pitr",
            cluster="mvn-api",
            expected_system_identifier=SYSTEM_IDENTIFIER,
        )


def test_manifest_proof_rejects_wrong_system_identifier_and_file_key():
    payload = _manifest_payload()
    client, key, _raw = _manifest_client(payload)
    with pytest.raises(pitr_remote.StatusProofError, match="system identifier"):
        pitr_remote._load_manifest_proof(
            client,
            bucket="private",
            key=key,
            key_prefix="postgres/pitr",
            cluster="mvn-api",
            expected_system_identifier="8423456789012345678",
        )

    payload["files"][0]["key"] += ".other"
    client, key, _raw = _manifest_client(payload)
    with pytest.raises(pitr_remote.StatusProofError, match="file key"):
        pitr_remote._load_manifest_proof(
            client,
            bucket="private",
            key=key,
            key_prefix="postgres/pitr",
            cluster="mvn-api",
            expected_system_identifier=SYSTEM_IDENTIFIER,
        )


@pytest.mark.parametrize(
    ("uploaded_by", "digest", "message"),
    [
        ("other-uploader", None, "provenance"),
        ("mvn-postgres-pitr", "0" * 64, "body sha256"),
    ],
)
def test_manifest_proof_rejects_bad_metadata(uploaded_by, digest, message):
    payload = _manifest_payload()
    client, key, _raw = _manifest_client(
        payload,
        uploaded_by=uploaded_by,
        digest=digest,
    )

    with pytest.raises(pitr_remote.StatusProofError, match=message):
        pitr_remote._load_manifest_proof(
            client,
            bucket="private",
            key=key,
            key_prefix="postgres/pitr",
            cluster="mvn-api",
            expected_system_identifier=SYSTEM_IDENTIFIER,
        )


def test_manifest_proof_rejects_oversized_head_before_get():
    payload = _manifest_payload()
    client, key, _raw = _manifest_client(payload)
    client.heads[key]["ContentLength"] = pitr_remote.MAX_MANIFEST_BYTES + 1

    with pytest.raises(pitr_remote.StatusProofError, match="bounded size"):
        pitr_remote._load_manifest_proof(
            client,
            bucket="private",
            key=key,
            key_prefix="postgres/pitr",
            cluster="mvn-api",
            expected_system_identifier=SYSTEM_IDENTIFIER,
        )
    assert client.get_calls == []


def test_manifest_proof_rejects_last_modified_before_completion():
    payload = _manifest_payload()
    client, key, _raw = _manifest_client(payload)
    client.heads[key]["LastModified"] = datetime(
        2026, 7, 14, 1, 4, tzinfo=timezone.utc
    )

    with pytest.raises(pitr_remote.StatusProofError, match="LastModified"):
        pitr_remote._load_manifest_proof(
            client,
            bucket="private",
            key=key,
            key_prefix="postgres/pitr",
            cluster="mvn-api",
            expected_system_identifier=SYSTEM_IDENTIFIER,
        )


def test_main_downloads_and_reports_fresh_exact_manifest(
    monkeypatch,
    capsys,
):
    payload = _manifest_payload()
    client, key, raw = _manifest_client(payload)
    base_prefix = "postgres/pitr/mvn-api/basebackups/"
    client.pages_by_prefix[base_prefix] = [
        {
            "Contents": [
                {
                    "Key": key,
                    "LastModified": datetime.now(timezone.utc),
                    "Size": len(raw),
                }
            ]
        }
    ]
    config = SimpleNamespace(
        bucket="private",
        key_prefix="postgres/pitr",
        cluster="mvn-api",
    )
    monkeypatch.setattr(pitr_remote, "load_config", lambda: config)
    monkeypatch.setattr(pitr_remote, "build_client", lambda _config: client)
    monkeypatch.setattr(pitr_remote, "_age_hours", lambda _completed_at: 0.25)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_postgres_pitr_remote.py",
            "--skip-wal",
            "--expected-system-identifier",
            SYSTEM_IDENTIFIER,
        ],
    )

    assert pitr_remote.main() == 0
    output = capsys.readouterr().out
    assert "pitr_remote_basebackup status=fresh" in output
    assert "files=2 timeline=7" in output
    assert "pitr_remote_summary status=passed failures=0 warnings=0" in output


def test_stale_wal_is_idle_only_when_expected_wal_exists_and_queue_is_empty():
    assert pitr_remote._classify_wal_status(4.0, 3.0, 0, True) == "idle"
    assert pitr_remote._classify_wal_status(4.0, 3.0, 1, True) == "stale"
    assert pitr_remote._classify_wal_status(4.0, 3.0, None, True) == "stale"
    assert pitr_remote._classify_wal_status(4.0, 3.0, 0, False) == "stale"


def test_fresh_wal_stays_fresh_even_with_pending_local_wal():
    assert pitr_remote._classify_wal_status(0.5, 3.0, 2, False) == "fresh"


def _run_wal_check(monkeypatch, client, wal):
    config = SimpleNamespace(
        bucket="private",
        key_prefix="postgres/pitr",
        cluster="mvn-api",
    )
    monkeypatch.setattr(pitr_remote, "load_config", lambda: config)
    monkeypatch.setattr(pitr_remote, "build_client", lambda _config: client)
    monkeypatch.setattr(pitr_remote, "_age_hours", lambda _last_modified: 4.0)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_postgres_pitr_remote.py",
            "--skip-basebackup",
            "--expected-wal",
            wal,
            "--local-pending-wal-count",
            "0",
        ],
    )
    return pitr_remote.main()


def test_main_reports_idle_when_expected_wal_is_present_and_queue_is_empty(
    monkeypatch,
    capsys,
):
    wal = "00000001000000000000000A"
    wal_prefix = "postgres/pitr/mvn-api/wal/"
    expected_key = f"{wal_prefix}00000001/{wal}"
    item = {
        "Key": expected_key,
        "LastModified": datetime.now(timezone.utc),
        "Size": pitr_remote.WAL_SEGMENT_BYTES,
    }
    client = PrefixClient(
        {
            wal_prefix: [{"Contents": [item]}],
        },
        heads={
            expected_key: {
                "ContentLength": pitr_remote.WAL_SEGMENT_BYTES,
                "LastModified": datetime.now(timezone.utc),
                "Metadata": {
                    "sha256": "c" * 64,
                    "uploaded-by": "mvn-postgres-pitr",
                },
            }
        },
    )

    assert _run_wal_check(monkeypatch, client, wal) == 0
    output = capsys.readouterr().out
    assert "pitr_remote_wal_expected status=present" in output
    assert "size_bytes=16777216" in output
    assert client.head_calls == [expected_key]
    assert "pitr_remote_wal status=idle" in output
    assert "pitr_remote_summary status=passed failures=0 warnings=1" in output


@pytest.mark.parametrize(
    "head",
    [
        {
            "ContentLength": pitr_remote.WAL_SEGMENT_BYTES - 1,
            "Metadata": {
                "sha256": "c" * 64,
                "uploaded-by": "mvn-postgres-pitr",
            },
        },
        {
            "ContentLength": pitr_remote.WAL_SEGMENT_BYTES,
            "Metadata": {
                "sha256": "not-a-digest",
                "uploaded-by": "mvn-postgres-pitr",
            },
        },
        {
            "ContentLength": pitr_remote.WAL_SEGMENT_BYTES,
            "Metadata": {
                "sha256": "c" * 64,
                "uploaded-by": "unknown",
            },
        },
    ],
)
def test_main_rejects_expected_wal_without_canonical_head_proof(
    monkeypatch,
    capsys,
    head,
):
    wal = "00000001000000000000000A"
    wal_prefix = "postgres/pitr/mvn-api/wal/"
    expected_key = f"{wal_prefix}00000001/{wal}"
    latest_item = {
        "Key": expected_key,
        "LastModified": datetime.now(timezone.utc),
        "Size": pitr_remote.WAL_SEGMENT_BYTES,
    }
    client = PrefixClient(
        {wal_prefix: [{"Contents": [latest_item]}]},
        heads={expected_key: head},
    )

    assert _run_wal_check(monkeypatch, client, wal) == 1
    output = capsys.readouterr().out
    assert "pitr_remote_wal_expected status=invalid" in output
    assert "pitr_remote_summary status=failed" in output


def test_main_fails_when_expected_wal_is_missing(monkeypatch, capsys):
    wal = "00000001000000000000000A"
    wal_prefix = "postgres/pitr/mvn-api/wal/"
    expected_key = f"{wal_prefix}00000001/{wal}"
    latest_item = {
        "Key": f"{wal_prefix}00000001/000000010000000000000009",
        "LastModified": datetime.now(timezone.utc),
        "Size": pitr_remote.WAL_SEGMENT_BYTES,
    }
    client = PrefixClient(
        {
            wal_prefix: [{"Contents": [latest_item]}],
        }
    )

    assert _run_wal_check(monkeypatch, client, wal) == 1
    output = capsys.readouterr().out
    assert "pitr_remote_wal_expected status=missing" in output
    assert "pitr_remote_wal status=stale" in output
    assert "pitr_remote_summary status=failed failures=2 warnings=0" in output
