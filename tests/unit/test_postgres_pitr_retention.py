from __future__ import annotations

import base64
import copy
import hashlib
import json
import struct
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import plan_postgres_pitr_retention as planner
from scripts.ha import postgres_pitr_wal_lineage as lineage

FIXTURE = Path(__file__).parent / "fixtures/postgres_pitr_retention/timeline1.json"
SYSTEM_ID = "7612345678901234567"
SEGMENT = 16 * 1024 * 1024
PREFIX = "postgres/pitr/mvn-api/"
CONFIG = SimpleNamespace(bucket="offline", key_prefix="postgres/pitr", cluster="mvn-api")
AS_OF = planner.parse_as_of("2026-10-07T12:00:00+03:00")


def wal_name(timeline, position):
    return lineage.wal_name_for_position(
        timeline=timeline, position=position, segment_size_bytes=SEGMENT
    )


def wal_key(timeline, position):
    return f"{PREFIX}wal/{timeline:08X}/{wal_name(timeline, position)}"


def record(key, data, *, size=None):
    digest = hashlib.sha256(data).hexdigest()
    return dict(
        key=key,
        size_bytes=len(data) if size is None else size,
        etag=f'"{digest}"',
        sha256=digest,
        payload_base64=base64.b64encode(data).decode(),
    )


def segment(timeline, position, *, header_timeline=None, sysid=SYSTEM_ID, endian="<"):
    header = struct.pack(
        endian + "HHIQI4xQII",
        planner.PG15_WAL_MAGIC,
        2,
        timeline if header_timeline is None else header_timeline,
        position * SEGMENT,
        0,
        int(sysid),
        SEGMENT,
        8192,
    )
    item = record(wal_key(timeline, position), header, size=SEGMENT)
    item["wal_header_hex"] = header.hex()
    del item["payload_base64"]
    return item


def backup(backup_id, completed, position, *, timeline=1, source="mvn-api", sysid=SYSTEM_ID):
    prefix = f"{PREFIX}basebackups/{backup_id}/"
    pg_manifest = {
        "PostgreSQL-Backup-Manifest-Version": 1,
        "Files": [{"Path": "PG_VERSION", "Size": 3, "Last-Modified": "2026-09-27 09:00:00 GMT"}],
        "WAL-Ranges": [
            {
                "Timeline": timeline,
                "Start-LSN": f"0/{position * SEGMENT + 40:X}",
                "End-LSN": f"0/{position * SEGMENT + 200:X}",
            }
        ],
    }
    native_prefix = (json.dumps(pg_manifest, indent=2)[:-2] + ",\n").encode()
    native_bytes = (
        native_prefix
        + (f'"Manifest-Checksum": "{hashlib.sha256(native_prefix).hexdigest()}"}}\n').encode()
    )
    artifacts = [
        record(prefix + "base.tar.gz", b"synthetic compressed backup identity"),
        record(prefix + "pg_wal.tar.gz", b"synthetic streamed wal identity"),
        record(prefix + "backup_manifest", native_bytes),
    ]
    payload = dict(
        schema_version=1,
        backup_id=backup_id,
        cluster="mvn-api",
        system_identifier=sysid,
        timeline=timeline,
        start_lsn=f"0/{position * SEGMENT:X}",
        end_lsn=f"0/{position * SEGMENT + 300:X}",
        started_at=completed,
        completed_at=completed,
        source_node=source,
        files=[
            dict(
                name=r["key"].rsplit("/", 1)[-1],
                key=r["key"],
                size_bytes=r["size_bytes"],
                sha256=r["sha256"],
            )
            for r in artifacts
        ],
    )
    return [
        *artifacts,
        record(prefix + "manifest.json", json.dumps(payload, sort_keys=True).encode()),
    ]


def fixture_payload():
    return dict(
        schema_version=1,
        listing_complete=True,
        objects=[
            *backup("old", "2026-09-27T09:00:00Z", 1),
            *backup("anchor", "2026-09-29T09:00:00Z", 3),
            *backup("inside", "2026-10-05T09:00:00Z", 5, source="zakup"),
            *(segment(1, p) for p in range(1, 8)),
            record(f"{PREFIX}wal/00000001/{wal_name(1, 3)}.00000028.backup", b"backup history"),
            record(f"{PREFIX}unclassified/operator-note", b"keep"),
        ],
    )


