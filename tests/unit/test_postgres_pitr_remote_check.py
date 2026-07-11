import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


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
    def __init__(self, pages_by_prefix):
        self.pages_by_prefix = pages_by_prefix

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        pages_by_prefix = self.pages_by_prefix

        class PrefixPaginator:
            def paginate(self, **kwargs):
                assert kwargs["Bucket"] == "private"
                yield from pages_by_prefix.get(kwargs["Prefix"], [])

        return PrefixPaginator()


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


def test_object_exists_requires_exact_key():
    key = "postgres/pitr/mvn-api/wal/00000001/00000001000000000000000A"
    client = FakeClient(
        [
            {
                "Contents": [
                    {"Key": f"{key}.backup", "LastModified": datetime.now(timezone.utc)},
                    {"Key": key, "LastModified": datetime.now(timezone.utc)},
                ]
            }
        ]
    )

    assert pitr_remote._object_exists(client, "private", key) is True


def test_object_exists_rejects_prefix_only_match():
    key = "postgres/pitr/mvn-api/wal/00000001/00000001000000000000000A"
    client = FakeClient(
        [
            {
                "Contents": [
                    {
                        "Key": f"{key}.backup",
                        "LastModified": datetime.now(timezone.utc),
                    }
                ]
            }
        ]
    )

    assert pitr_remote._object_exists(client, "private", key) is False


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
        "Size": 16,
    }
    client = PrefixClient(
        {
            expected_key: [{"Contents": [item]}],
            wal_prefix: [{"Contents": [item]}],
        }
    )

    assert _run_wal_check(monkeypatch, client, wal) == 0
    output = capsys.readouterr().out
    assert "pitr_remote_wal_expected status=present" in output
    assert "pitr_remote_wal status=idle" in output
    assert "pitr_remote_summary status=passed failures=0 warnings=1" in output


def test_main_fails_when_expected_wal_is_missing(monkeypatch, capsys):
    wal = "00000001000000000000000A"
    wal_prefix = "postgres/pitr/mvn-api/wal/"
    expected_key = f"{wal_prefix}00000001/{wal}"
    latest_item = {
        "Key": f"{wal_prefix}00000001/000000010000000000000009",
        "LastModified": datetime.now(timezone.utc),
        "Size": 16,
    }
    client = PrefixClient(
        {
            expected_key: [{"Contents": []}],
            wal_prefix: [{"Contents": [latest_item]}],
        }
    )

    assert _run_wal_check(monkeypatch, client, wal) == 1
    output = capsys.readouterr().out
    assert "pitr_remote_wal_expected status=missing" in output
    assert "pitr_remote_wal status=stale" in output
    assert "pitr_remote_summary status=failed failures=2 warnings=0" in output
