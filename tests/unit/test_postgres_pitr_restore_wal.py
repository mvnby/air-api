import json
from dataclasses import replace

import pytest

from tests.unit.postgres_pitr_restore_test_support import (
    FakeClient,
    FakeConfig,
    OTHER_SYSTEM_IDENTIFIER,
    REQUIRED_END_WAL,
    SEGMENT_SIZE,
    START_WAL,
    SYSTEM_IDENTIFIER,
    _manifest_record,
    _postgres_backup_manifest,
    _prepare_args,
    _restore_objects,
    pitr_restore,
)


def test_postgres_backup_manifest_lineage_must_be_bracketed_by_outer_manifest():
    manifest = _manifest_record()
    postgres_manifest = json.loads(_postgres_backup_manifest())

    assert pitr_restore._validate_postgres_manifest_lineage(
        manifest,
        postgres_manifest,
    ) == ("0/400", "0/700")

    wrong_timeline = json.loads(_postgres_backup_manifest(timeline=2))
    with pytest.raises(SystemExit, match="timeline does not match"):
        pitr_restore._validate_postgres_manifest_lineage(manifest, wrong_timeline)

    with pytest.raises(SystemExit, match="does not bracket"):
        pitr_restore._validate_postgres_manifest_lineage(
            replace(manifest, start_lsn="0/500"),
            postgres_manifest,
        )

    postgres_manifest["WAL-Ranges"][0]["unexpected"] = True
    with pytest.raises(SystemExit, match="exact schema"):
        pitr_restore._validate_postgres_manifest_lineage(
            manifest,
            postgres_manifest,
        )


def test_wal_selection_is_contiguous_same_timeline_and_categorizes_history():
    history = b"1\t0/100\tdirect promotion\n"
    assert pitr_restore._wal_segment_name(
        timeline=5,
        lsn="0/400",
        segment_size_bytes=SEGMENT_SIZE,
    ) == "000000050000000000000001"
    objects = [
        pitr_restore.WalObject("old", "000000050000000000000000", SEGMENT_SIZE),
        pitr_restore.WalObject("one", "000000050000000000000001", SEGMENT_SIZE),
        pitr_restore.WalObject("two", "000000050000000000000002", SEGMENT_SIZE),
        pitr_restore.WalObject("three", "000000050000000000000003", SEGMENT_SIZE),
        pitr_restore.WalObject("after", "000000050000000000000004", SEGMENT_SIZE),
        pitr_restore.WalObject("history", "00000005.history", len(history)),
        pitr_restore.WalObject("future-history", "00000006.history", 10),
        pitr_restore.WalObject(
            "backup-history",
            "000000050000000000000002.00000010.backup",
            10,
        ),
        pitr_restore.WalObject("future", "000000060000000000000001", SEGMENT_SIZE),
    ]

    selected = pitr_restore._select_wal_objects(
        objects,
        start_wal_name="000000050000000000000001",
        start_lsn="0/400",
        required_end_wal="000000050000000000000003",
        segment_size_bytes=SEGMENT_SIZE,
        history_loader=lambda _item: history,
    )

    assert [item.key for item in selected.segments] == ["one", "two", "three"]
    assert [item.key for item in selected.history_files] == ["history"]
    assert [item.key for item in selected.backup_history_files] == [
        "backup-history"
    ]
    assert "future" not in [item.key for item in selected.objects]
    assert "future-history" not in [item.key for item in selected.objects]
    assert "old" not in [item.key for item in selected.objects]
    assert "after" not in [item.key for item in selected.objects]


def test_wal_selection_rejects_a_gap_and_missing_descendant_history():
    history = b"1\t0/100\tdirect promotion\n"
    objects = [
        pitr_restore.WalObject("history", "00000005.history", len(history)),
        pitr_restore.WalObject("one", "000000050000000000000001", SEGMENT_SIZE),
        pitr_restore.WalObject("three", "000000050000000000000003", SEGMENT_SIZE),
    ]

    with pytest.raises(SystemExit, match="gap at 000000050000000000000002"):
        pitr_restore._select_wal_objects(
            objects,
            start_wal_name="000000050000000000000001",
            start_lsn="0/400",
            required_end_wal="000000050000000000000003",
            segment_size_bytes=SEGMENT_SIZE,
            history_loader=lambda _item: history,
        )

    with pytest.raises(SystemExit, match="Missing PostgreSQL timeline history"):
        pitr_restore._select_wal_objects(
            objects,
            start_wal_name="000000050000000000000001",
            start_lsn="0/400",
            required_end_wal="000000060000000000000003",
            segment_size_bytes=SEGMENT_SIZE,
            history_loader=lambda _item: history,
        )


def test_wal_selection_excludes_an_invalid_future_timeline_segment():
    large_segment_size = 1024 * 1024 * 1024
    history = b"1\t0/100\tdirect promotion\n"
    selected = pitr_restore._select_wal_objects(
        [
            pitr_restore.WalObject(
                "start",
                "000000050000000000000000",
                large_segment_size,
            ),
            pitr_restore.WalObject("history", "00000005.history", len(history)),
            pitr_restore.WalObject(
                "invalid-future",
                "0000000600000000000000FF",
                large_segment_size,
            ),
        ],
        start_wal_name="000000050000000000000000",
        start_lsn="0/100",
        required_end_wal="000000050000000000000000",
        segment_size_bytes=large_segment_size,
        history_loader=lambda _item: history,
    )

    assert [item.key for item in selected.segments] == ["start"]