def run(payload=None, **kwargs):
    return planner.plan(
        planner.InventoryClient(payload or fixture_payload()),
        CONFIG,
        as_of=AS_OF,
        retention=timedelta(days=7),
        expected_system_identifier=SYSTEM_ID,
        required_end_wal=kwargs.pop("required_end_wal", wal_name(1, 7)),
        **kwargs,
    )


def change_manifest(payload, backup_id, edit):
    key = f"{PREFIX}basebackups/{backup_id}/manifest.json"
    index = next(i for i, r in enumerate(payload["objects"]) if r["key"] == key)
    outer = json.loads(base64.b64decode(payload["objects"][index]["payload_base64"]))
    edit(outer)
    payload["objects"][index] = record(key, json.dumps(outer, sort_keys=True).encode())


def blocked(report):
    assert report["status"] == "blocked", report
    assert report["candidates"] == []
    assert report["candidate_count"] == report["candidate_bytes"] == 0
    assert report["blocked_reasons"]
    assert report["deletion_authorized"] is False


def test_timeline1_exact_candidates_and_conservative_metadata():
    payload = json.loads(FIXTURE.read_bytes())
    assert payload == fixture_payload()  # checked-in operator fixture is reproducible
    report = run(payload)
    assert report["status"] == "planned", report
    assert report["evidence"]["anchor_backup_id"] == "anchor"
    assert report["evidence"]["retained_backup_ids"] == ["anchor", "inside"]
    keys = {r["key"] for r in report["candidates"]}
    expected = {r["key"] for r in payload["objects"] if "/basebackups/old/" in r["key"]}
    expected |= {wal_key(1, 1), wal_key(1, 2)}
    assert keys == expected
    assert report["candidate_count"] == 6
    assert report["candidate_bytes"] == sum(
        r["size_bytes"] for r in payload["objects"] if r["key"] in keys
    )
    assert report["retained_bytes"] + report["candidate_bytes"] == sum(
        r["size_bytes"] for r in payload["objects"]
    )
    assert any(r["key"].endswith(".backup") for r in report["retained"])
    assert any("/unclassified/" in r["key"] for r in report["retained"])
    assert report["recovery_window_proven"] is False


def test_deterministic_order_and_timezone_equivalence():
    payload = fixture_payload()
    original = run(payload)
    payload["objects"].reverse()
    assert run(payload) == original
    assert planner.parse_as_of("2026-10-07T09:00:00Z") == AS_OF
    with pytest.raises(ValueError, match="timezone"):
        planner.parse_as_of("2026-10-07T09:00:00")


def failover_payload():
    payload = fixture_payload()
    payload["objects"] = [r for r in payload["objects"] if "/basebackups/inside/" not in r["key"]]
    payload["objects"] += backup("inside", "2026-10-05T09:00:00Z", 5, timeline=3, source="zakup")
    # Sparse lineage: 1 -> 3 -> 5; fork in middle of segment 4 / segment 6.
    history3 = b"1\t0/4800000\tpromoted\n"
    payload["objects"] += [
        record(f"{PREFIX}wal/00000003/00000003.history", history3),
        record(f"{PREFIX}wal/00000005/00000005.history", history3 + b"3\t0/6800000\tpromoted\n"),
        segment(3, 4, header_timeline=1),
        segment(3, 5),
        segment(5, 6, header_timeline=3),
        segment(5, 7),
    ]
    return payload


def test_failover_preserves_sparse_ancestor_histories_and_restore_chain():
    payload = failover_payload()
    report = run(payload, required_end_wal=wal_name(5, 7))
    assert report["status"] == "planned", report
    assert report["evidence"]["verified_lineage"] == [1, 3, 5]
    assert not any(
        "/wal/00000003/" in r["key"] or "/wal/00000005/" in r["key"] for r in report["candidates"]
    )
    # Independently select using the restore helper after removing all candidates.
    candidates = {r["key"] for r in report["candidates"]}
    remaining = [
        lineage.WalObject(r["key"], r["key"].rsplit("/", 1)[-1], r["size_bytes"])
        for r in payload["objects"]
        if "/wal/" in r["key"] and r["key"] not in candidates
    ]
    by_key = {r["key"]: r for r in payload["objects"]}
    selection = lineage.select_wal_objects(
        remaining,
        start_wal_name=wal_name(1, 3),
        start_lsn="0/3000000",
        required_end_wal=wal_name(5, 7),
        segment_size_bytes=SEGMENT,
        history_loader=lambda w: base64.b64decode(by_key[w.key]["payload_base64"]),
    )
    assert [w.filename for w in selection.segments] == [
        wal_name(1, 3),
        wal_name(3, 4),
        wal_name(3, 5),
        wal_name(5, 6),
        wal_name(5, 7),
    ]
    assert len(selection.history_files) == 2


