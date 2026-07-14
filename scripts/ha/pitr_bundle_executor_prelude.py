"""Imports and immutable policy constants for the remote PITR release executor."""
from __future__ import annotations

REMOTE_RELEASE_BUNDLE_PRELUDE = r'''import base64
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
MAX_BUNDLE, MAX_ASSET = 2097152, 1048576
ROOT_UID = ROOT_GID = 0
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
    LIBEXEC_DIR + "/safe_deploy_lock.py": 0o755,
    LIBEXEC_DIR + "/prepare_google_oauth_token_dir.sh": 0o755,
    "/etc/systemd/system/mvn-postgres-wal-upload.service": 0o644,
    "/etc/systemd/system/mvn-postgres-wal-upload.timer": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.service": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.timer": 0o644,
}
PREVIOUS_RELEASE_ADDITIONS = {LIBEXEC_DIR + "/safe_deploy_lock.py"}
PROJECT_COMPOSE = {
    "/opt/air-api": "/opt/air-api/docker-compose.patroni.yml",
    "/opt/mvn-reserve": "/opt/mvn-reserve/docker-compose.patroni.yml",
}
'''
