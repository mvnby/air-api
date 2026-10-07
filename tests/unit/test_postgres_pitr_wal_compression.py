"""Storage roundtrips using PG15 page geometry, without a database server."""
import argparse
import base64
import gzip
import hashlib
import io
import struct
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.ha import postgres_pitr_immutable_upload as storage
from scripts.ha import postgres_pitr_wal_lineage as lineage
from scripts.ha import upload_postgres_pitr_to_s3 as upload
from tests.unit import test_postgres_pitr_retention as retention
from tests.unit.postgres_pitr_restore_test_support import FakeConfig, pitr_restore

SIZE = 16 * 1024**2
NAME = "000000010000000000000001"
KEY = f"postgres/pitr/mvn-api/wal/00000001/{NAME}"
CONFIG = upload.PitrS3Config(FakeConfig.bucket, "https://private.invalid", "auto", "key", "secret", "postgres/pitr", "mvn-api")


def wal_bytes(timeline=1, position=1, endian="<", header_timeline=None):
    """Long first header and short continuation page headers at PG15 addresses.

    Synthetic page contents prove byte preservation/identity, not replayability.
    """
    data = bytearray(SIZE)
    struct.pack_into(endian + "HHIQI4xQII", data, 0, 0xD110, 2,
                     header_timeline or timeline, position * SIZE, 0,
                     int(retention.SYSTEM_ID), SIZE, 8192)
    for offset in range(8192, SIZE, 8192):
        struct.pack_into(endian + "HHIQI", data, offset, 0xD110, 0, timeline,
                         position * SIZE + offset, 0)
    payload = b"MVN synthetic WAL page payload!"
    data[100:100 + len(payload)] = payload
    return bytes(data)


@pytest.fixture(scope="module")
def original():
    return wal_bytes()


def metadata(data, encoded):
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "uploaded-by": "mvn-postgres-pitr",
            "wal-format": "1", "wal-codec": "gzip", "wal-name": NAME,
            "wal-size": str(len(data)), "wal-sha256": hashlib.sha256(data).hexdigest()}


class Missing(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class Client:
    def __init__(self):
        self.objects = {}
        self.metadata = {}
        self.puts = []
        self.bodies = []

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise Missing()
        return {"ContentLength": len(self.objects[Key]), "ETag": self.etag(Key),
                "LastModified": datetime.now(timezone.utc), "Metadata": dict(self.metadata[Key])}

    def etag(self, key):
        return '"' + hashlib.sha256(self.objects[key]).hexdigest() + '"'

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        assert kwargs["IfNoneMatch"] == "*"
        assert key not in self.objects
        data = kwargs["Body"].read()
        assert len(data) == kwargs["ContentLength"]
        self.objects[key], self.metadata[key] = data, dict(kwargs["Metadata"])
        self.puts.append(key)

    def get_object(self, *, Bucket, Key, IfMatch=None):
        if IfMatch is not None:
            assert IfMatch == self.etag(Key)
        body = io.BytesIO(self.objects[Key])
        self.bodies.append(body)
        return {"ContentLength": len(self.objects[Key]), "ETag": self.etag(Key), "Body": body}

    def get_paginator(self, _name):
        return self

    def paginate(self, **kwargs):
        return [{"Contents": [{"Key": k, "Size": len(v)} for k, v in self.objects.items()
                               if k.startswith(kwargs["Prefix"])]}]


def compressed_client(original, encoded=None):
    client = Client()
    data = gzip.compress(original, mtime=0) if encoded is None else encoded
    client.objects[KEY + ".gz"] = data
    client.metadata[KEY + ".gz"] = metadata(original, data)
    return client


def upload_args(directory, **kwargs):
    return argparse.Namespace(archive_dir=str(directory), dry_run=False, delete_after_upload=False,
                              wal_compression="gzip", **kwargs)


def test_upload_repeat_is_deterministic_and_restores_original(monkeypatch, tmp_path, original):
    source = tmp_path / NAME
    source.write_bytes(original)
    client = Client()
    monkeypatch.setattr(upload, "load_config", lambda: CONFIG)
    monkeypatch.setattr(upload, "build_client", lambda _: client)
    assert upload.upload_wal(upload_args(tmp_path)) == 0
    first = client.objects[KEY + ".gz"]
    source.touch()
    args = upload_args(tmp_path)
    args.delete_after_upload = True
    assert upload.upload_wal(args) == 0
    assert client.objects[KEY + ".gz"] == first
    assert first[4:8] == b"\0" * 4
    assert client.puts == [KEY + ".gz"]
    assert not source.exists()
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda _: client)
    destination = tmp_path / "restored" / NAME
    assert pitr_restore.main(["fetch-wal", "--wal-name", NAME, "--destination", str(destination)]) == 0
    assert destination.read_bytes() == original
    assert all(body.closed for body in client.bodies)