@pytest.mark.parametrize("failure", ["gap", "missing_history", "fork", "branch", "corrupt_history"])
def test_failover_uncertainties_block_whole_report(failure):
    payload = failover_payload()
    if failure == "gap":
        payload["objects"] = [r for r in payload["objects"] if r["key"] != wal_key(3, 5)]
    elif failure == "missing_history":
        payload["objects"] = [
            r for r in payload["objects"] if not r["key"].endswith("00000003.history")
        ]
    elif failure == "fork":
        key = f"{PREFIX}wal/00000003/00000003.history"
        payload["objects"] = [r for r in payload["objects"] if r["key"] != key]
        payload["objects"].append(record(key, b"1\t0/4900000\tdifferent fork\n"))
    elif failure == "branch":
        payload["objects"] += [
            record(f"{PREFIX}wal/00000004/00000004.history", b"1\t0/5800000\tbranch\n")
        ]
    else:
        key = f"{PREFIX}wal/00000003/00000003.history"
        payload["objects"] = [r for r in payload["objects"] if r["key"] != key]
        payload["objects"].append(record(key, b"not a valid history"))
    blocked(run(payload, required_end_wal=wal_name(5, 7)))


@pytest.mark.parametrize(
    "failure",
    [
        "missing_manifest",
        "bad_json",
        "bad_schema",
        "legacy",
        "missing_artifact",
        "digest",
        "artifact_size",
        "pg_lineage",
        "system",
        "duplicate",
        "version",
        "wal_identity",
        "wal_size",
        "wal_header",
        "no_anchor",
        "end_before_backup",
        "noncanonical_wal",
        "missing_digest",
    ],
)
def test_inventory_and_backup_uncertainties_block(failure):
    payload = fixture_payload()
    args = {}
    manifest_key = f"{PREFIX}basebackups/anchor/manifest.json"
    if failure in {"missing_manifest", "missing_artifact"}:
        key = (
            manifest_key
            if failure == "missing_manifest"
            else f"{PREFIX}basebackups/old/base.tar.gz"
        )
        payload["objects"] = [r for r in payload["objects"] if r["key"] != key]
    elif failure == "bad_json":
        payload["objects"] = [r for r in payload["objects"] if r["key"] != manifest_key]
        payload["objects"].append(record(manifest_key, b"{"))
    elif failure == "bad_schema":
        change_manifest(payload, "anchor", lambda m: m.update(schema_version=2))
    elif failure == "legacy":
        change_manifest(payload, "old", lambda m: m.pop("schema_version"))
    elif failure == "digest":
        next(r for r in payload["objects"] if r["key"].endswith("old/base.tar.gz"))["sha256"] = (
            "0" * 64
        )
    elif failure == "artifact_size":
        next(r for r in payload["objects"] if r["key"].endswith("old/base.tar.gz"))[
            "size_bytes"
        ] += 1
    elif failure == "pg_lineage":
        change_manifest(payload, "anchor", lambda m: m.update(timeline=2))
    elif failure == "system":
        change_manifest(payload, "old", lambda m: m.update(system_identifier="8612345678901234567"))
    elif failure == "duplicate":
        payload["objects"].append(copy.deepcopy(payload["objects"][0]))
        with pytest.raises(ValueError, match="duplicate"):
            planner.InventoryClient(payload)
        return
    elif failure == "version":
        next(r for r in payload["objects"] if r["key"] == manifest_key)["version_id"] = "version-a"
    elif failure == "wal_identity":
        key = wal_key(1, 2)
        payload["objects"] = [r for r in payload["objects"] if r["key"] != key]
        payload["objects"].append(segment(1, 2, sysid="8612345678901234567"))
    elif failure == "wal_size":
        next(r for r in payload["objects"] if r["key"] == wal_key(1, 2))["size_bytes"] -= 1
    elif failure == "wal_header":
        next(r for r in payload["objects"] if r["key"] == wal_key(1, 2))["wal_header_hex"] = (
            "00" * 40
        )
    elif failure == "no_anchor":
        payload["objects"] = [
            r
            for r in payload["objects"]
            if "/basebackups/old/" not in r["key"] and "/basebackups/anchor/" not in r["key"]
        ]
    elif failure == "end_before_backup":
        args["required_end_wal"] = wal_name(1, 4)
    elif failure == "noncanonical_wal":
        next(r for r in payload["objects"] if r["key"] == wal_key(1, 2))["key"] = (
            f"{PREFIX}wal/bad/{wal_name(1, 2)}"
        )
    elif failure == "missing_digest":
        next(r for r in payload["objects"] if r["key"] == manifest_key).pop("sha256")
    blocked(run(payload, **args))


