#!/usr/bin/env python3
"""Validate the exact Patroni Compose bytes pinned into a PITR release."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

import yaml

try:
    from scripts.ha.pitr_pinned_ssh import PatroniNode
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_pinned_ssh import PatroniNode  # type: ignore[no-redef]


MAX_COMPOSE_BYTES = 1024 * 1024
API_SERVICES = ("app", "app-blue", "app-green")
WORKER_SERVICE = "communications-worker"
WORKER_COMMAND = "python -m services.communications.runtime"
WORKER_ENV_FILES = {
    (".env", ".ha-app-role.env"),
    ("${MVN_RESERVE_ENV_FILE:-.env}", ".ha-app-role.env"),
}
REVIEWED_PROFILES = {
    ("false", "false"): "dormant",
    ("true", "false"): "canary",
    ("true", "true"): "active",
}
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")


def _decode_compose_from_bundle(node: PatroniNode, rendered: str) -> bytes:
    if not isinstance(rendered, str):
        raise RuntimeError("pinned PITR release bundle is invalid")
    try:
        bundle = json.loads(rendered)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("pinned PITR release bundle is invalid") from exc
    compose_path = f"{node.project_dir}/{node.compose_file}"
    if (
        not isinstance(bundle, dict)
        or set(bundle)
        != {"files", "project_dir", "release_sha256", "version"}
        or type(bundle.get("version")) is not int
        or bundle.get("version") != 1
        or bundle.get("project_dir") != node.project_dir
        or not isinstance(bundle.get("files"), list)
        or not isinstance(bundle.get("release_sha256"), str)
        or HEX_64.fullmatch(bundle["release_sha256"]) is None
    ):
        raise RuntimeError("pinned PITR release bundle contract is invalid")
    try:
        canonical = json.dumps(
            bundle,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, UnicodeEncodeError) as exc:
        raise RuntimeError("pinned PITR release bundle is invalid") from exc
    body = {
        "files": bundle["files"],
        "project_dir": node.project_dir,
        "version": 1,
    }
    body_digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    if rendered.encode("ascii") != canonical or bundle["release_sha256"] != body_digest:
        raise RuntimeError("pinned PITR release bundle digest is invalid")
    matches = [
        item
        for item in bundle["files"]
        if isinstance(item, dict) and item.get("path") == compose_path
    ]
    if len(matches) != 1:
        raise RuntimeError("pinned PITR release bundle has no exact Compose source")
    descriptor = matches[0]
    digest = descriptor.get("sha256")
    if (
        set(descriptor) != {"content", "mode", "path", "sha256"}
        or type(descriptor.get("mode")) is not int
        or descriptor["mode"] != 0o644
        or not isinstance(descriptor.get("content"), str)
        or not isinstance(digest, str)
        or HEX_64.fullmatch(digest) is None
    ):
        raise RuntimeError("pinned PITR Compose descriptor is invalid")
    try:
        content = base64.b64decode(descriptor["content"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("pinned PITR Compose payload is invalid") from exc
    if (
        not content
        or len(content) > MAX_COMPOSE_BYTES
        or hashlib.sha256(content).hexdigest() != digest
    ):
        raise RuntimeError("pinned PITR Compose digest is invalid")
    return content


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"pinned PITR Compose {label} is not a mapping")
    return value


def _profile_from_compose(content: bytes) -> str:
    try:
        document = yaml.safe_load(content)
    except (UnicodeError, yaml.YAMLError) as exc:
        raise RuntimeError("pinned PITR Compose YAML is invalid") from exc
    root = _mapping(document, "document")
    services = _mapping(root.get("services"), "services")
    worker = _mapping(services.get(WORKER_SERVICE), "communications worker")
    environment = _mapping(
        worker.get("environment"),
        "communications worker environment",
    )
    gates = (
        environment.get("COMMUNICATIONS_WORKER_ENABLED"),
        environment.get("COMMUNICATIONS_WORKER_ALLOW_ALL_MODE"),
    )
    profile = REVIEWED_PROFILES.get(gates)
    if profile is None:
        raise RuntimeError("pinned PITR Compose worker profile is not reviewed")
    if (
        worker.get("command") != WORKER_COMMAND
        or not isinstance(worker.get("env_file"), list)
        or tuple(worker["env_file"]) not in WORKER_ENV_FILES
        or not isinstance(worker.get("depends_on"), Mapping)
        or "db" not in worker["depends_on"]
    ):
        raise RuntimeError("pinned PITR Compose worker structure is not reviewed")
    worker_image = worker.get("image")
    if not isinstance(worker_image, str) or not worker_image:
        raise RuntimeError("pinned PITR Compose worker image is invalid")
    for service_name in API_SERVICES:
        service = _mapping(
            services.get(service_name),
            f"{service_name} service",
        )
        image = service.get("image")
        if not isinstance(image, str) or not image or image != worker_image:
            raise RuntimeError("pinned PITR Compose API/worker image mismatch")
    return profile


def validate_target_compose_bundles(
    nodes: Sequence[PatroniNode],
    bundles: Mapping[str, str],
) -> str:
    """Return the one reviewed profile shared by both exact bundle payloads."""

    ordered_nodes = tuple(nodes)
    expected_projects = {node.project_dir for node in ordered_nodes}
    if (
        len(ordered_nodes) != 2
        or len(expected_projects) != 2
        or set(bundles) != expected_projects
    ):
        raise RuntimeError("PITR profile cutover requires two exact node bundles")
    profiles = {
        _profile_from_compose(
            _decode_compose_from_bundle(node, bundles[node.project_dir])
        )
        for node in ordered_nodes
    }
    if len(profiles) != 1:
        raise RuntimeError("pinned PITR Compose profiles differ across cluster nodes")
    return profiles.pop()