def test_upload_failure_keeps_source_and_cleans_temporary(monkeypatch, tmp_path, original):
    source = tmp_path / NAME
    source.write_bytes(original)
    client = Client()
    directories = []
    real_temp = upload.tempfile.TemporaryDirectory

    def temporary(**kwargs):
        result = real_temp(dir=tmp_path, **kwargs)
        directories.append(Path(result.name))
        return result

    monkeypatch.setattr(upload.tempfile, "TemporaryDirectory", temporary)
    monkeypatch.setattr(upload, "load_config", lambda: CONFIG)
    monkeypatch.setattr(upload, "build_client", lambda _: client)
    monkeypatch.setattr(client, "put_object", lambda **_: (_ for _ in ()).throw(RuntimeError("network failed")))
    args = upload_args(tmp_path)
    args.delete_after_upload = True
    with pytest.raises(RuntimeError, match="network failed"):
        upload.upload_wal(args)
    assert source.read_bytes() == original
    assert directories and all(not p.exists() for p in directories)


@pytest.mark.parametrize("failure", ["crc", "truncated", "trailing", "members", "stored_digest", "original_digest", "decoded_short", "bomb"])
def test_invalid_gzip_never_publishes_destination(tmp_path, original, failure):
    encoded = gzip.compress(original, mtime=0)
    if failure == "crc":
        encoded = encoded[:-8] + bytes([encoded[-8] ^ 1]) + encoded[-7:]
    elif failure == "truncated":
        encoded = encoded[:-1]
    elif failure == "trailing":
        encoded += b"junk"
    elif failure == "members":
        encoded += gzip.compress(b"more", mtime=0)
    elif failure == "decoded_short":
        encoded = gzip.compress(original[:-1], mtime=0)
    elif failure == "bomb":
        encoded = gzip.compress(original + b"\0" * SIZE, mtime=0)
    client = compressed_client(original, encoded)
    if failure in {"stored_digest", "original_digest"}:
        client.metadata[KEY + ".gz"]["sha256" if failure == "stored_digest" else "wal-sha256"] = "0" * 64
    destination = tmp_path / NAME
    destination.write_bytes(b"previous valid destination")
    with pytest.raises(SystemExit):
        storage.download_gzip_wal(client, bucket=CONFIG.bucket, key=KEY + ".gz",
                                  head=client.head_object(Bucket=CONFIG.bucket, Key=KEY + ".gz"), destination=destination)
    assert destination.read_bytes() == b"previous valid destination"
    assert list(tmp_path.iterdir()) == [destination]
    assert client.bodies[-1].closed


@pytest.mark.parametrize("field,value", [("wal-codec", "zstd"), ("wal-format", "2"), ("wal-size", str(2**31)),
                                        ("wal-size", "16777217"), ("wal-name", "0" * 24), ("wal-sha256", "bad")])
def test_invalid_contract_is_rejected_before_get(original, field, value):
    client = compressed_client(original)
    client.metadata[KEY + ".gz"][field] = value
    with pytest.raises(SystemExit, match="contract"):
        storage.read_gzip_wal(client, bucket=CONFIG.bucket, key=KEY + ".gz",
                             head=client.head_object(Bucket=CONFIG.bucket, Key=KEY + ".gz"))
    assert not client.bodies


