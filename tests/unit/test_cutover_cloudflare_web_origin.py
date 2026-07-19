import pytest

from scripts.cutover_cloudflare_web_origin import (
    CloudflareError,
    Config,
    audit,
    cutover,
    probe_dns_write,
    rollback,
)


class FakeClient:
    def __init__(self, *, dns_write: bool = True) -> None:
        self.config = Config(
            token="secret",
            account_id="account",
            zone_id="zone",
            project="mvn-by",
            origin_ip="153.80.244.78",
        )
        self.pages = set(self.config.domains)
        self.records = {
            domain: [
                {
                    "id": f"pages-{domain}",
                    "type": "CNAME",
                    "name": domain,
                    "content": "mvn-by.pages.dev",
                    "proxied": True,
                    "meta": {"managed_by_apps": True},
                }
            ]
            for domain in self.config.domains
        }
        self.records["mvn.by"].extend(
            [
                {
                    "id": "mail-mx",
                    "type": "MX",
                    "name": "mvn.by",
                    "content": "mx.example.test",
                    "proxied": False,
                },
                {
                    "id": "mail-spf",
                    "type": "TXT",
                    "name": "mvn.by",
                    "content": "v=spf1 -all",
                    "proxied": False,
                },
            ]
        )
        self.dns_write = dns_write
        self.counter = 0

    def pages_domains(self):
        return set(self.pages)

    def dns_records(self, domain):
        return list(self.records.get(domain, []))

    def delete_pages_domain(self, domain):
        self.pages.remove(domain)

    def add_pages_domain(self, domain):
        self.pages.add(domain)

    def create_dns_record(self, payload):
        if not self.dns_write:
            raise CloudflareError("DNS write forbidden")
        self.counter += 1
        record = {"id": f"record-{self.counter}", **payload}
        self.records.setdefault(payload["name"], []).append(record)
        return record

    def update_dns_record(self, record_id, payload):
        if not self.dns_write:
            raise CloudflareError("DNS write forbidden")
        for name, records in self.records.items():
            for index, record in enumerate(records):
                if record["id"] == record_id:
                    updated = {"id": record_id, **payload}
                    records[index] = updated
                    return updated
        raise AssertionError(f"unknown record {record_id}")

    def delete_dns_record(self, record_id):
        for name, records in self.records.items():
            for index, record in enumerate(records):
                if record["id"] == record_id:
                    del records[index]
                    return
        raise AssertionError(f"unknown record {record_id}")


def test_audit_reports_pages_and_managed_dns_without_token():
    state = audit(FakeClient())

    assert state["pages_domains"] == ["mvn.by", "www.mvn.by"]
    assert state["dns"]["mvn.by"][0]["managed"] is True
    assert len(state["dns"]["mvn.by"]) == 1
    assert "mx.example.test" not in str(state)
    assert "secret" not in str(state)


def test_cutover_replaces_pages_domains_with_proxied_origin_records(monkeypatch):
    monkeypatch.setattr("scripts.cutover_cloudflare_web_origin.time.sleep", lambda _: None)
    client = FakeClient()

    cutover(client)

    assert client.pages == set()
    for domain in client.config.domains:
        web_record = next(
            record for record in client.records[domain] if record["type"] == "A"
        )
        assert web_record["content"] == client.config.origin_ip
        assert web_record["proxied"] is True
    assert {record["type"] for record in client.records["mvn.by"]} == {
        "A",
        "MX",
        "TXT",
    }


def test_cutover_stops_before_pages_mutation_without_dns_write():
    client = FakeClient(dns_write=False)

    with pytest.raises(CloudflareError, match="DNS write forbidden"):
        probe_dns_write(client)

    assert client.pages == set(client.config.domains)


def test_rollback_restores_pages_domains(monkeypatch):
    monkeypatch.setattr("scripts.cutover_cloudflare_web_origin.time.sleep", lambda _: None)
    client = FakeClient()
    cutover(client)

    rollback(client)

    assert client.pages == set(client.config.domains)
    for domain in client.config.domains:
        web_record = next(
            record for record in client.records[domain] if record["type"] == "CNAME"
        )
        assert web_record["content"] == "mvn-by.pages.dev"
    assert {record["type"] for record in client.records["mvn.by"]} == {
        "CNAME",
        "MX",
        "TXT",
    }


def test_cutover_refuses_an_unknown_existing_record(monkeypatch):
    monkeypatch.setattr("scripts.cutover_cloudflare_web_origin.time.sleep", lambda _: None)
    client = FakeClient()
    client.pages.remove("mvn.by")
    client.records["mvn.by"] = [
        {
            "id": "unexpected",
            "type": "A",
            "name": "mvn.by",
            "content": "192.0.2.1",
            "proxied": True,
        }
    ]

    with pytest.raises(CloudflareError, match="neither on Pages"):
        cutover(client)

    assert client.records["mvn.by"][0]["content"] == "192.0.2.1"