def test_partial_unknown_and_future_objects_never_become_candidates():
    payload = fixture_payload()
    partial = record(wal_key(1, 1) + ".partial", b"partial", size=SEGMENT)
    payload["objects"] += [partial, segment(1, 8)]
    payload["objects"] += backup("future", "2026-10-08T09:00:00Z", 6)
    report = run(payload)
    assert report["status"] == "planned", report
    retained = {r["key"] for r in report["retained"]}
    assert partial["key"] in retained and wal_key(1, 8) in retained
    assert f"{PREFIX}basebackups/future/manifest.json" in retained


@pytest.mark.parametrize("start_lsn", ["0/3000000", "0/3000028"])
def test_anchor_start_segment_boundary_is_preserved(start_lsn):
    payload = fixture_payload()
    change_manifest(payload, "anchor", lambda m: m.update(start_lsn=start_lsn))
    report = run(payload)
    assert report["status"] == "planned", report
    assert wal_key(1, 3) not in {r["key"] for r in report["candidates"]}
    assert wal_key(1, 2) in {r["key"] for r in report["candidates"]}


def test_anchor_exact_window_start_and_no_age_based_wal_decision():
    payload = fixture_payload()
    change_manifest(
        payload,
        "anchor",
        lambda m: m.update(started_at="2026-09-30T09:00:00Z", completed_at="2026-09-30T09:00:00Z"),
    )
    assert run(payload)["evidence"]["anchor_backup_id"] == "anchor"
    # LastModified is deliberately absent in all fixtures.
    assert run(payload)["status"] == "planned"


@pytest.mark.parametrize(
    "failure",
    [
        "page_error",
        "truncated",
        "token_loop",
        "bad_page",
        "duplicate_page",
        "changed_inventory",
        "changed_head",
        "changed_range",
    ],
)
def test_pagination_and_concurrent_upload_fail_closed(failure):
    class FaultClient(planner.InventoryClient):
        calls = 0

        def list_objects_v2(self, **kwargs):
            self.calls += 1
            page = super().list_objects_v2(**kwargs)
            if failure == "page_error":
                if self.calls == 1:
                    return dict(
                        Contents=page["Contents"][:1],
                        IsTruncated=True,
                        NextContinuationToken="next",
                    )
                raise RuntimeError("secret-value-must-not-appear")
            if failure == "truncated":
                page["IsTruncated"] = True
            if failure in {"token_loop", "duplicate_page"}:
                page["IsTruncated"] = True
                page["NextContinuationToken"] = "0"
                if failure == "token_loop":
                    page["Contents"] = []
            if failure == "bad_page":
                del page["IsTruncated"]
            if failure == "changed_inventory" and self.calls > 1:
                page["Contents"] = page["Contents"][:-1]
            return page

        def head_object(self, **kwargs):
            head = super().head_object(**kwargs)
            if failure == "changed_head":
                head["ETag"] = "changed"
            return head

        def get_object(self, **kwargs):
            result = super().get_object(**kwargs)
            if failure == "changed_range" and kwargs.get("Range"):
                result["ETag"] = "changed"
            return result

    report = planner.plan(
        FaultClient(fixture_payload()),
        CONFIG,
        as_of=AS_OF,
        retention=timedelta(days=7),
        expected_system_identifier=SYSTEM_ID,
        required_end_wal=wal_name(1, 7),
    )
    blocked(report)
    assert "secret-value" not in json.dumps(report)