def test_decode_has_bounded_output_chunks(monkeypatch, original):
    client = compressed_client(original)
    monkeypatch.setattr(storage, "STREAM_CHUNK_BYTES", 4096)
    sizes = []
    sink = type("Sink", (), {"write": lambda self, chunk: sizes.append(len(chunk))})()
    header = storage.read_gzip_wal(client, bucket=CONFIG.bucket, key=KEY + ".gz",
                                  head=client.head_object(Bucket=CONFIG.bucket, Key=KEY + ".gz"), output=sink)
    assert header == original[:40]
    assert sum(sizes) == SIZE and max(sizes) <= 4096


def test_dual_representations_block_upload_restore_and_selection(monkeypatch, tmp_path, original):
    client = compressed_client(original)
    client.objects[KEY] = original
    client.metadata[KEY] = {"sha256": hashlib.sha256(original).hexdigest(), "uploaded-by": "mvn-postgres-pitr"}
    (tmp_path / NAME).write_bytes(original)
    monkeypatch.setattr(upload, "load_config", lambda: CONFIG)
    monkeypatch.setattr(upload, "build_client", lambda _: client)
    with pytest.raises(RuntimeError, match="Conflicting"):
        upload.upload_wal(upload_args(tmp_path))
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda _: client)
    with pytest.raises(SystemExit, match="Conflicting"):
        pitr_restore.main(["fetch-wal", "--wal-name", NAME, "--destination", str(tmp_path / "out")])
    with pytest.raises(SystemExit, match="Duplicate"):
        pitr_restore._list_wal_objects(client, FakeConfig)
    assert (tmp_path / NAME).exists() and not client.puts


def convert_record(record):
    name = record["key"].rsplit("/", 1)[-1]
    data = bytearray(wal_bytes(int(name[:8], 16), int(name[16:24], 16)))
    data[:40] = bytes.fromhex(record["wal_header_hex"])
    encoded = gzip.compress(data, mtime=0)
    result = retention.record(record["key"] + ".gz", encoded)
    result["metadata"] = metadata(data, encoded)
    result["metadata"]["wal-name"] = name
    return result


@pytest.mark.parametrize("mode", ["raw", "gzip", "mixed", "failover"])
def test_planner_supports_raw_compressed_mixed_and_failover(mode):
    payload = retention.failover_payload() if mode == "failover" else retention.fixture_payload()
    for index, record in enumerate(payload["objects"]):
        if "wal_header_hex" in record and (mode in {"gzip", "failover"} or mode == "mixed" and index % 2):
            payload["objects"][index] = convert_record(record)
    report = retention.run(payload, required_end_wal=retention.wal_name(5 if mode == "failover" else 1, 7))
    assert report["status"] == "planned", report["blocked_reasons"]
    assert len(report["candidates"]) == 6
    assert report["candidate_bytes"] == sum(r["size_bytes"] for r in report["candidates"])


@pytest.mark.parametrize("failure", ["duplicate", "codec", "corruption", "identity"])
def test_planner_compressed_uncertainty_clears_all_candidates(failure):
    payload = retention.fixture_payload()
    index = next(i for i, r in enumerate(payload["objects"]) if "wal_header_hex" in r)
    old = payload["objects"][index]
    compressed = convert_record(old)
    payload["objects"][index] = compressed
    if failure == "duplicate":
        payload["objects"].append(old)
    elif failure == "codec":
        compressed["metadata"]["wal-codec"] = "zstd"
    elif failure == "corruption":
        raw = base64.b64decode(compressed["payload_base64"])
        compressed["payload_base64"] = base64.b64encode(raw[:-1] + bytes([raw[-1] ^ 1])).decode()
    if failure != "identity":
        retention.blocked(retention.run(payload))
        return
    client = retention.planner.InventoryClient(payload)
    final_key = payload["objects"][-1]["key"]
    changed = False
    original_head = client.head_object

    def head(**kwargs):
        nonlocal changed
        result = original_head(**kwargs)
        # The last unclassified key is HEADed only in final validation. Change
        # compressed decoded identity after its stream has already verified.
        if kwargs["Key"] == final_key:
            changed = True
        if changed and kwargs["Key"] == compressed["key"]:
            result["Metadata"]["wal-sha256"] = "f" * 64
        return result

    client.head_object = head
    report = retention.planner.plan(client, retention.CONFIG, as_of=retention.AS_OF,
                                   retention=retention.timedelta(days=7), expected_system_identifier=retention.SYSTEM_ID,
                                   required_end_wal=retention.wal_name(1, 7))
    retention.blocked(report)
    assert "identity changed" in " ".join(report["blocked_reasons"])


