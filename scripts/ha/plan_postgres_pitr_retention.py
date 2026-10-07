#!/usr/bin/env python3
"""Report-only PITR retention planning; no mutation methods or activation path."""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import struct
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ha import postgres_pitr_artifact_security as security
from scripts.ha import postgres_pitr_immutable_upload as storage
from scripts.ha import postgres_pitr_wal_lineage as lineage
from scripts.ha import restore_postgres_pitr_from_s3 as restore

MAX_OBJECTS = 262144
MAX_INVENTORY_BYTES = 64 * 1024 * 1024
WAL_HEADER_BYTES = 40
# PostgreSQL 15, 64-bit MAXALIGN layout: access/xlog_internal.h.
PG15_WAL_MAGIC = 0xD110


@dataclass(frozen=True)
class Object:
    key: str
    size_bytes: int
    etag: str


class ProofIdentityClient:
    """Remember every HEAD identity consumed by the calculation and its helpers."""

    def __init__(self, client: Any):
        self.client = client
        self.identities: dict[str, tuple] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    def head_object(self, **kwargs: Any) -> dict:
        head = self.client.head_object(**kwargs)
        key = kwargs["Key"]
        digest = (head.get("Metadata") or {}).get("sha256")
        if not isinstance(digest, str) or not security.SHA256_RE.fullmatch(digest):
            raise ValueError(f"invalid proof SHA256 identity: {key}")
        identity = (head.get("ContentLength"), head.get("ETag"), head.get("VersionId"), digest,
                    tuple(sorted((head.get("Metadata") or {}).items())))
        previous = self.identities.setdefault(key, identity)
        if identity != previous:
            raise ValueError(f"proof identity changed during planning: {key}")
        return head


def parse_as_of(raw: str) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", raw):
        raise ValueError("as-of requires ISO 8601 seconds and an explicit timezone")
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return value.astimezone(timezone.utc)