def test_multiple_pages_complete_listing_and_zero_mutation_interface():
    payload = fixture_payload()
    payload["objects"] += [record(f"{PREFIX}unknown/{i:04d}", b"x") for i in range(1020)]
    report = run(payload)
    assert report["status"] == "planned", report
    assert report["retained_count"] + report["candidate_count"] == len(payload["objects"])
    assert not hasattr(planner.InventoryClient(payload), "delete_object")
    assert not hasattr(planner.InventoryClient(payload), "put_object")


def test_cli_fixture_dry_run_and_invalid_inventory(tmp_path, capsys):
    args = [
        "--inventory",
        str(FIXTURE),
        "--as-of",
        "2026-10-07T12:00:00+03:00",
        "--retention-days",
        "7",
        "--expected-system-identifier",
        SYSTEM_ID,
        "--required-end-wal",
        wal_name(1, 7),
        "--dry-run",
    ]
    assert planner.main(args) == 0
    assert json.loads(capsys.readouterr().out)["candidate_count"] == 6
    file = tmp_path / "incomplete.json"
    payload = fixture_payload()
    payload["listing_complete"] = False
    file.write_text(json.dumps(payload))
    args[1] = str(file)
    assert planner.main(args) == 1
    blocked(json.loads(capsys.readouterr().out))


def test_big_endian_wal_header():
    payload = fixture_payload()
    payload["objects"] = [r for r in payload["objects"] if r["key"] != wal_key(1, 2)]
    payload["objects"].append(segment(1, 2, endian=">"))
    assert run(payload)["status"] == "planned"


@pytest.mark.parametrize(
    "failure",
    [
        "float_schema",
        "history_timeline1",
        "pre_birth_wal",
        "ambiguous_anchor",
        "overlapping_backup",
    ],
)
def test_additional_lineage_and_version_uncertainties(failure):
    payload = fixture_payload()
    end = wal_name(1, 7)
    if failure == "float_schema":
        change_manifest(payload, "anchor", lambda m: m.update(schema_version=1.0))
    elif failure == "history_timeline1":
        payload["objects"].append(record(f"{PREFIX}wal/00000001/00000001.history", b"bad history"))
    elif failure == "pre_birth_wal":
        payload = failover_payload()
        payload["objects"].append(segment(3, 2, header_timeline=1))
        end = wal_name(5, 7)
    elif failure == "ambiguous_anchor":
        payload["objects"] += backup("other-anchor", "2026-09-29T09:00:00Z", 2)
    else:
        payload["objects"] += backup("overlap", "2026-10-01T09:00:00Z", 2)
    blocked(run(payload, required_end_wal=end))


@pytest.mark.parametrize("days", [0, -1])
def test_invalid_retention_blocks(days):
    report = planner.plan(
        planner.InventoryClient(fixture_payload()),
        CONFIG,
        as_of=AS_OF,
        retention=timedelta(days=days),
        expected_system_identifier=SYSTEM_ID,
        required_end_wal=wal_name(1, 7),
    )
    blocked(report)


