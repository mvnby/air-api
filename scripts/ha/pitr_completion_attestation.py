"""Completion-receipt program embedded in privileged PITR SSH calls."""

from __future__ import annotations


REMOTE_COMPLETION_ATTESTATION = r'''
COMPLETION_ROOT = "/run/mvn-postgres-pitr-completions"
COMPLETION_UID = 0
COMPLETION_GID = 0
COMPLETION_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
COMPLETION_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
COMPLETION_ALLOWED_PHASES = {
    "preflight",
    "provision-node",
    "configure-node",
    "scrub-node",
    "basebackup",
    "enable-archive-env",
    "enable-timers",
    "restore-drill",
    "verify",
}
COMPLETION_STALE_AFTER_NS = 300 * 1_000_000_000


def _completion_payload(
    nonce,
    transaction_id,
    phase,
    project_dir,
    compose_file,
    asset_manifest,
    wrapper_digest,
):
    if COMPLETION_NONCE_RE.fullmatch(nonce) is None:
        raise RuntimeError("PITR completion nonce is invalid")
    if re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None:
        raise RuntimeError("PITR completion transaction ID is invalid")
    if phase not in COMPLETION_ALLOWED_PHASES:
        raise RuntimeError("PITR completion phase is invalid")
    if project_dir not in ALLOWED_PROJECT_DIRS:
        raise RuntimeError("PITR completion project is invalid")
    if os.path.join(project_dir, compose_file) not in ALLOWED_COMPOSE_PATHS:
        raise RuntimeError("PITR completion compose file is invalid")
    if COMPLETION_DIGEST_RE.fullmatch(wrapper_digest) is None:
        raise RuntimeError("PITR completion wrapper digest is invalid")
    return (
        json.dumps(
            {
                "asset_manifest_sha256": hashlib.sha256(
                    asset_manifest.encode()
                ).hexdigest(),
                "compose_file": compose_file,
                "nonce": nonce,
                "phase": phase,
                "project_dir": project_dir,
                "transaction_id": transaction_id,
                "version": 1,
                "wrapper_sha256": wrapper_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _completion_root(*, create):
    if create:
        try:
            os.mkdir(COMPLETION_ROOT, 0o700)
        except FileExistsError:
            pass
    metadata = os.lstat(COMPLETION_ROOT)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != COMPLETION_UID
        or metadata.st_gid != COMPLETION_GID
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("PITR completion root metadata is unsafe")
    return os.listdir(COMPLETION_ROOT)


def _validate_stale_receipt(path, name, before):
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != COMPLETION_UID
        or before.st_gid != COMPLETION_GID
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size <= 0
        or before.st_size > 2048
    ):
        raise RuntimeError("stale PITR completion receipt metadata is unsafe")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError("stale PITR completion receipt changed while opening")
        payload = os.read(descriptor, 2049)
        finished = os.fstat(descriptor)
        if len(payload) != opened.st_size or os.read(descriptor, 1):
            raise RuntimeError("stale PITR completion receipt size is invalid")
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ) != (
            finished.st_dev,
            finished.st_ino,
            finished.st_size,
            finished.st_mtime_ns,
            finished.st_ctime_ns,
        ):
            raise RuntimeError("stale PITR completion receipt changed while reading")
    finally:
        os.close(descriptor)
    try:
        record = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stale PITR completion receipt is invalid") from exc
    expected_keys = {
        "asset_manifest_sha256",
        "compose_file",
        "nonce",
        "phase",
        "project_dir",
        "transaction_id",
        "version",
        "wrapper_sha256",
    }
    if not isinstance(record, dict) or set(record) != expected_keys:
        raise RuntimeError("stale PITR completion receipt schema is invalid")
    string_keys = expected_keys - {"version"}
    if (
        any(not isinstance(record[key], str) for key in string_keys)
        or type(record["version"]) is not int
        or record["version"] != 1
        or name != f'{record["nonce"]}.json'
        or COMPLETION_NONCE_RE.fullmatch(record["nonce"]) is None
        or COMPLETION_NONCE_RE.fullmatch(record["transaction_id"]) is None
        or record["phase"] not in COMPLETION_ALLOWED_PHASES
        or record["project_dir"] not in ALLOWED_PROJECT_DIRS
        or os.path.join(record["project_dir"], record["compose_file"])
        not in ALLOWED_COMPOSE_PATHS
        or COMPLETION_DIGEST_RE.fullmatch(record["asset_manifest_sha256"]) is None
        or COMPLETION_DIGEST_RE.fullmatch(record["wrapper_sha256"]) is None
    ):
        raise RuntimeError("stale PITR completion receipt contract is invalid")
    canonical = (
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    if payload != canonical:
        raise RuntimeError("stale PITR completion receipt is not canonical")


def scavenge_completion_receipts(*, now_ns=None):
    entries = _completion_root(create=True)
    current_ns = time.time_ns() if now_ns is None else now_ns
    removed = False
    for name in entries:
        receipt_match = re.fullmatch(r"[0-9a-f]{32}\.json", name)
        temporary_match = re.fullmatch(r"\.[0-9a-f]{32}\.[0-9]+\.tmp", name)
        if receipt_match is None and temporary_match is None:
            raise RuntimeError("PITR completion root contains an unknown entry")
        path = os.path.join(COMPLETION_ROOT, name)
        before = os.lstat(path)
        if receipt_match is not None:
            _validate_stale_receipt(path, name, before)
        elif (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != COMPLETION_UID
            or before.st_gid != COMPLETION_GID
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size > 2048
        ):
            raise RuntimeError("stale PITR completion temporary metadata is unsafe")
        if current_ns < before.st_mtime_ns:
            raise RuntimeError("PITR completion entry timestamp is in the future")
        if current_ns - before.st_mtime_ns < COMPLETION_STALE_AFTER_NS:
            continue
        final = os.lstat(path)
        if (final.st_dev, final.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError("stale PITR completion entry changed before removal")
        os.unlink(path)
        removed = True
    remaining = os.listdir(COMPLETION_ROOT)
    if len(remaining) >= 64:
        raise RuntimeError("recent PITR completion receipts require bounded retry")
    if removed:
        root_fd = os.open(
            COMPLETION_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        )
        try:
            os.fsync(root_fd)
        finally:
            os.close(root_fd)
    return len(entries) - len(remaining)


def _read_completion(path, expected):
    before = os.lstat(path)
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != COMPLETION_UID
        or before.st_gid != COMPLETION_GID
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size != len(expected)
    ):
        raise RuntimeError("PITR completion receipt metadata is unsafe")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError("PITR completion receipt changed while opening")
        payload = os.read(descriptor, len(expected) + 1)
        finished = os.fstat(descriptor)
        if payload != expected or os.read(descriptor, 1):
            raise RuntimeError("PITR completion receipt content is invalid")
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ) != (
            finished.st_dev,
            finished.st_ino,
            finished.st_size,
            finished.st_mtime_ns,
            finished.st_ctime_ns,
        ):
            raise RuntimeError("PITR completion receipt changed while reading")
        return opened.st_dev, opened.st_ino
    finally:
        os.close(descriptor)


def write_completion_receipt(
    nonce,
    transaction_id,
    phase,
    project_dir,
    compose_file,
    asset_manifest,
    wrapper_digest,
):
    expected = _completion_payload(
        nonce,
        transaction_id,
        phase,
        project_dir,
        compose_file,
        asset_manifest,
        wrapper_digest,
    )
    entries = _completion_root(create=True)
    if len(entries) >= 64:
        raise RuntimeError("too many recent PITR completion receipts")
    target = os.path.join(COMPLETION_ROOT, f"{nonce}.json")
    temporary = os.path.join(COMPLETION_ROOT, f".{nonce}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.fchown(descriptor, COMPLETION_UID, COMPLETION_GID)
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(expected):
            written = os.write(descriptor, expected[offset:])
            if written <= 0:
                raise RuntimeError("PITR completion receipt write made no progress")
            offset += written
        os.fsync(descriptor)
    except BaseException:
        os.unlink(temporary)
        raise
    finally:
        os.close(descriptor)
    try:
        os.lstat(target)
    except FileNotFoundError:
        pass
    else:
        os.unlink(temporary)
        raise RuntimeError("PITR completion nonce already exists")
    os.replace(temporary, target)
    root_fd = os.open(COMPLETION_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(root_fd)
    finally:
        os.close(root_fd)
    _read_completion(target, expected)


def consume_completion_receipt(
    nonce,
    transaction_id,
    phase,
    project_dir,
    compose_file,
    asset_manifest,
    wrapper_digest,
):
    expected = _completion_payload(
        nonce,
        transaction_id,
        phase,
        project_dir,
        compose_file,
        asset_manifest,
        wrapper_digest,
    )
    _completion_root(create=False)
    target = os.path.join(COMPLETION_ROOT, f"{nonce}.json")
    identity = _read_completion(target, expected)
    final = os.lstat(target)
    if (final.st_dev, final.st_ino) != identity:
        raise RuntimeError("PITR completion receipt changed before removal")
    os.unlink(target)
    root_fd = os.open(COMPLETION_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(root_fd)
    finally:
        os.close(root_fd)


def write_completion_after_status(status, *receipt_fields):
    if status == 0:
        write_completion_receipt(*receipt_fields)
    return status


def consume_completion_after_status(status, *receipt_fields):
    if status == 0:
        consume_completion_receipt(*receipt_fields)
    return status


def discard_completion_receipt(*receipt_fields):
    try:
        consume_completion_receipt(*receipt_fields)
    except FileNotFoundError:
        return False
    return True
'''.strip()