def test_compressed_listing_identity_cannot_change_before_download(tmp_path, original):
    client = compressed_client(original)
    item = pitr_restore._list_wal_objects(client, FakeConfig)[0]
    client.metadata[item.key]["wal-sha256"] = "f" * 64
    with pytest.raises(SystemExit, match="identity changed since listing"):
        pitr_restore._download_wal(client, FakeConfig, item, tmp_path / NAME)
    assert not client.bodies


@pytest.mark.parametrize("mode", ["raw", "gzip", "mixed"])
def test_prepare_materializes_identical_original_chain(monkeypatch, tmp_path, mode):
    from tests.unit.postgres_pitr_restore_test_support import _restore_objects, _prepare_args
    objects, _ = _restore_objects(start_lsn="0/1000000", end_lsn="0/1000800",
                                  postgres_start_lsn="0/1000400", postgres_end_lsn="0/1000700")
    client = Client()
    for key, data in objects.items():
        if "/wal/" not in key:
            client.objects[key] = data
            client.metadata[key] = {"sha256": hashlib.sha256(data).hexdigest()}
    originals = {}
    for position in (1, 2):
        name = retention.wal_name(1, position)
        key = retention.wal_key(1, position)
        data = wal_bytes(position=position)
        originals[name] = data
        if mode == "gzip" or mode == "mixed" and position == 2:
            encoded = gzip.compress(data, mtime=0)
            client.objects[key + ".gz"] = encoded
            client.metadata[key + ".gz"] = metadata(data, encoded)
            client.metadata[key + ".gz"]["wal-name"] = name
        else:
            client.objects[key] = data
            client.metadata[key] = {"sha256": hashlib.sha256(data).hexdigest()}
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda _: client)
    target = tmp_path / mode
    args = _prepare_args(target, required_end_wal=retention.wal_name(1, 2))
    args[args.index("--wal-segment-size-bytes") + 1] = str(SIZE)
    assert pitr_restore.main(args) == 0
    for name, data in originals.items():
        assert (target / "wal" / name).read_bytes() == data
    assert not list((target / "wal").glob("*.gz"))


def test_unknown_suffix_and_raw_codec_metadata_fail_closed(tmp_path, original):
    with pytest.raises(SystemExit, match="Unsupported WAL storage codec"):
        storage.wal_storage_name(NAME + ".zstd")
    client = Client()
    client.objects[KEY] = original
    client.metadata[KEY] = {"sha256": hashlib.sha256(original).hexdigest(), "wal-codec": "zstd"}
    with pytest.raises(SystemExit, match="Unsupported raw WAL codec"):
        pitr_restore._download_wal(client, FakeConfig, lineage.WalObject(KEY, NAME, SIZE), tmp_path / NAME)
    assert not client.bodies


@pytest.mark.parametrize("changed", ["wal-sha256", "wal-size", "sha256"])
def test_stream_rejects_changed_final_head_even_with_same_etag(original, changed):
    client = compressed_client(original)
    head = client.head_object(Bucket=CONFIG.bucket, Key=KEY + ".gz")
    client.metadata[KEY + ".gz"][changed] = "0" * 64
    with pytest.raises(SystemExit, match="identity changed"):
        storage.read_gzip_wal(client, bucket=CONFIG.bucket, key=KEY + ".gz", head=head)


def test_repeat_upload_rejects_changed_decoded_identity_and_retains_source(monkeypatch, tmp_path, original):
    client = Client()
    (tmp_path / NAME).write_bytes(original)
    monkeypatch.setattr(upload, "load_config", lambda: CONFIG)
    monkeypatch.setattr(upload, "build_client", lambda _: client)
    args = upload_args(tmp_path)
    upload.upload_wal(args)
    client.metadata[KEY + ".gz"]["wal-sha256"] = "f" * 64
    args.delete_after_upload = True
    with pytest.raises(RuntimeError, match="different PITR object"):
        upload.upload_wal(args)
    assert (tmp_path / NAME).read_bytes() == original and len(client.puts) == 1