def test_current_uploader_manifest_and_idempotent_retry_are_accepted(tmp_path, monkeypatch, capsys):
    import argparse
    import io
    from scripts.ha import upload_postgres_pitr_to_s3 as uploader

    class MissingObject(Exception):
        response = {"Error": {"Code": "404"}}

    class CaptureClient(planner.InventoryClient):
        writes = 0

        def head_object(self, **kwargs):
            if kwargs["Key"] not in self.by_key:
                raise MissingObject()
            head = super().head_object(**kwargs)
            head["Metadata"]["uploaded-by"] = "mvn-postgres-pitr"
            return head

        def put_object(self, **kwargs):
            assert kwargs["IfNoneMatch"] == "*"
            assert kwargs["Key"] not in self.by_key
            body = kwargs["Body"]
            data = body.read() if hasattr(body, "read") else body
            r = record(kwargs["Key"], data)
            assert kwargs["Metadata"]["sha256"] == r["sha256"]
            self.records.append(r)
            self.by_key[r["key"]] = r
            self.writes += 1

        def get_object(self, **kwargs):
            if "Range" in kwargs:
                return super().get_object(**kwargs)
            r = self.by_key[kwargs["Key"]]
            data = base64.b64decode(r["payload_base64"])
            return dict(ContentLength=len(data), Body=io.BytesIO(data), ETag=r["etag"])

    client = CaptureClient(fixture_payload())
    monkeypatch.setattr(uploader, "load_config", lambda: CONFIG)
    monkeypatch.setattr(uploader, "build_client", lambda _config: client)
    for r in backup("current-upload", "2026-10-05T09:00:00Z", 5):
        if not r["key"].endswith("/manifest.json"):
            (tmp_path / r["key"].rsplit("/", 1)[-1]).write_bytes(
                base64.b64decode(r["payload_base64"])
            )
    args = argparse.Namespace(
        source_dir=str(tmp_path),
        backup_id="current-upload",
        system_identifier=SYSTEM_ID,
        timeline=1,
        start_lsn="0/5000000",
        end_lsn="0/500012C",
        started_at="2026-10-05T09:00:00Z",
        completed_at="2026-10-05T09:00:00Z",
        source_node="zakup",
        dry_run=False,
    )
    assert uploader.upload_basebackup(args) == 0
    assert client.writes == 4
    assert uploader.upload_basebackup(args) == 0
    assert client.writes == 4
    report = planner.plan(
        client,
        CONFIG,
        as_of=AS_OF,
        retention=timedelta(days=7),
        expected_system_identifier=SYSTEM_ID,
        required_end_wal=wal_name(1, 7),
    )
    assert report["status"] == "planned", report
    assert report["evidence"]["retained_backup_ids"] == ["anchor", "current-upload", "inside"]
    capsys.readouterr()


@pytest.mark.parametrize("archive_name", ["base.tar.gz", "pg_wal.tar.gz"])
def test_empty_required_archive_cannot_supply_retention_anchor(archive_name):
    payload = fixture_payload()
    key = f"{PREFIX}basebackups/anchor/{archive_name}"
    empty = record(key, b"")
    index = next(i for i, r in enumerate(payload["objects"]) if r["key"] == key)
    payload["objects"][index] = empty

    def replace_entry(m):
        entry = next(e for e in m["files"] if e["key"] == key)
        entry.update(size_bytes=0, sha256=empty["sha256"])

    change_manifest(payload, "anchor", replace_entry)
    blocked(run(payload))


@pytest.mark.parametrize("ancestor_switch", ["0/4800000", "0/4000000"])
def test_anchor_after_failover_retains_ancestor_fork_and_divergent_segments(ancestor_switch):
    payload = failover_payload()
    history3 = f"1\t{ancestor_switch}\tpromoted\n".encode()
    key3 = f"{PREFIX}wal/00000003/00000003.history"
    key5 = f"{PREFIX}wal/00000005/00000005.history"
    payload["objects"] = [
        r
        for r in payload["objects"]
        if r["key"] not in (key3, key5, wal_key(3, 4))
        and r["key"] != wal_key(5, 6)
        and "/basebackups/inside/" not in r["key"]
    ]
    payload["objects"] += [
        record(key3, history3),
        segment(3, 4, header_timeline=1 if ancestor_switch == "0/4800000" else 3),
        record(key5, history3 + b"3\t0/6000000\tpromoted\n"),
        segment(5, 6),
        *backup("leaf-anchor", "2026-09-29T10:00:00Z", 6, timeline=5, source="zakup"),
        *backup("inside", "2026-10-05T09:00:00Z", 7, timeline=5, source="zakup"),
    ]
    report = run(payload, required_end_wal=wal_name(5, 7))
    assert report["status"] == "planned", report
    assert report["evidence"]["anchor_backup_id"] == "leaf-anchor"
    candidates = {r["key"] for r in report["candidates"]}
    assert {wal_key(1, 1), wal_key(1, 2), wal_key(1, 3), wal_key(3, 4), wal_key(3, 5)} <= candidates
    # Segment 4 contains the ancestor switch; segment 5 is beyond that switch.
    # Neither belongs to a fully proven ancestor interval, even though both
    # positions precede the leaf anchor's segment number 6.
    assert wal_key(1, 4) not in candidates
    assert wal_key(1, 5) not in candidates
    assert wal_key(5, 6) not in candidates


