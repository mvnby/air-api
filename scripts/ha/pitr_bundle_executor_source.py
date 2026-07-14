"""Self-contained production source for the pinned PITR release executor."""

from __future__ import annotations
REMOTE_RELEASE_BUNDLE_EXECUTOR = r'''
import base64
import binascii
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
MAX_BUNDLE = 2097152
MAX_ASSET = 1048576
ROOT_UID = 0
ROOT_GID = 0
LOCK_PATH = "/run/lock/mvn-postgres-pitr-prerequisites.lock"
STATE_ROOT = "/var/lib/mvn-postgres-pitr"
TRANSACTION_ROOT = STATE_ROOT + "/release-transactions"
ROLLBACK_RECEIPT_ROOT = STATE_ROOT + "/rollback-receipts"
RELEASE_MANIFEST = STATE_ROOT + "/release-manifest.json"
MAINTENANCE_MARKER = "/run/mvn-postgres-pitr-maintenance"
OPERATION_ROOT = "/run/mvn-postgres-pitr-operations"
LIBEXEC_DIR = "/usr/local/libexec/mvn-pitr"
LIBEXEC_PARENT = "/usr/local/libexec"
BASE_MODES = {
    "/usr/local/sbin/mvn-postgres-pitr-upload": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-immutable-upload": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-upload-wal": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-basebackup": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-configure-env": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-provision-host": 0o755,
    "/usr/local/sbin/mvn_postgres_pitr_config_transaction.py": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-restore": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-restore-drill": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-status": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-remote-status": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-bootstrap": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-runtime-check": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-scheduled-runner": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-manual-runner": 0o755,
    "/usr/local/sbin/mvn-restore-drill-latest-db": 0o755,
    "/usr/local/sbin/mvn-restore-drill-latest-db-cleanup": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-tool-runner": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-artifact-security": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-wal-lineage": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-recovery-config": 0o755,
    "/usr/local/sbin/mvn_postgres_pitr_operation_guard.py": 0o755,
    "/usr/local/sbin/mvn_postgres_pitr_operation_cleanup.py": 0o755,
    LIBEXEC_DIR + "/install_postgres_pitr_units.sh": 0o755,
    LIBEXEC_DIR + "/run_postgres_pitr_install_locked.py": 0o755,
    LIBEXEC_DIR + "/deploy_backend_blue_green.sh": 0o755,
    LIBEXEC_DIR + "/deploy_backend_blue_green_safety.sh": 0o755,
    LIBEXEC_DIR + "/prepare_google_oauth_token_dir.sh": 0o755,
    "/etc/systemd/system/mvn-postgres-wal-upload.service": 0o644,
    "/etc/systemd/system/mvn-postgres-wal-upload.timer": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.service": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.timer": 0o644,
}
PROJECT_COMPOSE = {
    "/opt/air-api": "/opt/air-api/docker-compose.patroni.yml",
    "/opt/mvn-reserve": "/opt/mvn-reserve/docker-compose.patroni.yml",
}
def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
def expected_modes(project_dir, compose_file):
    compose = PROJECT_COMPOSE.get(project_dir)
    if compose != os.path.join(project_dir, compose_file):
        raise RuntimeError("unreviewed node compose destination")
    return {**BASE_MODES, compose: 0o644}
def validate_txid(txid):
    if not re.fullmatch(r"[0-9a-f]{32}", txid):
        raise RuntimeError("transaction id must be 32 lowercase hexadecimal characters")
def ensure_dir(path, mode):
    validate_parent(path)
    try:
        os.mkdir(path, mode)
    except FileExistsError:
        pass
    metadata = os.lstat(path)
    if (not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != ROOT_UID or metadata.st_gid != ROOT_GID
            or stat.S_IMODE(metadata.st_mode) != mode):
        raise RuntimeError("release directory metadata is unsafe: " + path)
def ensure_roots():
    ensure_dir(STATE_ROOT, 0o700)
    ensure_dir(TRANSACTION_ROOT, 0o700)
    ensure_dir(ROLLBACK_RECEIPT_ROOT, 0o700)
    ensure_dir(LIBEXEC_PARENT, 0o755)
    ensure_dir(LIBEXEC_DIR, 0o755)
def unsafe_parent_metadata(current, metadata):
    if (not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != ROOT_UID or metadata.st_gid != ROOT_GID):
        return True
    writable = stat.S_IMODE(metadata.st_mode) & 0o022
    if not writable:
        return False
    if current != "/run/lock":
        return True
    return bool(writable & 0o002 and not metadata.st_mode & stat.S_ISVTX)
def validate_parent(path):
    if not path.startswith("/") or os.path.normpath(path) != path:
        raise RuntimeError("release path is not canonical")
    current = "/"
    if unsafe_parent_metadata(current, os.lstat(current)):
        raise RuntimeError("release parent metadata is unsafe: " + current)
    for part in os.path.dirname(path).split("/")[1:]:
        current = os.path.join(current, part)
        metadata = os.lstat(current)
        if unsafe_parent_metadata(current, metadata):
            raise RuntimeError("release parent metadata is unsafe: " + current)
def fsync_dir(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
def read_regular(path, *, exact_mode=None, max_bytes=MAX_ASSET):
    before = os.lstat(path)
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or before.st_uid != ROOT_UID or before.st_gid != ROOT_GID
            or before.st_nlink != 1 or before.st_mode & 0o022
            or (exact_mode is not None and stat.S_IMODE(before.st_mode) != exact_mode)):
        raise RuntimeError("release file metadata is unsafe: " + path)
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if tuple(getattr(opened, name) for name in fields) != tuple(getattr(before, name) for name in fields):
            raise RuntimeError("release file changed while opening: " + path)
        chunks = []
        size = 0
        while True:
            chunk = os.read(descriptor, 131072)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise RuntimeError("release file exceeds its size bound: " + path)
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if tuple(getattr(after, name) for name in fields) != tuple(getattr(opened, name) for name in fields):
            raise RuntimeError("release file changed while reading: " + path)
        return b"".join(chunks), opened
    finally:
        os.close(descriptor)
def atomic_write(path, content, mode):
    validate_parent(path)
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        pass
    else:
        if (not stat.S_ISREG(existing.st_mode) or stat.S_ISLNK(existing.st_mode)
                or existing.st_uid != ROOT_UID or existing.st_gid != ROOT_GID or existing.st_nlink != 1):
            raise RuntimeError("release target metadata is unsafe: " + path)
    parent = os.path.dirname(path)
    stage = os.path.join(parent, ".mvn-pitr-stage-" + secrets.token_hex(16))
    descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, ROOT_UID, ROOT_GID)
        view = memoryview(content)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise RuntimeError("short release asset write")
            offset += written
        view.release()
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(stage, path)
        fsync_dir(parent)
    finally:
        try:
            os.unlink(stage)
        except FileNotFoundError:
            pass
def read_payload(stream, required):
    payload = stream.read(MAX_BUNDLE + 1)
    if (required and not payload) or len(payload) > MAX_BUNDLE or (not required and payload):
        raise RuntimeError("release bundle payload size is invalid")
    return payload
def decode_bundle(payload, project_dir, compose_file):
    try:
        bundle = json.loads(payload)
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("release bundle is not valid JSON") from exc
    if not isinstance(bundle, dict) or set(bundle) != {"files", "project_dir", "release_sha256", "version"}:
        raise RuntimeError("release bundle schema is invalid")
    if payload != canonical(bundle):
        raise RuntimeError("release bundle is not canonical")
    if bundle["version"] != 1 or bundle["project_dir"] != project_dir:
        raise RuntimeError("release bundle targets an unexpected node")
    modes = expected_modes(project_dir, compose_file)
    if not isinstance(bundle["files"], list) or len(bundle["files"]) != len(modes):
        raise RuntimeError("release bundle has a missing or extra path")
    decoded = {}
    descriptors = []
    for item in bundle["files"]:
        if not isinstance(item, dict) or set(item) != {"content", "mode", "path", "sha256"}:
            raise RuntimeError("release asset schema is invalid")
        path = item["path"]
        if path in decoded or path not in modes or item["mode"] != modes[path]:
            raise RuntimeError("release bundle contains an unreviewed path or mode")
        digest = item["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError("release asset digest is invalid")
        try:
            content = base64.b64decode(item["content"], validate=True)
        except (binascii.Error, TypeError, ValueError) as exc:
            raise RuntimeError("release asset encoding is invalid") from exc
        if len(content) > MAX_ASSET or hashlib.sha256(content).hexdigest() != digest:
            raise RuntimeError("release asset content digest or size is invalid")
        decoded[path] = content
        descriptors.append({"mode": item["mode"], "path": path, "sha256": digest})
    if set(decoded) != set(modes):
        raise RuntimeError("release bundle has a missing or extra path")
    if [item["path"] for item in bundle["files"]] != sorted(decoded):
        raise RuntimeError("release bundle path order is not canonical")
    body = {"files": bundle["files"], "project_dir": project_dir, "version": 1}
    release = hashlib.sha256(canonical(body)).hexdigest()
    if bundle["release_sha256"] != release:
        raise RuntimeError("release bundle digest is invalid")
    return release, decoded, sorted(descriptors, key=lambda item: item["path"])
def open_lock(path):
    allowed = {LOCK_PATH, *(os.path.join(project, ".deploy.lock") for project in PROJECT_COMPOSE)}
    if path not in allowed:
        raise RuntimeError("unreviewed release lock path")
    validate_parent(path)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    metadata = os.fstat(descriptor)
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != ROOT_UID
            or metadata.st_gid != ROOT_GID or metadata.st_nlink != 1
            or metadata.st_mode & 0o022):
        os.close(descriptor)
        raise RuntimeError("release lock metadata is unsafe")
    os.fchmod(descriptor, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise RuntimeError("another PITR or deploy operation is active") from exc
    return descriptor
def reject_operation_records():
    try:
        metadata = os.lstat(OPERATION_ROOT)
    except FileNotFoundError:
        return
    if (not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != ROOT_UID or metadata.st_gid != ROOT_GID
            or metadata.st_mode & 0o077):
        raise RuntimeError("PITR operation record directory is unsafe")
    if os.listdir(OPERATION_ROOT):
        raise RuntimeError("a recorded PITR operation must be cleaned up first")
def marker_value():
    try:
        content, metadata = read_regular(MAINTENANCE_MARKER, exact_mode=0o600, max_bytes=34)
    except FileNotFoundError:
        return None
    try:
        value = content.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RuntimeError("maintenance marker is invalid") from exc
    if not re.fullmatch(r"[0-9a-f]{32}\n", value):
        raise RuntimeError("maintenance marker is invalid")
    return value[:-1]
def ensure_marker(txid):
    current = marker_value()
    if current is not None:
        if current != txid:
            raise RuntimeError("another release transaction owns the maintenance marker")
        return False
    validate_parent(MAINTENANCE_MARKER)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = os.open(MAINTENANCE_MARKER, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, ROOT_UID, ROOT_GID)
        content = (txid + "\n").encode("ascii")
        if os.write(descriptor, content) != len(content):
            raise RuntimeError("short maintenance marker write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    fsync_dir(os.path.dirname(MAINTENANCE_MARKER))
    return True
def remove_marker(txid):
    if marker_value() != txid:
        raise RuntimeError("maintenance marker ownership changed")
    os.unlink(MAINTENANCE_MARKER)
    fsync_dir(os.path.dirname(MAINTENANCE_MARKER))
def file_generation(path, old, new_digest, new_mode):
    try:
        content, metadata = read_regular(path)
    except FileNotFoundError:
        return "old" if not old["present"] else "unknown"
    digest = hashlib.sha256(content).hexdigest()
    mode = stat.S_IMODE(metadata.st_mode)
    if digest == new_digest and mode == new_mode:
        return "new"
    if old["present"] and digest == old["sha256"] and mode == old["mode"]:
        return "old"
    return "unknown"
def write_journal(txdir, journal):
    atomic_write(os.path.join(txdir, "journal.json"), canonical(journal) + b"\n", 0o600)
def read_journal(txdir):
    path = os.path.join(txdir, "journal.json")
    content, _ = read_regular(path, exact_mode=0o600, max_bytes=MAX_BUNDLE)
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("release transaction journal is invalid") from exc
    if content != canonical(value) + b"\n":
        raise RuntimeError("release transaction journal is not canonical")
    return value
def prepare_transaction(txid, project_dir, release, descriptors):
    temporary = tempfile.mkdtemp(prefix="." + txid + ".prepare-", dir=TRANSACTION_ROOT)
    os.chown(temporary, ROOT_UID, ROOT_GID)
    os.chmod(temporary, 0o700)
    try:
        snapshots = os.path.join(temporary, "snapshots")
        os.mkdir(snapshots, 0o700)
        os.chown(snapshots, ROOT_UID, ROOT_GID)
        entries = []
        for index, descriptor in enumerate(descriptors):
            path = descriptor["path"]
            validate_parent(path)
            old = {"present": False}
            snapshot = None
            try:
                content, metadata = read_regular(path, exact_mode=descriptor["mode"])
            except FileNotFoundError:
                pass
            else:
                old = {"mode": stat.S_IMODE(metadata.st_mode), "present": True,
                       "sha256": hashlib.sha256(content).hexdigest()}
                snapshot = f"{index:03d}.snapshot"
                atomic_write(os.path.join(snapshots, snapshot), content, 0o600)
            entries.append({**descriptor, "old": old, "snapshot": snapshot})
        journal = {"entries": entries, "project_dir": project_dir,
                   "release_sha256": release, "state": "prepared", "txid": txid, "version": 1}
        write_journal(temporary, journal)
        fsync_dir(snapshots)
        fsync_dir(temporary)
        target = os.path.join(TRANSACTION_ROOT, txid)
        os.rename(temporary, target)
        fsync_dir(TRANSACTION_ROOT)
        return target, journal
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
def transaction_exists(txdir):
    try:
        metadata = os.lstat(txdir)
    except FileNotFoundError:
        return False
    if (not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != ROOT_UID or metadata.st_gid != ROOT_GID
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise RuntimeError("release transaction directory is unsafe")
    return True
def validate_journal(journal, txid, project_dir, release=None, descriptors=None):
    if (not isinstance(journal, dict)
            or set(journal) != {"entries", "project_dir", "release_sha256", "state", "txid", "version"}
            or journal["version"] != 1 or journal["txid"] != txid
            or journal["project_dir"] != project_dir or journal["state"] not in {"prepared", "applied"}
            or not isinstance(journal["entries"], list)):
        raise RuntimeError("release transaction journal contract is invalid")
    if release is not None and journal["release_sha256"] != release:
        raise RuntimeError("release transaction belongs to another release")
    if descriptors is not None:
        actual = [{key: entry[key] for key in ("mode", "path", "sha256")} for entry in journal["entries"]]
        if actual != descriptors:
            raise RuntimeError("release transaction asset set changed")
    paths = set()
    allowed = {**BASE_MODES, PROJECT_COMPOSE[project_dir]: 0o644}
    for entry in journal["entries"]:
        if (not isinstance(entry, dict) or set(entry) != {"mode", "old", "path", "sha256", "snapshot"}
                or entry["path"] in paths or entry["path"] not in allowed
                or entry["mode"] != allowed[entry["path"]]):
            raise RuntimeError("release transaction entry is invalid")
        paths.add(entry["path"])
        old = entry["old"]
        if old == {"present": False}:
            if entry["snapshot"] is not None:
                raise RuntimeError("absent generation has a snapshot")
        elif (not isinstance(old, dict) or set(old) != {"mode", "present", "sha256"}
              or old["present"] is not True or old["mode"] != entry["mode"]
              or not re.fullmatch(r"[0-9a-f]{64}", old["sha256"])
              or not re.fullmatch(r"[0-9]{3}\.snapshot", entry["snapshot"] or "")):
            raise RuntimeError("recorded old generation is invalid")
def verify_snapshot(txdir, entry):
    if not entry["old"]["present"]:
        return None
    path = os.path.join(txdir, "snapshots", entry["snapshot"])
    content, _ = read_regular(path, exact_mode=0o600)
    if hashlib.sha256(content).hexdigest() != entry["old"]["sha256"]:
        raise RuntimeError("release rollback snapshot digest mismatch")
    return content
def apply_transaction(txdir, journal, decoded):
    for entry in journal["entries"]:
        generation = file_generation(entry["path"], entry["old"], entry["sha256"], entry["mode"])
        if generation == "unknown":
            raise RuntimeError("release target has an unknown generation: " + entry["path"])
        if generation == "old":
            atomic_write(entry["path"], decoded[entry["path"]], entry["mode"])
        content, metadata = read_regular(entry["path"], exact_mode=entry["mode"])
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise RuntimeError("release target verification failed: " + entry["path"])
    journal["state"] = "applied"
    write_journal(txdir, journal)
def rollback_transaction(txdir, journal):
    for entry in reversed(journal["entries"]):
        generation = file_generation(entry["path"], entry["old"], entry["sha256"], entry["mode"])
        if generation == "unknown":
            raise RuntimeError("release target has an unknown generation: " + entry["path"])
        if generation == "new":
            content = verify_snapshot(txdir, entry)
            if content is None:
                os.unlink(entry["path"])
                fsync_dir(os.path.dirname(entry["path"]))
            else:
                atomic_write(entry["path"], content, entry["old"]["mode"])
        if file_generation(entry["path"], entry["old"], entry["sha256"], entry["mode"]) != "old":
            raise RuntimeError("release rollback verification failed: " + entry["path"])
def safe_remove_transaction(txdir):
    metadata = os.lstat(txdir)
    if (not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != ROOT_UID or metadata.st_gid != ROOT_GID
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise RuntimeError("release transaction directory is unsafe")
    for root, directories, files in os.walk(txdir, topdown=True, followlinks=False):
        for name in directories:
            value = os.lstat(os.path.join(root, name))
            if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
                raise RuntimeError("release transaction contains an unsafe directory")
        for name in files:
            value = os.lstat(os.path.join(root, name))
            if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
                raise RuntimeError("release transaction contains an unsafe file")
    shutil.rmtree(txdir)
    fsync_dir(TRANSACTION_ROOT)
def daemon_reload():
    environment = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                   "HOME": "/root", "LANG": "C", "LC_ALL": "C"}
    result = subprocess.run(["/usr/bin/systemctl", "daemon-reload"], env=environment,
                            stdin=subprocess.DEVNULL, check=False, timeout=60)
    if result.returncode != 0:
        raise RuntimeError("systemd daemon-reload failed")
def release_manifest(journal):
    files = [{key: entry[key] for key in ("mode", "path", "sha256")} for entry in journal["entries"]]
    return {"files": files, "project_dir": journal["project_dir"],
            "release_sha256": journal["release_sha256"], "txid": journal["txid"], "version": 1}
def rollback_receipt(journal):
    generations = []
    for entry in journal["entries"]:
        old = entry["old"]
        generations.append({"mode": entry["mode"], "path": entry["path"],
                            "present": old["present"], "sha256": old.get("sha256")})
    return {"old_generations": generations, "project_dir": journal["project_dir"],
            "release_sha256": journal["release_sha256"], "txid": journal["txid"], "version": 1}
def validate_rollback_receipt(receipt, txid, project_dir, modes):
    release_digest = receipt.get("release_sha256") if isinstance(receipt, dict) else None
    if (not isinstance(receipt, dict)
            or set(receipt) != {"old_generations", "project_dir", "release_sha256", "txid", "version"}
            or type(receipt["version"]) is not int or receipt["version"] != 1
            or receipt["txid"] != txid
            or receipt["project_dir"] != project_dir
            or not isinstance(release_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", release_digest)
            or not isinstance(receipt["old_generations"], list)):
        raise RuntimeError("rollback receipt contract is invalid")
    paths = []
    for generation in receipt["old_generations"]:
        path = generation.get("path") if isinstance(generation, dict) else None
        if (not isinstance(generation, dict)
                or set(generation) != {"mode", "path", "present", "sha256"}
                or not isinstance(path, str) or path not in modes or path in paths
                or generation["mode"] != modes[path]
                or type(generation["present"]) is not bool):
            raise RuntimeError("rollback receipt generation is invalid")
        if generation["present"]:
            if (not isinstance(generation["sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", generation["sha256"])):
                raise RuntimeError("rollback receipt generation digest is invalid")
        elif generation["sha256"] is not None:
            raise RuntimeError("absent rollback generation has a digest")
        paths.append(path)
    if paths != sorted(modes):
        raise RuntimeError("rollback receipt path set is incomplete")
def rollback_receipt_path(txid):
    return os.path.join(ROLLBACK_RECEIPT_ROOT, txid + ".json")
def read_rollback_receipt(txid, project_dir, modes):
    content, _ = read_regular(rollback_receipt_path(txid), exact_mode=0o600, max_bytes=MAX_BUNDLE)
    try:
        receipt = json.loads(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("rollback receipt is invalid") from exc
    if content != canonical(receipt) + b"\n":
        raise RuntimeError("rollback receipt is not canonical")
    validate_rollback_receipt(receipt, txid, project_dir, modes)
    return receipt
def write_rollback_receipt(receipt, modes):
    validate_rollback_receipt(receipt, receipt["txid"], receipt["project_dir"], modes)
    path = rollback_receipt_path(receipt["txid"])
    expected = canonical(receipt) + b"\n"
    try:
        existing, _ = read_regular(path, exact_mode=0o600, max_bytes=MAX_BUNDLE)
    except FileNotFoundError:
        atomic_write(path, expected, 0o600)
    else:
        if existing != expected:
            raise RuntimeError("rollback receipt conflicts with this transaction")
    return read_rollback_receipt(receipt["txid"], receipt["project_dir"], modes)
def verify_rollback_generations(receipt):
    for generation in receipt["old_generations"]:
        try:
            content, _ = read_regular(generation["path"], exact_mode=generation["mode"])
        except FileNotFoundError:
            if generation["present"]:
                raise RuntimeError("recorded rollback generation is missing: " + generation["path"])
            continue
        if (not generation["present"]
                or hashlib.sha256(content).hexdigest() != generation["sha256"]):
            raise RuntimeError("recorded rollback generation does not match: " + generation["path"])
def read_release_manifest(modes, project_dir):
    try:
        content, _ = read_regular(RELEASE_MANIFEST, exact_mode=0o600, max_bytes=MAX_BUNDLE)
    except FileNotFoundError:
        return None
    try:
        manifest = json.loads(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("release manifest is invalid") from exc
    if content != canonical(manifest) + b"\n":
        raise RuntimeError("release manifest is not canonical")
    if (not isinstance(manifest, dict)
            or set(manifest) != {"files", "project_dir", "release_sha256", "txid", "version"}
            or type(manifest["version"]) is not int or manifest["version"] != 1
            or not isinstance(manifest["project_dir"], str)
            or manifest["project_dir"] != project_dir
            or not isinstance(manifest["txid"], str)
            or not re.fullmatch(r"[0-9a-f]{32}", manifest["txid"])
            or not isinstance(manifest["release_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest["release_sha256"])
            or not isinstance(manifest["files"], list)):
        raise RuntimeError("release manifest contract is invalid")
    files = []
    for item in manifest["files"]:
        path = item.get("path") if isinstance(item, dict) else None
        if (not isinstance(item, dict) or set(item) != {"mode", "path", "sha256"}
                or not isinstance(path, str) or path not in modes
                or item["mode"] != modes[path]
                or not isinstance(item["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
            raise RuntimeError("release manifest file contract is invalid")
        files.append(item)
    if [item["path"] for item in files] != sorted(modes):
        raise RuntimeError("release manifest path set is incomplete")
    for item in files:
        content, _ = read_regular(item["path"], exact_mode=item["mode"])
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise RuntimeError("current file does not match the release manifest: " + item["path"])
    return manifest
def clear_completed_marker(txid):
    marker = marker_value()
    if marker is None:
        return
    if marker != txid:
        raise RuntimeError("another release transaction owns the maintenance marker")
    remove_marker(txid)
def execute(action, txid, project_dir, compose_file, payload):
    validate_txid(txid)
    modes = expected_modes(project_dir, compose_file)
    release = decoded = descriptors = None
    if action == "apply":
        release, decoded, descriptors = decode_bundle(payload, project_dir, compose_file)
    elif action not in {"rollback", "finalize"}:
        raise RuntimeError("unsupported release transaction action")
    global_fd = open_lock(LOCK_PATH)
    deploy_fd = None
    try:
        deploy_fd = open_lock(os.path.join(project_dir, ".deploy.lock"))
        ensure_roots()
        reject_operation_records()
        txdir = os.path.join(TRANSACTION_ROOT, txid)
        has_tx = transaction_exists(txdir)
        completed = None if has_tx else read_release_manifest(modes, project_dir)
        if completed is not None and completed["txid"] == txid:
            if has_tx:
                raise RuntimeError("completed release still has a transaction directory")
            if action == "rollback":
                raise RuntimeError("cannot roll back a finalized release transaction")
            if action == "apply":
                expected_files = [{key: item[key] for key in ("mode", "path", "sha256")} for item in descriptors]
                if (completed["release_sha256"] != release
                        or completed["files"] != expected_files):
                    raise RuntimeError("transaction id already finalized another release")
                # Re-open the same completed transaction's maintenance fence so
                # a controller can safely replay idempotent host phases after a
                # crash between the two node finalizations.
                ensure_marker(txid)
                return "reopened"
            clear_completed_marker(txid)
            return "already-finalized"
        if action == "apply":
            try:
                read_rollback_receipt(txid, project_dir, modes)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError("release transaction id already has a rollback receipt")
        if action == "rollback":
            try:
                receipt = read_rollback_receipt(txid, project_dir, modes)
            except FileNotFoundError:
                if not has_tx:
                    raise
            else:
                verify_rollback_generations(receipt)
                if has_tx:
                    safe_remove_transaction(txdir)
                verify_rollback_generations(receipt)
                marker = marker_value()
                if marker is not None:
                    if marker != txid:
                        raise RuntimeError("another release transaction owns the maintenance marker")
                    remove_marker(txid)
                return "already-rolled-back"
        created_marker = ensure_marker(txid)
        try:
            if action == "apply":
                if has_tx:
                    journal = read_journal(txdir)
                else:
                    txdir, journal = prepare_transaction(txid, project_dir, release, descriptors)
                validate_journal(journal, txid, project_dir, release, descriptors)
                apply_transaction(txdir, journal, decoded)
                daemon_reload()
                return "applied"
            if not has_tx:
                raise RuntimeError("release transaction does not exist")
            journal = read_journal(txdir)
            validate_journal(journal, txid, project_dir)
            if set(entry["path"] for entry in journal["entries"]) != set(modes):
                raise RuntimeError("release transaction path set is incomplete")
            if action == "rollback":
                rollback_transaction(txdir, journal)
                daemon_reload()
                receipt = write_rollback_receipt(rollback_receipt(journal), modes)
                verify_rollback_generations(receipt)
                safe_remove_transaction(txdir)
                verify_rollback_generations(receipt)
                remove_marker(txid)
                return "rolled-back"
            for entry in journal["entries"]:
                if file_generation(entry["path"], entry["old"], entry["sha256"], entry["mode"]) != "new":
                    raise RuntimeError("cannot finalize a non-current release")
            daemon_reload()
            atomic_write(RELEASE_MANIFEST, canonical(release_manifest(journal)) + b"\n", 0o600)
            safe_remove_transaction(txdir)
            remove_marker(txid)
            return "finalized"
        except BaseException:
            if action != "rollback" and created_marker and not transaction_exists(txdir):
                remove_marker(txid)
            raise
    finally:
        if deploy_fd is not None:
            os.close(deploy_fd)
        os.close(global_fd)
def main():
    if len(sys.argv) != 5:
        print("PITR release transport: invalid invocation", file=sys.stderr)
        return 64
    if os.geteuid() != 0 or not hasattr(os, "O_NOFOLLOW"):
        print("PITR release transport: root Linux execution is required", file=sys.stderr)
        return 77
    action, txid, project_dir, compose_file = sys.argv[1:]
    try:
        payload = read_payload(sys.stdin.buffer, action == "apply")
        result = execute(action, txid, project_dir, compose_file, payload)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print("PITR release transport: " + str(exc), file=sys.stderr)
        return 1
    print(result)
    return 0
raise SystemExit(main())
'''.strip()