def test_wal_listing_rejects_noncanonical_object_keys():
    wal_name = "000000010000000000000001"
    client = FakeClient(
        {f"postgres/pitr/mvn-api/wal/wrong/{wal_name}": b"x" * SEGMENT_SIZE}
    )

    with pytest.raises(SystemExit, match="Noncanonical PITR WAL object key"):
        pitr_restore._list_wal_objects(client, FakeConfig)


def test_wal_listing_has_a_hard_object_count_limit(monkeypatch):
    monkeypatch.setattr(pitr_restore, "MAX_LISTED_WAL_OBJECTS", 1)
    client = FakeClient(
        {
            "postgres/pitr/mvn-api/wal/00000001/000000010000000000000001": b"1",
            "postgres/pitr/mvn-api/wal/00000001/000000010000000000000002": b"2",
        }
    )

    with pytest.raises(SystemExit, match="Too many PITR WAL objects"):
        pitr_restore._list_wal_objects(client, FakeConfig)


def test_prepare_verifies_lineage_downloads_exact_chain_and_writes_target(
    monkeypatch,
    tmp_path,
):
    objects, payload = _restore_objects()
    client = FakeClient(objects)
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda config: client)

    target_dir = tmp_path / "restore"
    assert pitr_restore.main(_prepare_args(target_dir)) == 0

    data_dir = target_dir / "data"
    assert (data_dir / "PG_VERSION").read_text() == "15\n"
    assert (target_dir / "wal" / START_WAL).read_bytes() == b"1" * SEGMENT_SIZE
    assert (target_dir / "wal" / REQUIRED_END_WAL).read_bytes() == (
        b"2" * SEGMENT_SIZE
    )
    assert not (
        target_dir / "wal" / "000000010000000000000000"
    ).exists()
    assert not (
        target_dir / "wal" / "000000010000000000000003"
    ).exists()
    assert not (
        target_dir / "wal" / "000000020000000000000001"
    ).exists()
    assert (data_dir / "recovery.signal").is_file()
    safe_conf = (target_dir / "control/postgresql.conf").read_text()
    assert "restore_command = 'cp /pitr-restore/wal/%f %p'" in safe_conf
    assert "recovery_target_action = 'pause'" in safe_conf
    assert "recovery_target_inclusive = off" in safe_conf
    assert "recovery_target_time = '2026-07-02T02:30:00+00:00'" in safe_conf
    assert "shared_preload_libraries = ''" in safe_conf
    assert "include" not in safe_conf.lower()
    assert json.loads((target_dir / "manifest.json").read_text()) == payload
    assert json.loads((target_dir / "restore-contract.json").read_text()) == {
        "schema_version": 1,
        "backup_id": "backup-1",
        "expected_system_identifier": SYSTEM_IDENTIFIER,
        "timeline": 1,
        "target_mode": "time",
        "target_time": "2026-07-02T02:30:00Z",
        "target_name": "",
        "target_lsn": "",
        "start_wal": START_WAL,
        "required_end_wal": REQUIRED_END_WAL,
        "selected_segments": 2,
    }


def test_prepare_rejects_wrong_system_identifier(monkeypatch, tmp_path):
    objects, _ = _restore_objects()
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(
        pitr_restore,
        "build_client",
        lambda config: FakeClient(objects),
    )

    with pytest.raises(SystemExit, match="expected cluster"):
        pitr_restore.main(
            _prepare_args(
                tmp_path / "restore",
                expected_system_identifier=OTHER_SYSTEM_IDENTIFIER,
            )
        )


def test_prepare_rejects_required_end_wal_before_completed_backup(
    monkeypatch,
    tmp_path,
):
    objects, _ = _restore_objects()
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(
        pitr_restore,
        "build_client",
        lambda config: FakeClient(objects),
    )

    with pytest.raises(SystemExit, match="does not cover the completed basebackup"):
        pitr_restore.main(
            _prepare_args(
                tmp_path / "restore",
                required_end_wal=START_WAL,
            )
        )


def test_prepare_refuses_non_empty_target_dir(monkeypatch, tmp_path):
    target = tmp_path / "restore"
    target.mkdir()
    (target / "existing").write_text("do not overwrite")
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda config: FakeClient({}))

    with pytest.raises(SystemExit, match="Target directory must be empty"):
        pitr_restore.main(_prepare_args(target))


def test_fetch_wal_downloads_verified_canonical_object(monkeypatch, tmp_path):
    wal_name = "00000001000000000000000A"
    key = f"postgres/pitr/mvn-api/wal/00000001/{wal_name}"
    client = FakeClient({key: b"wal-bytes"})
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda config: client)

    destination = tmp_path / "pg_wal" / wal_name
    assert pitr_restore.main(
        ["fetch-wal", "--wal-name", wal_name, "--destination", str(destination)]
    ) == 0

    assert destination.read_bytes() == b"wal-bytes"
    assert key in client.gets


def test_fetch_wal_rejects_invalid_wal_name(monkeypatch, tmp_path):
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda config: FakeClient({}))

    with pytest.raises(SystemExit, match="Invalid WAL filename"):
        pitr_restore.main(
            [
                "fetch-wal",
                "--wal-name",
                "../../bad",
                "--destination",
                str(tmp_path / "bad"),
            ]
        )


def test_fetch_wal_explicitly_rejects_archived_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda config: FakeClient({}))

    with pytest.raises(SystemExit, match="Invalid WAL filename"):
        pitr_restore.main(
            [
                "fetch-wal",
                "--wal-name",
                "00000007000000000000004B.partial",
                "--destination",
                str(tmp_path / "partial"),
            ]
        )