def change_postgres_manifest(payload, edit):
    key = f"{PREFIX}basebackups/anchor/backup_manifest"
    index = next(i for i, item in enumerate(payload["objects"]) if item["key"] == key)
    native = json.loads(base64.b64decode(payload["objects"][index]["payload_base64"]))
    edit(native)
    updated = record(key, json.dumps(native, sort_keys=True).encode())
    payload["objects"][index] = updated

    def update_outer(outer):
        entry = next(item for item in outer["files"] if item["key"] == key)
        entry.update(size_bytes=updated["size_bytes"], sha256=updated["sha256"])

    change_manifest(payload, "anchor", update_outer)


@pytest.mark.parametrize("version", [999, True, 1.0, "1", None])
def test_native_manifest_requires_exact_supported_integer_version(version):
    payload = fixture_payload()
    change_postgres_manifest(
        payload, lambda native: native.update({"PostgreSQL-Backup-Manifest-Version": version})
    )
    blocked(run(payload))


@pytest.mark.parametrize(
    "field", ["PostgreSQL-Backup-Manifest-Version", "Files", "WAL-Ranges", "Manifest-Checksum"]
)
def test_native_manifest_requires_all_top_level_fields(field):
    payload = fixture_payload()
    change_postgres_manifest(payload, lambda native: native.pop(field))
    blocked(run(payload))


@pytest.mark.parametrize(
    "files",
    [
        None,
        {},
        [],
        [None],
        [{}],
        [{"Path": "PG_VERSION", "Size": True, "Last-Modified": "date"}],
        [{"Path": "PG_VERSION", "Size": 3}],
        [{"Path": "PG_VERSION", "Encoded-Path": "5047", "Size": 3, "Last-Modified": "date"}],
        [{"Encoded-Path": "abc", "Size": 3, "Last-Modified": "date"}],
        [
            {
                "Path": "PG_VERSION",
                "Size": 3,
                "Last-Modified": "date",
                "Checksum-Algorithm": "SHA256",
            }
        ],
    ],
)
def test_native_manifest_rejects_malformed_file_structures(files):
    payload = fixture_payload()
    change_postgres_manifest(payload, lambda native: native.update(Files=files))
    blocked(run(payload))


@pytest.mark.parametrize("checksum", [None, 123, "xyz", "a" * 63])
def test_native_manifest_rejects_malformed_manifest_checksum(checksum):
    payload = fixture_payload()
    change_postgres_manifest(payload, lambda native: native.update({"Manifest-Checksum": checksum}))
    blocked(run(payload))


def test_native_manifest_accepts_encoded_paths_and_optional_file_checksums():
    payload = fixture_payload()
    change_postgres_manifest(
        payload,
        lambda native: native.update(
            Files=[
                {
                    "Encoded-Path": "50475f56455253494f4e",
                    "Size": 3,
                    "Last-Modified": "date",
                    "Checksum-Algorithm": "SHA256",
                    "Checksum": "A" * 64,
                },
                {"Path": "base/1/123", "Size": 0, "Last-Modified": "date"},
            ]
        ),
    )
    assert run(payload)["status"] == "planned"


@pytest.mark.parametrize(
    "suffix", ["base.tar.gz", "pg_wal.tar.gz", "backup_manifest", "manifest.json", "history", "wal"]
)
@pytest.mark.parametrize("digest", ["0" * 64, None, "malformed"])
def test_final_head_blocks_changed_missing_or_malformed_used_sha_identity(suffix, digest):
    payload = failover_payload()
    if suffix == "history":
        changed_key = next(
            item["key"] for item in payload["objects"] if item["key"].endswith(".history")
        )
    elif suffix == "wal":
        changed_key = next(item["key"] for item in payload["objects"] if "wal_header_hex" in item)
    else:
        changed_key = f"{PREFIX}basebackups/anchor/{suffix}"

    class MetadataRace(planner.InventoryClient):
        lists = 0

        def list_objects_v2(self, **kwargs):
            self.lists += 1
            return super().list_objects_v2(**kwargs)

        def head_object(self, **kwargs):
            head = super().head_object(**kwargs)
            if self.lists >= 2 and kwargs["Key"] == changed_key:
                head["Metadata"] = {} if digest is None else {"sha256": digest}
            return head

    report = planner.plan(
        MetadataRace(payload),
        CONFIG,
        as_of=AS_OF,
        retention=timedelta(days=7),
        expected_system_identifier=SYSTEM_ID,
        required_end_wal=wal_name(5, 7),
    )
    blocked(report)
    assert any(changed_key in reason for reason in report["blocked_reasons"])