def test_dry_run_preserves_source_and_uses_no_s3(monkeypatch, tmp_path, original):
    (tmp_path / NAME).write_bytes(original)
    client = Client()
    monkeypatch.setattr(upload, "load_config", lambda: CONFIG)
    monkeypatch.setattr(upload, "build_client", lambda _: client)
    monkeypatch.setattr(client, "head_object", lambda **_: pytest.fail("dry-run HEAD"))
    args = upload_args(tmp_path)
    args.dry_run = True
    args.delete_after_upload = True
    assert upload.upload_wal(args) == 0
    assert (tmp_path / NAME).exists() and not client.objects


@pytest.mark.parametrize("variant", ["gzip", "duplicate", "unknown"])
def test_remote_monitor_understands_gzip_and_rejects_conflicts(monkeypatch, capsys, original, variant):
    from tests.unit.test_postgres_pitr_remote_check import PrefixClient, _run_wal_check
    client = compressed_client(original)
    head = client.head_object(Bucket=CONFIG.bucket, Key=KEY + ".gz")
    heads = {KEY + ".gz": head}
    if variant == "duplicate":
        heads[KEY] = {"ContentLength": SIZE, "Metadata": {"sha256": "a" * 64, "uploaded-by": "mvn-postgres-pitr"},
                      "LastModified": datetime.now(timezone.utc)}
    elif variant == "unknown":
        head["Metadata"]["wal-codec"] = "zstd"
    remote = PrefixClient({}, heads=heads)
    assert _run_wal_check(monkeypatch, remote, NAME) == (0 if variant == "gzip" else 1)
    output = capsys.readouterr().out
    assert ("status=present" if variant == "gzip" else "status=invalid") in output
    assert not remote.get_calls


def test_default_uploader_keeps_raw_format(monkeypatch, tmp_path, original):
    (tmp_path / NAME).write_bytes(original)
    client = Client()
    monkeypatch.setattr(upload, "load_config", lambda: CONFIG)
    monkeypatch.setattr(upload, "build_client", lambda _: client)
    args = upload_args(tmp_path)
    del args.wal_compression
    assert upload.upload_wal(args) == 0
    assert client.objects == {KEY: original}
    assert "wal-codec" not in client.metadata[KEY]


def test_changed_source_after_get_is_never_deleted(monkeypatch, tmp_path, original):
    source = tmp_path / NAME
    source.write_bytes(original)
    client = Client()
    get = client.get_object

    def changed_source(**kwargs):
        source.touch()
        return get(**kwargs)

    monkeypatch.setattr(client, "get_object", changed_source)
    monkeypatch.setattr(upload, "load_config", lambda: CONFIG)
    monkeypatch.setattr(upload, "build_client", lambda _: client)
    args = upload_args(tmp_path)
    args.delete_after_upload = True
    with pytest.raises(RuntimeError, match="changed during upload"):
        upload.upload_wal(args)
    assert source.exists()


def test_incompressible_segment_still_roundtrips(tmp_path, original):
    import random
    data = bytearray(random.Random(893).randbytes(SIZE))
    data[:40] = original[:40]
    for offset in range(8192, SIZE, 8192):
        data[offset:offset + 24] = original[offset:offset + 24]
    source = tmp_path / NAME
    source.write_bytes(data)
    client = Client()
    upload.upload_gzip_wal(client, CONFIG, source, KEY + ".gz", False)
    head = client.head_object(Bucket=CONFIG.bucket, Key=KEY + ".gz")
    contract = storage.gzip_wal_contract(head, key=KEY + ".gz")
    assert contract.original_size == SIZE
    output = tmp_path / "decoded"
    storage.download_gzip_wal(client, bucket=CONFIG.bucket, key=KEY + ".gz", head=head, destination=output)
    assert output.read_bytes() == data


def test_legacy_lineage_caller_cannot_silently_skip_gzip(original):
    client = compressed_client(original)
    with pytest.raises(SystemExit, match="storage codec helper is required"):
        lineage.list_wal_objects(client, bucket=CONFIG.bucket,
                                 prefix="postgres/pitr/mvn-api/wal/", max_objects=100)
