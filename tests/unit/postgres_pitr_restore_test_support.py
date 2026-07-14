import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts/ha/restore_postgres_pitr_from_s3.py"
)
SPEC = importlib.util.spec_from_file_location(
    "restore_postgres_pitr_from_s3",
    MODULE_PATH,
)
pitr_restore = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = pitr_restore
SPEC.loader.exec_module(pitr_restore)

SYSTEM_IDENTIFIER = "7612345678901234567"
OTHER_SYSTEM_IDENTIFIER = "8612345678901234567"
SEGMENT_SIZE = 1024
START_WAL = "000000010000000000000001"
REQUIRED_END_WAL = "000000010000000000000002"


class FakeConfig:
    bucket = "private-pitr"
    key_prefix = "postgres/pitr"
    cluster = "mvn-api"


class FakeBody:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self.payload) - self.offset
        start = self.offset
        self.offset = min(len(self.payload), self.offset + size)
        return self.payload[start : self.offset]

    def close(self) -> None:
        return None


class FakePaginator:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    def paginate(self, **kwargs):
        prefix = kwargs["Prefix"]
        return [
            {
                "Contents": [
                    {
                        "Key": key,
                        "Size": len(content),
                        "LastModified": datetime(2026, 7, 2, tzinfo=timezone.utc),
                    }
                    for key, content in self.objects.items()
                    if key.startswith(prefix)
                ]
            }
        ]


class FakeClient:
    def __init__(
        self,
        objects: dict[str, bytes],
        *,
        metadata: dict[str, dict[str, str]] | None = None,
    ):
        self.objects = objects
        self.metadata = metadata or {
            key: {"sha256": hashlib.sha256(content).hexdigest()}
            for key, content in objects.items()
        }
        self.gets: list[str] = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self.objects)

    def head_object(self, *, Bucket, Key):
        assert Bucket == FakeConfig.bucket
        return {
            "ContentLength": len(self.objects[Key]),
            "Metadata": self.metadata.get(Key, {}),
        }

    def get_object(self, *, Bucket, Key):
        assert Bucket == FakeConfig.bucket
        self.gets.append(Key)
        return {
            "ContentLength": len(self.objects[Key]),
            "Body": FakeBody(self.objects[Key]),
        }


