#!/usr/bin/env python3
"""Move mvn.by between Cloudflare Pages and the audited SSR origin."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


API_BASE = "https://api.cloudflare.com/client/v4"
DEFAULT_DOMAINS = ("mvn.by", "www.mvn.by")


class CloudflareError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    token: str
    account_id: str
    zone_id: str
    project: str
    origin_ip: str
    domains: tuple[str, ...] = DEFAULT_DOMAINS

    @classmethod
    def from_env(cls) -> "Config":
        values = {
            "token": os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
            "account_id": os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
            "zone_id": os.getenv("CLOUDFLARE_ZONE_ID", "").strip(),
            "project": os.getenv("CLOUDFLARE_PAGES_PROJECT", "mvn-by").strip(),
            "origin_ip": os.getenv("WEB_ORIGIN_IP", "153.80.244.78").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise CloudflareError(f"missing configuration: {', '.join(missing)}")
        return cls(**values)


class CloudflareClient:
    def __init__(self, config: Config) -> None:
        self.config = config

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{API_BASE}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.config.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                envelope = json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                envelope = json.load(exc)
            except (ValueError, TypeError):
                envelope = {"errors": [{"message": str(exc)}]}
            raise CloudflareError(
                f"Cloudflare {method} {path} failed ({exc.code}): "
                f"{_error_messages(envelope)}"
            ) from exc
        if not envelope.get("success"):
            raise CloudflareError(
                f"Cloudflare {method} {path} failed: {_error_messages(envelope)}"
            )
        return envelope.get("result")

    def pages_domains(self) -> set[str]:
        path = (
            f"/accounts/{self.config.account_id}/pages/projects/"
            f"{urllib.parse.quote(self.config.project, safe='')}/domains"
        )
        return {item["name"] for item in self.request("GET", path)}

    def delete_pages_domain(self, domain: str) -> None:
        path = (
            f"/accounts/{self.config.account_id}/pages/projects/"
            f"{urllib.parse.quote(self.config.project, safe='')}/domains/"
            f"{urllib.parse.quote(domain, safe='')}"
        )
        self.request("DELETE", path)

    def add_pages_domain(self, domain: str) -> None:
        path = (
            f"/accounts/{self.config.account_id}/pages/projects/"
            f"{urllib.parse.quote(self.config.project, safe='')}/domains"
        )
        self.request("POST", path, {"name": domain})

    def dns_records(self, domain: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"name": domain, "per_page": 100})
        return list(
            self.request(
                "GET",
                f"/zones/{self.config.zone_id}/dns_records?{query}",
            )
        )

    def create_dns_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request(
            "POST", f"/zones/{self.config.zone_id}/dns_records", payload
        )

    def update_dns_record(
        self, record_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/zones/{self.config.zone_id}/dns_records/{record_id}",
            payload,
        )

    def delete_dns_record(self, record_id: str) -> None:
        self.request(
            "DELETE", f"/zones/{self.config.zone_id}/dns_records/{record_id}"
        )


def _error_messages(envelope: dict[str, Any]) -> str:
    errors = envelope.get("errors") or []
    return "; ".join(str(item.get("message") or item) for item in errors) or "unknown error"


def _safe_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "type": record.get("type"),
        "name": record.get("name"),
        "content": record.get("content"),
        "proxied": record.get("proxied"),
        "managed": bool((record.get("meta") or {}).get("managed_by_apps")),
    }


def audit(client: CloudflareClient) -> dict[str, Any]:
    pages = client.pages_domains()
    return {
        "pages_project": client.config.project,
        "pages_domains": sorted(pages),
        "origin_ip": client.config.origin_ip,
        "dns": {
            domain: [_safe_record(record) for record in client.dns_records(domain)]
            for domain in client.config.domains
        },
    }


def probe_dns_write(client: CloudflareClient) -> None:
    name = f"_mvn-web-cutover-probe.{client.config.domains[0]}"
    record = client.create_dns_record(
        {
            "type": "TXT",
            "name": name,
            "content": f"cutover-probe-{uuid.uuid4().hex}",
            "ttl": 60,
            "proxied": False,
            "comment": "Temporary write-permission probe; safe to delete",
        }
    )
    try:
        if not record.get("id"):
            raise CloudflareError("DNS write probe returned no record id")
    finally:
        if record.get("id"):
            client.delete_dns_record(record["id"])


def _is_origin_record(record: dict[str, Any], config: Config) -> bool:
    return (
        record.get("type") == "A"
        and record.get("content") == config.origin_ip
        and record.get("proxied") is True
    )


def _single_record(client: CloudflareClient, domain: str) -> dict[str, Any] | None:
    records = client.dns_records(domain)
    if len(records) > 1:
        raise CloudflareError(f"refusing multiple DNS records for {domain}")
    return records[0] if records else None


def _wait_for(
    predicate: Any, description: str, *, attempts: int = 20, interval: float = 1.0
) -> None:
    for _ in range(attempts):
        if predicate():
            return
        time.sleep(interval)
    raise CloudflareError(f"timed out waiting for {description}")


def _restore_pages_domain(client: CloudflareClient, domain: str) -> None:
    record = _single_record(client, domain)
    if record and _is_origin_record(record, client.config):
        client.delete_dns_record(record["id"])
        _wait_for(lambda: not client.dns_records(domain), f"DNS removal for {domain}")
    elif record:
        raise CloudflareError(f"refusing to delete unexpected DNS record for {domain}")
    if domain not in client.pages_domains():
        client.add_pages_domain(domain)
    _wait_for(
        lambda: domain in client.pages_domains(), f"Pages domain restoration for {domain}"
    )


def cutover(client: CloudflareClient) -> None:
    probe_dns_write(client)
    changed: list[str] = []
    active_domain: str | None = None
    try:
        for domain in client.config.domains:
            active_domain = domain
            current = _single_record(client, domain)
            if current and _is_origin_record(current, client.config):
                active_domain = None
                continue
            if domain not in client.pages_domains():
                raise CloudflareError(
                    f"{domain} is neither on Pages nor the expected SSR origin"
                )
            client.delete_pages_domain(domain)
            _wait_for(
                lambda: domain not in client.pages_domains(),
                f"Pages detachment for {domain}",
            )
            _wait_for(
                lambda: not client.dns_records(domain), f"managed DNS removal for {domain}"
            )
            client.create_dns_record(
                {
                    "type": "A",
                    "name": domain,
                    "content": client.config.origin_ip,
                    "ttl": 1,
                    "proxied": True,
                    "comment": "Standalone mvn-web SSR origin",
                }
            )
            _wait_for(
                lambda: bool(
                    (record := _single_record(client, domain))
                    and _is_origin_record(record, client.config)
                ),
                f"SSR origin record for {domain}",
            )
            changed.append(domain)
            active_domain = None
    except Exception:
        recovery = list(reversed(changed))
        if active_domain and active_domain not in recovery:
            recovery.insert(0, active_domain)
        for domain in recovery:
            try:
                _restore_pages_domain(client, domain)
            except Exception as recovery_error:  # noqa: BLE001
                print(f"recovery_failed domain={domain} error={recovery_error}")
        raise


def rollback(client: CloudflareClient) -> None:
    probe_dns_write(client)
    for domain in client.config.domains:
        _restore_pages_domain(client, domain)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("audit", "cutover", "rollback"))
    parser.add_argument(
        "--confirm",
        default="",
        help="Required confirmation: origin IP for cutover, Pages project for rollback",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = Config.from_env()
    client = CloudflareClient(config)
    print(json.dumps(audit(client), ensure_ascii=False, indent=2, sort_keys=True))
    if args.operation == "audit":
        return 0
    expected = config.origin_ip if args.operation == "cutover" else config.project
    if args.confirm != expected:
        raise CloudflareError(f"confirmation must equal {expected!r}")
    if args.operation == "cutover":
        cutover(client)
    else:
        rollback(client)
    print(json.dumps(audit(client), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