def list_inventory(client: Any, config: Any) -> list[Object]:
    """Use explicit continuation tokens, rejecting partial/malformed listings."""
    if (
        not isinstance(config.key_prefix, str)
        or not isinstance(config.cluster, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", config.key_prefix)
        or not re.fullmatch(r"[A-Za-z0-9_-]+", config.cluster)
    ):
        raise ValueError("PITR inventory namespace is invalid")
    prefix = f"{config.key_prefix}/{config.cluster}/"
    objects: dict[str, Object] = {}
    tokens: set[str] = set()
    token = None
    while True:
        args = dict(Bucket=config.bucket, Prefix=prefix, MaxKeys=1000)
        if token is not None:
            args["ContinuationToken"] = token
        page = client.list_objects_v2(**args)
        if not isinstance(page, dict) or type(page.get("IsTruncated")) is not bool:
            raise ValueError("listing has no explicit completion status")
        contents = page.get("Contents", [])
        if not isinstance(contents, list) or len(contents) > 1000:
            raise ValueError("listing contents are invalid")
        for raw in contents:
            key, size, etag = raw.get("Key"), raw.get("Size"), raw.get("ETag")
            if (
                not isinstance(key, str)
                or not key.startswith(prefix)
                or any(ord(c) < 32 for c in key)
                or type(size) is not int
                or size < 0
                or not isinstance(etag, str)
                or not etag
            ):
                raise ValueError("listing object identity is invalid")
            if key in objects:
                raise ValueError(f"duplicate inventory key: {key}")
            objects[key] = Object(key, size, etag)
            if len(objects) > MAX_OBJECTS:
                raise ValueError("inventory exceeds object limit")
        if not page["IsTruncated"]:
            if page.get("NextContinuationToken"):
                raise ValueError("completed listing unexpectedly has a continuation token")
            break
        token = page.get("NextContinuationToken")
        if not isinstance(token, str) or not token or token in tokens:
            raise ValueError("listing continuation is missing or repeated")
        tokens.add(token)
    return sorted(objects.values(), key=lambda item: item.key)


def check_identity(client: Any, config: Any, item: Object, digest: str | None = None) -> str:
    head = client.head_object(Bucket=config.bucket, Key=item.key)
    if (
        type(head.get("ContentLength")) is not int
        or head["ContentLength"] != item.size_bytes
        or head.get("ETag") != item.etag
        or head.get("VersionId") not in (None, "null")
    ):
        raise ValueError(f"object changed or versioned: {item.key}")
    actual = security.object_sha256(
        client, bucket=config.bucket, key=item.key, expected_size=item.size_bytes
    )
    if digest is not None and actual != digest:
        raise ValueError(f"artifact digest identity mismatch: {item.key}")
    return actual


def read_small(client: Any, config: Any, item: Object, maximum: int) -> bytes:
    digest = check_identity(client, config, item)
    return security.read_verified_object(
        client,
        bucket=config.bucket,
        key=item.key,
        expected_size=item.size_bytes,
        expected_sha256=digest,
        maximum_size=maximum,
        label=item.key,
    )


def wal_header_identity(
    payload: bytes,
    *,
    item: lineage.WalObject,
    system_identifier: str,
    segment_size: int,
    chain: tuple[int, ...],
    entries: tuple,
) -> None:
    if len(payload) != WAL_HEADER_BYTES:
        raise ValueError(f"incomplete WAL long header: {item.key}")
    endian = "<" if struct.unpack_from("<H", payload)[0] == PG15_WAL_MAGIC else ">"
    magic, flags, header_timeline, pageaddr, _rem, sysid, size, block = struct.unpack(
        endian + "HHIQI4xQII", payload
    )
    timeline, position = lineage.wal_segment_position(
        item.filename, segment_size_bytes=segment_size
    )
    if (
        magic != PG15_WAL_MAGIC
        or not flags & 2
        or flags & ~15
        or str(sysid) != system_identifier
        or size != segment_size
        or block != 8192
        or pageaddr != position * segment_size
    ):
        raise ValueError(f"WAL header cluster/geometry mismatch: {item.key}")
    # A fork segment can contain pages copied from an ancestor timeline.
    index = chain.index(timeline)
    if index and position < entries[index - 1].switch_lsn // segment_size:
        raise ValueError(f"WAL segment precedes its timeline birth: {item.key}")
    allowed = {timeline}
    for ancestor in entries[:index]:
        if pageaddr < ancestor.switch_lsn:
            allowed.add(ancestor.timeline)
    if header_timeline not in allowed:
        raise ValueError(f"WAL header timeline mismatch: {item.key}")


def read_wal_header(client: Any, config: Any, item: Object) -> bytes:
    check_identity(client, config, item)
    head = client.head_object(Bucket=config.bucket, Key=item.key)
    if any(k.startswith("wal-") for k in (head.get("Metadata") or {})):
        raise ValueError(f"unsupported raw WAL codec metadata: {item.key}")
    response = client.get_object(
        Bucket=config.bucket, Key=item.key, Range="bytes=0-39", IfMatch=item.etag
    )
    body = response["Body"]
    try:
        if (
            response.get("ETag") != item.etag
            or response.get("VersionId") not in (None, "null")
            or response.get("ContentLength") != WAL_HEADER_BYTES
            or response.get("ContentRange") != f"bytes 0-39/{item.size_bytes}"
        ):
            raise ValueError(f"WAL header response identity mismatch: {item.key}")
        return security.read_body_bounded(
            body,
            expected_size=WAL_HEADER_BYTES,
            maximum_size=WAL_HEADER_BYTES,
            label="WAL long header",
        )
    finally:
        body.close()


def _calculate(
    client: Any,
    config: Any,
    objects: list[Object],
    *,
    as_of: datetime,
    retention: timedelta,
    expected_system_identifier: str,
    required_end_wal: str,
    segment_size: int,
) -> tuple[dict[str, str], dict]:
    by_key = {item.key: item for item in objects}
    backup_prefix = restore._manifest_prefix(config)
    wal_prefix = restore._wal_prefix(config)
    groups: dict[str, list[Object]] = {}
    wal_objects = []
    reasons = {item.key: "unclassified object; conservatively retained" for item in objects}
    for item in objects:
        if item.key.startswith(backup_prefix):
            suffix = item.key[len(backup_prefix) :].split("/")
            if len(suffix) != 2 or not security.BACKUP_ID_RE.fullmatch(suffix[0]):
                raise ValueError(f"noncanonical basebackup key: {item.key}")
            groups.setdefault(suffix[0], []).append(item)
        elif item.key.startswith(wal_prefix):
            storage_name = item.key.rsplit("/", 1)[-1]
            name, codec = storage.wal_storage_name(storage_name)
            if not lineage.WAL_ARCHIVE_NAME_RE.fullmatch(name):
                continue
            if item.key != f"{wal_prefix}{name[:8]}/{storage_name}" or item.size_bytes <= 0:
                raise ValueError(f"noncanonical WAL object: {item.key}")
            if codec == "gzip":
                check_identity(client, config, item)
                contract = storage.gzip_wal_contract(client.head_object(Bucket=config.bucket, Key=item.key), key=item.key)
                wal_objects.append(lineage.WalObject(item.key, name, contract.original_size, item.size_bytes, codec))
            else:
                wal_objects.append(lineage.WalObject(item.key, name, item.size_bytes))
            reasons[item.key] = "WAL metadata/partial or position not proven obsolete"
    if len({w.filename for w in wal_objects}) != len(wal_objects):
        raise ValueError("Conflicting WAL representations / duplicate canonical name")
    if len(groups) > restore.MAX_LISTED_MANIFESTS:
        raise ValueError("too many basebackup groups")
    manifests = []
    for backup_id, group in sorted(groups.items()):
        key = f"{backup_prefix}{backup_id}/manifest.json"
        if key not in by_key:
            raise ValueError(f"missing completed manifest (possibly uploading): {backup_id}")
        check_identity(client, config, by_key[key])
        manifest = restore._load_manifest(
            client, config, key, expected_system_identifier=expected_system_identifier
        )
        if manifest is None:
            raise ValueError(f"legacy v0 has no provable lineage: {backup_id}")
        if type(manifest.payload["schema_version"]) is not int:
            raise ValueError(f"manifest schema version is not an integer: {backup_id}")
        expected_keys = {key, *(entry.key for entry in manifest.files)}
        if {item.key for item in group} != expected_keys:
            raise ValueError(f"backup artifacts missing or unmanifested: {backup_id}")
        for entry in manifest.files:
            if entry.name.endswith(".tar.gz") and entry.size_bytes == 0:
                raise ValueError(f"empty required backup archive: {entry.key}")
            obj = by_key[entry.key]
            if obj.size_bytes != entry.size_bytes:
                raise ValueError(f"listed artifact size mismatch: {entry.key}")
            check_identity(client, config, obj, entry.sha256)
        pg_manifest = restore._load_postgres_backup_manifest(client, config, manifest)
        security.validate_postgres_manifest_structure(pg_manifest)
        security.validate_postgres_manifest_lineage(manifest, pg_manifest)
        manifests.append(manifest)
    cutoff = as_of - retention
    anchors = [m for m in manifests if m.completed_at <= cutoff]
    if not anchors:
        raise ValueError("no valid completed anchor at/before the window start")
    anchors.sort(key=lambda m: (m.completed_at, m.backup_id))
    anchor = anchors[-1]
    if len(anchors) > 1 and anchors[-2].completed_at == anchor.completed_at:
        raise ValueError("ambiguous anchor completion time")
    retained = [m for m in manifests if m.completed_at >= cutoff or m == anchor]
    if not retained:
        raise ValueError("no retained basebackups")
    end_timeline, end_position = lineage.wal_segment_position(
        required_end_wal, segment_size_bytes=segment_size
    )
    histories = [w for w in wal_objects if lineage.WAL_HISTORY_RE.fullmatch(w.filename)]
    if len(histories) > lineage.MAX_TIMELINE_HISTORY_FILES:
        raise ValueError("too many timeline histories")
    payloads = {
        w.key: read_small(client, config, by_key[w.key], lineage.MAX_TIMELINE_HISTORY_BYTES)
        for w in histories
    }
    for w in histories:
        lineage.parse_timeline_history(payloads[w.key], timeline=int(w.filename[:8], 16))
    chain, entries, _ = lineage._history_lineage(
        wal_objects,
        start_timeline=1,
        end_timeline=end_timeline,
        history_loader=lambda w: payloads[w.key],
    )
    if any(int(w.filename[:8], 16) not in chain for w in wal_objects):
        raise ValueError("ambiguous branch or timeline beyond the declared end WAL")
    for m in manifests:
        if m.timeline not in chain:
            raise ValueError(f"backup timeline is outside the verified lineage: {m.backup_id}")
        # Check even obsolete backups' LSNs against timeline birth/switch bounds.
        index = chain.index(m.timeline)
        start = security.parse_canonical_lsn(m.start_lsn, label="Backup start")
        end = security.parse_canonical_lsn(m.end_lsn, label="Backup end")
        if (index and start < entries[index - 1].switch_lsn) or (
            index < len(entries) and end > entries[index].switch_lsn
        ):
            raise ValueError(f"backup crosses declared timeline bounds: {m.backup_id}")
    start_value = security.parse_canonical_lsn(anchor.start_lsn, label="Anchor start")
    anchor_position = start_value // segment_size
    for m in retained:
        if (
            chain.index(m.timeline) < chain.index(anchor.timeline)
            or security.parse_canonical_lsn(m.start_lsn, label="Backup start") < start_value
        ):
            raise ValueError("retained backup needs WAL before the chosen anchor")
        # Each retained backup must be connected to the declared end, including
        # its completion LSN; the end WAL is not evidence of a wall-clock target.
        if (
            security.parse_canonical_lsn(m.end_lsn, label="Backup end") // segment_size
            > end_position
        ):
            raise ValueError("declared end WAL does not cover every retained backup")
        lineage.select_wal_objects(
            wal_objects,
            start_wal_name=lineage.wal_segment_name(
                timeline=m.timeline, lsn=m.start_lsn, segment_size_bytes=segment_size
            ),
            start_lsn=m.start_lsn,
            required_end_wal=required_end_wal,
            segment_size_bytes=segment_size,
            history_loader=lambda w: payloads[w.key],
        )
    for w in wal_objects:
        if not lineage.WAL_SEGMENT_RE.fullmatch(w.filename):
            continue
        if w.size_bytes != segment_size:
            raise ValueError(f"WAL segment has an invalid size: {w.key}")
        if w.codec == "gzip":
            header = storage.read_gzip_wal(
                client, bucket=config.bucket, key=w.key,
                head=client.head_object(Bucket=config.bucket, Key=w.key),
            )
        else:
            header = read_wal_header(client, config, by_key[w.key])
        wal_header_identity(
            header,
            item=w,
            system_identifier=expected_system_identifier,
            segment_size=segment_size,
            chain=chain,
            entries=entries,
        )
        timeline, position = lineage.wal_segment_position(
            w.filename, segment_size_bytes=segment_size
        )
        timeline_index = chain.index(timeline)
        anchor_index = chain.index(anchor.timeline)
        if (
            timeline_index < anchor_index
            and (position + 1) * segment_size > entries[timeline_index].switch_lsn
        ):
            reasons[w.key] = "ancestor WAL at/after fork; age relative to anchor is unproven"
        elif timeline_index <= anchor_index and position < anchor_position:
            reasons[w.key] = (
                "candidate: complete WAL strictly before anchor start segment on proven lineage"
            )
        else:
            reasons[w.key] = "retained WAL at/after anchor or beyond declared end"
    for m in manifests:
        if m == anchor:
            reason = "anchor completed at/before window start"
        elif m.completed_at > as_of:
            reason = "backup after as-of; conservatively retained"
        elif m in retained:
            reason = "backup within retention window"
        else:
            reason = "candidate: validated backup older than anchor"
        for item in groups[m.backup_id]:
            reasons[item.key] = reason
    return reasons, dict(
        anchor_backup_id=anchor.backup_id,
        anchor_start_lsn=anchor.start_lsn,
        anchor_timeline=anchor.timeline,
        verified_lineage=list(chain),
        retained_backup_ids=sorted(m.backup_id for m in retained),
    )


def plan(
    client: Any,
    config: Any,
    *,
    as_of: datetime,
    retention: timedelta,
    expected_system_identifier: str,
    required_end_wal: str,
    segment_size: int = 16 * 1024 * 1024,
) -> dict:
    objects: list[Object] = []
    evidence: dict = {}
    blocked: list[str] = []
    try:
        if as_of.tzinfo is None or as_of.utcoffset() is None or retention <= timedelta(0):
            raise ValueError("positive retention and timezone-aware as-of are required")
        if not (1024 * 1024 <= segment_size <= 1024**3 and segment_size & (segment_size - 1) == 0):
            raise ValueError(
                "PostgreSQL WAL segment size must be a power of two from 1 MiB to 1 GiB"
            )
        security.validate_system_identifier(
            expected_system_identifier, label="Expected system identifier"
        )
        objects = list_inventory(client, config)
        proof_client = ProofIdentityClient(client)
        reasons, evidence = _calculate(
            proof_client,
            config,
            objects,
            as_of=as_of,
            retention=retention,
            expected_system_identifier=expected_system_identifier,
            required_end_wal=required_end_wal,
            segment_size=segment_size,
        )
        # Detect archive changes during calculation; no plan is an atomic snapshot.
        if list_inventory(client, config) != objects:
            raise ValueError("inventory changed during planning; retry from a fresh snapshot")
        for item in objects:
            final_client = proof_client if item.key in proof_client.identities else client
            head = final_client.head_object(Bucket=config.bucket, Key=item.key)
            if (
                type(head.get("ContentLength")) is not int
                or head.get("ContentLength") != item.size_bytes
                or head.get("ETag") != item.etag
                or head.get("VersionId") not in (None, "null")
            ):
                raise ValueError(f"object changed during planning: {item.key}")
    except (Exception, SystemExit) as exc:
        # SDK errors can include endpoints or credentials; never echo their text.
        message = str(exc) if isinstance(exc, (ValueError, SystemExit)) else type(exc).__name__
        blocked.append(message)
        reasons = {item.key: "blocked: retain all inventoried objects" for item in objects}
        evidence = {}

    def rows(candidate: bool) -> list[dict]:
        return [
            dict(key=item.key, size_bytes=item.size_bytes, etag=item.etag, reason=reasons[item.key])
            for item in objects
            if reasons[item.key].startswith("candidate:") == candidate
        ]

    candidates, retained = rows(True), rows(False)
    return dict(
        schema_version=1,
        mode="report-only",
        status="blocked" if blocked else "planned",
        as_of=as_of.isoformat(),
        retention_seconds=retention.total_seconds(),
        window_start=(as_of - retention).isoformat(),
        expected_system_identifier=expected_system_identifier,
        required_end_wal=required_end_wal,
        blocked_reasons=blocked,
        evidence=evidence,
        inventory_complete=bool(objects) and not blocked,
        candidates=candidates,
        retained=retained,
        candidate_count=len(candidates),
        candidate_bytes=sum(r["size_bytes"] for r in candidates),
        retained_count=len(retained),
        retained_bytes=sum(r["size_bytes"] for r in retained),
        deletion_authorized=False,
        recovery_window_proven=False,
    )


class InventoryClient:
    """Offline read evidence: complete listing, HEAD identities and small GETs.

    Backup tar bodies are unnecessary; their digest/size identities must agree
    with the manifest. WAL records contain only the first 40 bytes. This is
    planning evidence, not byte verification of a complete physical backup.
    """

    def __init__(self, payload: dict):
        if (
            payload.get("schema_version") != 1
            or type(payload.get("schema_version")) is not int
            or payload.get("listing_complete") is not True
            or not isinstance(payload.get("objects"), list)
        ):
            raise ValueError("offline inventory must declare schema 1 and a complete listing")
        self.records = payload["objects"]
        self.by_key = {}
        for r in self.records:
            if r["key"] in self.by_key:
                raise ValueError("duplicate offline inventory key")
            self.by_key[r["key"]] = r

    def list_objects_v2(self, **args):
        records = [r for r in self.records if r["key"].startswith(args["Prefix"])]
        start = int(args.get("ContinuationToken", "0"))
        end = start + args["MaxKeys"]
        page = dict(
            IsTruncated=end < len(records),
            Contents=[
                dict(Key=r["key"], Size=r["size_bytes"], ETag=r["etag"]) for r in records[start:end]
            ],
        )
        if page["IsTruncated"]:
            page["NextContinuationToken"] = str(end)
        return page

    def head_object(self, *, Bucket, Key):
        r = self.by_key[Key]
        return dict(
            ContentLength=r["size_bytes"],
            ETag=r["etag"],
            Metadata={"sha256": r.get("sha256", ""), **r.get("metadata", {})},
            VersionId=r.get("version_id"),
        )

    def get_object(self, *, Bucket, Key, Range=None, IfMatch=None):
        r = self.by_key[Key]
        if IfMatch is not None and IfMatch != r["etag"]:
            raise ValueError("offline conditional identity mismatch")
        if Range:
            data = bytes.fromhex(r["wal_header_hex"])
        else:
            data = base64.b64decode(r["payload_base64"], validate=True)
        response = dict(ContentLength=len(data), Body=io.BytesIO(data), ETag=r["etag"])
        if Range:
            response["ContentRange"] = f"bytes 0-39/{r['size_bytes']}"
        return response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--inventory", type=Path, help="Offline read-evidence JSON")
    source.add_argument(
        "--live", action="store_true", help="Read private POSTGRES_PITR_* S3 config"
    )
    parser.add_argument("--cluster", default="mvn-api", help="Offline inventory namespace")
    parser.add_argument("--key-prefix", default="postgres/pitr", help="Offline inventory prefix")

    def clock_argument(raw):
        try:
            return parse_as_of(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc

    parser.add_argument("--as-of", required=True, type=clock_argument)
    parser.add_argument("--retention-days", required=True, type=int)
    parser.add_argument("--expected-system-identifier", required=True)
    parser.add_argument("--required-end-wal", required=True)
    parser.add_argument("--wal-segment-size-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--dry-run", action="store_true", help="Report only (always enabled)")
    args = parser.parse_args(argv)
    try:
        if args.inventory:
            if args.inventory.stat().st_size > MAX_INVENTORY_BYTES:
                raise ValueError("offline inventory exceeds size limit")
            client = InventoryClient(json.loads(args.inventory.read_bytes()))
            config = SimpleNamespace(
                bucket="offline", key_prefix=args.key_prefix, cluster=args.cluster
            )
        else:
            config = restore.load_config()
            client = restore.build_client(config)
        report = plan(
            client,
            config,
            as_of=args.as_of,
            retention=timedelta(days=args.retention_days),
            expected_system_identifier=args.expected_system_identifier,
            required_end_wal=args.required_end_wal,
            segment_size=args.wal_segment_size_bytes,
        )
    except (Exception, SystemExit) as exc:
        report = dict(
            status="blocked",
            mode="report-only",
            candidate_count=0,
            candidate_bytes=0,
            candidates=[],
            deletion_authorized=False,
            recovery_window_proven=False,
            blocked_reasons=[str(exc) if isinstance(exc, ValueError) else type(exc).__name__],
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
