import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/ha/check_postgres_pitr_remote.py"
SPEC = importlib.util.spec_from_file_location("check_postgres_pitr_remote", MODULE_PATH)
assert SPEC and SPEC.loader
pitr_remote = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pitr_remote
SPEC.loader.exec_module(pitr_remote)


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **kwargs):
        assert kwargs["Bucket"] == "private"
        assert kwargs["Prefix"] == "postgres/pitr/mvn-api/wal/"
        yield from self.pages


class FakeClient:
    def __init__(self, pages):
        self.pages = pages

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self.pages)


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