def _tar_gz(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _postgres_backup_manifest(
    *,
    timeline: int = 1,
    start_lsn: str = "0/400",
    end_lsn: str = "0/700",
) -> bytes:
    return json.dumps(
        {
            "PostgreSQL-Backup-Manifest-Version": 1,
            "Files": [
                {"Path": "PG_VERSION", "Size": 3},
                {"Path": "postgresql.conf", "Size": 0},
            ],
            "WAL-Ranges": [
                {
                    "Timeline": timeline,
                    "Start-LSN": start_lsn,
                    "End-LSN": end_lsn,
                }
            ],
        },
        sort_keys=True,
    ).encode("utf-8")


def _file_entry(backup_id: str, name: str, content: bytes) -> dict:
    return {
        "name": name,
        "key": f"postgres/pitr/mvn-api/basebackups/{backup_id}/{name}",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _outer_payload(
    backup_id: str,
    files: list[dict],
    *,
    system_identifier: str = SYSTEM_IDENTIFIER,
    timeline: int = 1,
    start_lsn: str = "0/0",
    end_lsn: str = "0/800",
    started_at: str = "2026-07-02T01:00:00Z",
    completed_at: str = "2026-07-02T01:05:00Z",
) -> dict:
    return {
        "schema_version": 1,
        "backup_id": backup_id,
        "cluster": "mvn-api",
        "system_identifier": system_identifier,
        "timeline": timeline,
        "start_lsn": start_lsn,
        "end_lsn": end_lsn,
        "started_at": started_at,
        "completed_at": completed_at,
        "source_node": "mvn-api",
        "files": files,
    }


def _manifest_key(backup_id: str) -> str:
    return f"postgres/pitr/mvn-api/basebackups/{backup_id}/manifest.json"


def _minimal_payload(backup_id: str = "backup-1") -> dict:
    base_tar = _tar_gz({"PG_VERSION": b"15\n"})
    backup_manifest = _postgres_backup_manifest()
    return _outer_payload(
        backup_id,
        [
            _file_entry(backup_id, "backup_manifest", backup_manifest),
            _file_entry(backup_id, "base.tar.gz", base_tar),
        ],
    )


def _restore_objects(
    *,
    backup_id: str = "backup-1",
    system_identifier: str = SYSTEM_IDENTIFIER,
    timeline: int = 1,
    start_lsn: str = "0/0",
    end_lsn: str = "0/800",
    postgres_timeline: int = 1,
    postgres_start_lsn: str = "0/400",
    postgres_end_lsn: str = "0/700",
) -> tuple[dict[str, bytes], dict]:
    base_tar = _tar_gz(
        {
            "PG_VERSION": b"15\n",
            "postgresql.conf": b"",
            "postgresql.auto.conf": b"shared_buffers = '128MB'\n",
        }
    )
    backup_manifest = _postgres_backup_manifest(
        timeline=postgres_timeline,
        start_lsn=postgres_start_lsn,
        end_lsn=postgres_end_lsn,
    )
    metadata = json.dumps({"backup_id": backup_id}, sort_keys=True).encode()
    files = [
        _file_entry(backup_id, "backup_manifest", backup_manifest),
        _file_entry(backup_id, "base.tar.gz", base_tar),
        _file_entry(backup_id, "metadata.json", metadata),
    ]
    payload = _outer_payload(
        backup_id,
        files,
        system_identifier=system_identifier,
        timeline=timeline,
        start_lsn=start_lsn,
        end_lsn=end_lsn,
    )
    objects = {
        _manifest_key(backup_id): json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        ).encode(),
        files[0]["key"]: backup_manifest,
        files[1]["key"]: base_tar,
        files[2]["key"]: metadata,
        "postgres/pitr/mvn-api/wal/00000001/000000010000000000000000": (
            b"0" * SEGMENT_SIZE
        ),
        f"postgres/pitr/mvn-api/wal/00000001/{START_WAL}": b"1" * SEGMENT_SIZE,
        f"postgres/pitr/mvn-api/wal/00000001/{REQUIRED_END_WAL}": (
            b"2" * SEGMENT_SIZE
        ),
        "postgres/pitr/mvn-api/wal/00000001/000000010000000000000003": (
            b"3" * SEGMENT_SIZE
        ),
        "postgres/pitr/mvn-api/wal/00000002/000000020000000000000001": (
            b"future" * 32
        ),
        "postgres/pitr/mvn-api/wal/00000002/00000002.history": b"future-history",
    }
    return objects, payload


def _manifest_record(**changes) -> object:
    payload = _minimal_payload()
    record = pitr_restore._validate_outer_manifest(
        payload=payload,
        manifest_key=_manifest_key("backup-1"),
        config=FakeConfig,
        expected_system_identifier=SYSTEM_IDENTIFIER,
    )
    return replace(record, **changes)


def _prepare_args(target_dir: Path, **overrides: str) -> list[str]:
    values = {
        "backup_id": "backup-1",
        "target_time": "2026-07-02T02:30:00Z",
        "expected_system_identifier": SYSTEM_IDENTIFIER,
        "required_end_wal": REQUIRED_END_WAL,
    }
    values.update(overrides)
    return [
        "prepare",
        "--target-dir",
        str(target_dir),
        "--backup-id",
        values["backup_id"],
        "--target-time",
        values["target_time"],
        "--expected-system-identifier",
        values["expected_system_identifier"],
        "--required-end-wal",
        values["required_end_wal"],
        "--wal-segment-size-bytes",
        str(SEGMENT_SIZE),
        "--min-free-bytes",
        "0",
    ]
