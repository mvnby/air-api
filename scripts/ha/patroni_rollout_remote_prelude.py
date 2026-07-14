"""Constant prelude for the self-contained Patroni rollout executor."""

REMOTE_PRELUDE = r'''
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
import time

ROOT = 0
STATE_ROOT = "/var/lib/mvn-patroni-rollout"
TX_ROOT = STATE_ROOT + "/transactions"
LOCK_PATH = "/run/lock/mvn-patroni-rollout.lock"
PITR_MARKER = "/run/mvn-postgres-pitr-maintenance"
HELPER_PATH = "/usr/local/bin/mvn-patroni-archive-wal"
EXPECTED_COMMAND = HELPER_PATH + ' "%p" "%f"'
LEGACY_COMMAND = "test ! -f /postgres-wal-archive/%f && cp %p /postgres-wal-archive/%f || test -f /postgres-wal-archive/%f"
LEGACY_COMMAND_SHA256 = "f7b9b3dc5b5ff2bfd6f69f3d3f5f0fed9faa6a878357bedfa7b9bbf0ab09fa79"
WAL_SIZE = 16 * 1024 * 1024
UNITS_INACTIVE = (
    "mvn-postgres-wal-upload.timer", "mvn-postgres-wal-upload.service",
    "mvn-postgres-basebackup.timer", "mvn-postgres-basebackup.service",
)
NODES = {
    "mvn-api": ("/opt/air-api", "docker-compose.patroni.yml", "air-api", "air-api_postgres_data"),
    "zakup": ("/opt/mvn-reserve", "docker-compose.patroni.yml", "mvn_reserve", "mvn_reserve_postgres_data"),
}
IMAGE_RE = re.compile(r"ghcr[.]io/mvnby/air-api/patroni@sha256:[0-9a-f]{64}")
TX_RE = re.compile(r"[0-9a-f]{32}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")
WAL_RE = re.compile(r"[0-9A-F]{24}(?:[.]partial|[.][0-9A-F]{8}[.]backup)?")
HISTORY_RE = re.compile(r"[0-9A-F]{8}[.]history")
RECORDS = {
    "baseline-primary-mvn-api", "baseline-primary-zakup", "baseline-proved",
    "standby-updated", "switched-over", "former-primary-updated",
    "archive-command-applied", "archive-proved", "final-proved",
    "archive-command-reverted",
}
JOURNAL_ACTIONS = {
    "abort", "apply-archive-command", "finalize", "prove-archive",
    "revert-archive-command", "rollback-node", "switchover", "update-node",
}
READ_ACTIONS = {"attest-archive-runtime", "attest-current-runtime", "attest-runtime-ownership", "attest-target-runtime", "check-legacy-dcs", "check-target-dcs", "preflight", "prove-etcd", "stage"}
COMPLETED = JOURNAL_ACTIONS | {"record:" + name for name in RECORDS}
CLEAN_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root", "LANG": "C", "LC_ALL": "C", "DOCKER_CONTEXT": "default",
}

def die(message):
    raise RuntimeError(message)

def run(args, *, stdin=None, ok=(0,), env=None):
    timeout = 600 if args[:2] == ["docker", "pull"] else 180
    result = subprocess.run(args, input=stdin, text=True, capture_output=True, check=False,
        timeout=timeout, env=CLEAN_ENV if env is None else env)
    if result.returncode not in ok:
        detail = (result.stderr or result.stdout or "command failed").strip()
        die(detail)
    return result.stdout.strip()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"

def sha(value):
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()

def safe_dir(path, mode):
    try:
        os.mkdir(path, mode)
    except FileExistsError:
        pass
    meta = os.lstat(path)
    if (not stat.S_ISDIR(meta.st_mode) or stat.S_ISLNK(meta.st_mode)
            or meta.st_uid != ROOT or meta.st_gid != ROOT
            or stat.S_IMODE(meta.st_mode) != mode):
        die("unsafe rollout directory: " + path)

def atomic(path, payload, mode=0o600):
    parent = os.path.dirname(path)
    stage = os.path.join(parent, ".stage-" + secrets.token_hex(16))
    fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(fd, mode); os.fchown(fd, ROOT, ROOT)
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0: die("short rollout journal write")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(stage, path)
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        try: os.unlink(stage)
        except FileNotFoundError: pass

def read_root_file(path, mode=0o600, maximum=1048576):
    before = os.lstat(path)
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or before.st_uid != ROOT or before.st_gid != ROOT or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != mode or before.st_size > maximum):
        die("unsafe root file: " + path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            die("root file changed while opening: " + path)
        data = os.read(fd, maximum + 1)
        if len(data) > maximum or os.read(fd, 1): die("root file exceeds limit: " + path)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if tuple(getattr(after, x) for x in fields) != tuple(getattr(opened, x) for x in fields):
            die("root file changed while reading: " + path)
        return data
    finally:
        os.close(fd)
'''
