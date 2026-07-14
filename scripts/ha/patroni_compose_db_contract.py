#!/usr/bin/env python3
"""Hash the complete Compose contract that can affect the Patroni DB service."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any


RESOURCE_KINDS = ("volumes", "networks", "configs", "secrets")


class ContractError(ValueError):
    """Raised when Compose output cannot be reduced safely."""


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def _named_mount_sources(service: dict[str, Any]) -> set[str]:
    references: set[str] = set()
    mounts = service.get("volumes") or []
    if not isinstance(mounts, list):
        raise ContractError("services.db.volumes must be an array")
    for mount in mounts:
        if isinstance(mount, str):
            source = mount.split(":", 1)[0]
            if source and not source.startswith(("/", ".", "~")):
                references.add(source)
            continue
        if not isinstance(mount, dict):
            raise ContractError("services.db.volumes has an invalid entry")
        if mount.get("type") == "volume":
            source = mount.get("source")
            if not isinstance(source, str) or not source:
                raise ContractError("services.db volume source is invalid")
            references.add(source)
    return references


def _network_sources(service: dict[str, Any]) -> set[str]:
    networks = service.get("networks")
    if networks is None:
        return {"default"}
    if isinstance(networks, dict):
        return set(networks)
    if isinstance(networks, list) and all(isinstance(item, str) for item in networks):
        return set(networks)
    raise ContractError("services.db.networks has an invalid shape")


def _resource_sources(service: dict[str, Any], kind: str) -> set[str]:
    resources = service.get(kind) or []
    if not isinstance(resources, list):
        raise ContractError(f"services.db.{kind} must be an array")
    references: set[str] = set()
    for resource in resources:
        if isinstance(resource, str):
            references.add(resource)
            continue
        if not isinstance(resource, dict):
            raise ContractError(f"services.db.{kind} has an invalid entry")
        source = resource.get("source")
        if not isinstance(source, str) or not source:
            raise ContractError(f"services.db {kind} source is invalid")
        references.add(source)
    return references


def _selected_resources(
    config: dict[str, Any], kind: str, references: set[str]
) -> dict[str, Any]:
    available_raw = config.get(kind)
    if available_raw is None:
        available: dict[str, Any] = {}
    else:
        available = _mapping(available_raw, kind)
    missing = references.difference(available)
    if missing:
        raise ContractError(f"services.db references undefined {kind}")
    return {name: available[name] for name in sorted(references)}


def build_contract(config: dict[str, Any]) -> dict[str, Any]:
    project_name = config.get("name")
    if not isinstance(project_name, str) or not project_name:
        raise ContractError("Compose project name is missing")
    services = _mapping(config.get("services"), "services")
    db = _mapping(services.get("db"), "services.db")

    references = {
        "volumes": _named_mount_sources(db),
        "networks": _network_sources(db),
        "configs": _resource_sources(db, "configs"),
        "secrets": _resource_sources(db, "secrets"),
    }
    return {
        "contract_version": 1,
        "name": project_name,
        "service": db,
        "resources": {
            kind: _selected_resources(config, kind, references[kind])
            for kind in RESOURCE_KINDS
        },
    }


def contract_digest(config: dict[str, Any]) -> str:
    payload = json.dumps(
        build_contract(config),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ContractError("Compose config root must be an object")
        print(contract_digest(config))
    except (ContractError, json.JSONDecodeError) as exc:
        print(f"invalid Patroni Compose contract: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
