#!/usr/bin/env python3
"""Reviewed constants and validation for the Patroni rolling transaction."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping


PATRONI_REPOSITORY = "ghcr.io/mvnby/air-api/patroni"
IMAGE_RE = re.compile(
    rf"^{re.escape(PATRONI_REPOSITORY)}@sha256:[0-9a-f]{{64}}$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRANSACTION_RE = re.compile(r"^[0-9a-f]{32}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

EXPECTED_SCOPE = "mvn-postgres"
EXPECTED_PATRONI_VERSION = "4.1.4"
EXPECTED_ARCHIVE_MODE = "on"
EXPECTED_ARCHIVE_TIMEOUT = "300"
EXPECTED_ARCHIVE_COMMAND = '/usr/local/bin/mvn-patroni-archive-wal "%p" "%f"'
LEGACY_ARCHIVE_COMMAND = (
    "test ! -f /postgres-wal-archive/%f && cp %p /postgres-wal-archive/%f "
    "|| test -f /postgres-wal-archive/%f"
)
LEGACY_ARCHIVE_COMMAND_SHA256 = (
    "f7b9b3dc5b5ff2bfd6f69f3d3f5f0fed9faa6a878357bedfa7b9bbf0ab09fa79"
)

NODE_CONTRACTS = {
    "mvn-api": {
        "project_dir": "/opt/air-api",
        "compose_file": "docker-compose.patroni.yml",
        "compose_project": "air-api",
        "data_volume": "air-api_postgres_data",
    },
    "zakup": {
        "project_dir": "/opt/mvn-reserve",
        "compose_file": "docker-compose.patroni.yml",
        "compose_project": "mvn_reserve",
        "data_volume": "mvn_reserve_postgres_data",
    },
}

STAGES = (
    "prepared",
    "staged",
    "standby-updated",
    "switched-over",
    "former-primary-updated",
    "archive-command-applied",
    "archive-proved",
    "finalized",
)


@dataclass(frozen=True)
class RolloutInputs:
    deploy_sha: str
    transaction_id: str
    maintenance_transaction_id: str
    current_image: str
    target_image: str
    apply: bool
    resume: bool

    @classmethod
    def validated(
        cls,
        *,
        deploy_sha: str,
        transaction_id: str,
        maintenance_transaction_id: str,
        current_image: str,
        target_image: str,
        apply: bool,
        resume: bool = False,
    ) -> "RolloutInputs":
        if not COMMIT_RE.fullmatch(deploy_sha):
            raise RuntimeError("deploy SHA must be 40 lowercase hexadecimal characters")
        if not TRANSACTION_RE.fullmatch(transaction_id):
            raise RuntimeError(
                "rollout transaction ID must be 32 lowercase hexadecimal characters"
            )
        if not TRANSACTION_RE.fullmatch(maintenance_transaction_id):
            raise RuntimeError(
                "PITR maintenance transaction ID must be 32 lowercase hexadecimal characters"
            )
        for label, image in (("current", current_image), ("target", target_image)):
            if not IMAGE_RE.fullmatch(image):
                raise RuntimeError(f"{label} Patroni image must be an immutable reviewed digest")
        if current_image == target_image:
            raise RuntimeError("current and target Patroni image digests must differ")
        if sha256_text(LEGACY_ARCHIVE_COMMAND) != LEGACY_ARCHIVE_COMMAND_SHA256:
            raise RuntimeError("compiled legacy archive command digest is invalid")
        if apply is not True:
            raise RuntimeError("production Patroni rollout requires apply=true")
        return cls(
            deploy_sha=deploy_sha,
            transaction_id=transaction_id,
            maintenance_transaction_id=maintenance_transaction_id,
            current_image=current_image,
            target_image=target_image,
            apply=apply,
            resume=resume is True,
        )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def require_stage_transition(current: str, requested: str) -> None:
    if current not in STAGES or requested not in STAGES:
        raise RuntimeError("unknown Patroni rollout journal stage")
    current_index = STAGES.index(current)
    requested_index = STAGES.index(requested)
    if requested_index not in {current_index, current_index + 1}:
        raise RuntimeError(
            f"unsafe Patroni rollout stage transition: {current} -> {requested}"
        )
