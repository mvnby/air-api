#!/usr/bin/env bash

# Shell library. The caller supplies CANONICAL_FILE and CANDIDATE_FILE.

require_pitr_attested_candidate() {
  local release_manifest="${PATRONI_FINALIZED_RELEASE_MANIFEST:-/var/lib/mvn-postgres-pitr/release-manifest.json}"
  python3 - \
    "${release_manifest}" "${CANONICAL_FILE}" "${CANDIDATE_FILE}" <<'PY'
import base64
import hashlib
import json
import os
import re
import stat
import sys

manifest_path, canonical_path, candidate_path = sys.argv[1:]
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 1024 * 1024
MAX_RELEASE_BYTES = 2 * 1024 * 1024
HEX_32 = re.compile(r"[0-9a-f]{32}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")


def require_canonical_path(path: str, label: str) -> None:
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise SystemExit(f"{label} path is not canonical")


def read_owned(
    path: str,
    label: str,
    *,
    exact_mode: int,
    max_bytes: int,
) -> bytes:
    require_canonical_path(path, label)
    try:
        before = os.lstat(path)
    except FileNotFoundError as exc:
        raise SystemExit(f"{label} is missing") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_gid != os.getegid()
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != exact_mode
        or before.st_size > max_bytes
    ):
        raise SystemExit(
            f"{label} must be current-user-and-group-owned regular "
            f"non-symlink with mode {exact_mode:04o}, one link, and bounded size"
        )
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if tuple(getattr(opened, field) for field in fields) != tuple(
            getattr(before, field) for field in fields
        ):
            raise SystemExit(f"{label} changed while opening")
        chunks = []
        size = 0
        while True:
            chunk = os.read(descriptor, 131072)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise SystemExit(f"{label} exceeds its size bound")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if tuple(getattr(after, field) for field in fields) != tuple(
            getattr(opened, field) for field in fields
        ):
            raise SystemExit(f"{label} changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


manifest_raw = read_owned(
    manifest_path,
    "finalized PITR release manifest",
    exact_mode=0o600,
    max_bytes=MAX_MANIFEST_BYTES,
)
try:
    manifest = json.loads(manifest_raw)
except (UnicodeDecodeError, ValueError) as exc:
    raise SystemExit("finalized PITR release manifest is invalid") from exc
try:
    canonical_manifest = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("ascii")
        + b"\n"
    )
except (TypeError, UnicodeEncodeError) as exc:
    raise SystemExit("finalized PITR release manifest is invalid") from exc
if manifest_raw != canonical_manifest:
    raise SystemExit("finalized PITR release manifest is not canonical JSON")
if (
    not isinstance(manifest, dict)
    or set(manifest)
    != {"files", "project_dir", "release_sha256", "txid", "version"}
    or type(manifest.get("version")) is not int
    or manifest["version"] != 1
    or manifest.get("project_dir") != os.path.dirname(canonical_path)
    or not isinstance(manifest.get("txid"), str)
    or HEX_32.fullmatch(manifest["txid"]) is None
    or not isinstance(manifest.get("release_sha256"), str)
    or HEX_64.fullmatch(manifest["release_sha256"]) is None
    or not isinstance(manifest.get("files"), list)
    or not manifest["files"]
):
    raise SystemExit("finalized PITR release manifest contract is invalid")

files = manifest["files"]
paths = []
compose_entry = None
for item in files:
    if (
        not isinstance(item, dict)
        or set(item) != {"mode", "path", "sha256"}
        or type(item.get("mode")) is not int
        or item["mode"] not in {0o644, 0o755}
        or not isinstance(item.get("path"), str)
        or not os.path.isabs(item["path"])
        or os.path.normpath(item["path"]) != item["path"]
        or not isinstance(item.get("sha256"), str)
        or HEX_64.fullmatch(item["sha256"]) is None
    ):
        raise SystemExit("finalized PITR release manifest file contract is invalid")
    paths.append(item["path"])
    if item["path"] == canonical_path:
        compose_entry = item
if paths != sorted(paths) or len(paths) != len(set(paths)):
    raise SystemExit(
        "finalized PITR release manifest files must be sorted and unique"
    )

release_files = []
audited_contents = {}
for item in files:
    content = read_owned(
        item["path"],
        "finalized PITR release asset",
        exact_mode=item["mode"],
        max_bytes=MAX_ASSET_BYTES,
    )
    if hashlib.sha256(content).hexdigest() != item["sha256"]:
        raise SystemExit(
            "finalized PITR release asset differs from its manifest digest"
        )
    audited_contents[item["path"]] = content
    release_files.append(
        {
            "content": base64.b64encode(content).decode("ascii"),
            "mode": item["mode"],
            "path": item["path"],
            "sha256": item["sha256"],
        }
    )
release_body = {
    "files": release_files,
    "project_dir": manifest["project_dir"],
    "version": 1,
}
release_body_raw = json.dumps(
    release_body,
    sort_keys=True,
    separators=(",", ":"),
).encode("ascii")
if (
    len(release_body_raw) > MAX_RELEASE_BYTES
    or hashlib.sha256(release_body_raw).hexdigest()
    != manifest["release_sha256"]
):
    raise SystemExit("finalized PITR release digest does not match its exact files")

canonical = read_owned(
    canonical_path,
    "canonical compose",
    exact_mode=0o644,
    max_bytes=MAX_ASSET_BYTES,
)
if (
    compose_entry is None
    or compose_entry["mode"] != 0o644
    or audited_contents.get(canonical_path) != canonical
    or compose_entry["sha256"] != hashlib.sha256(canonical).hexdigest()
):
    raise SystemExit(
        "canonical Compose is not the exact finalized PITR release generation"
    )
candidate = read_owned(
    candidate_path,
    "candidate compose",
    exact_mode=0o644,
    max_bytes=MAX_ASSET_BYTES,
)
if candidate != canonical:
    raise SystemExit(
        "candidate Compose is not byte-identical to the PITR-attested canonical "
        "Compose; run the official atomic PITR cluster migration first"
    )
PY
}
