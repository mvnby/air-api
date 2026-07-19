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
        self.dns_write = dns_write
        self.counter = 0

    def pages_domains(self):
        return set(self.pages)

    def dns_records(self, domain):
        return list(self.records.get(domain, []))

    def delete_pages_domain(self, domain):
        self.pages.remove(domain)
        self.records[domain] = []

    def add_pages_domain(self, domain):
        self.pages.add(domain)
        self.records[domain] = [
            {
                "id": f"pages-{domain}",
                "type": "CNAME",
                "name": domain,
                "content": "mvn-by.pages.dev",
                "proxied": True,
                "meta": {"managed_by_apps": True},
            }
        ]

    def create_dns_record(self, payload):
        if not self.dns_write:
            raise CloudflareError("DNS write forbidden")
        self.counter += 1
        record = {"id": f"record-{self.counter}", **payload}
        self.records[payload["name"]] = [record]
        return record

    def delete_dns_record(self, record_id):
        for name, records in self.records.items():
            if records and records[0]["id"] == record_id:
                self.records[name] = []
                return
        raise AssertionError(f"unknown record {record_id}")


def test_audit_reports_pages_and_managed_dns_without_token():
    state = audit(FakeClient())

    assert state["pages_domains"] == ["mvn.by", "www.mvn.by"]
    assert state["dns"]["mvn.by"][0]["managed"] is True
    assert "secret" not in str(state)


def test_cutover_replaces_pages_domains_with_proxied_origin_records(monkeypatch):
    monkeypatch.setattr("scripts.cutover_cloudflare_web_origin.time.sleep", lambda _: None)
    client = FakeClient()

    cutover(client)

    assert client.pages == set()
    for domain in client.config.domains:
        assert client.records[domain][0]["type"] == "A"
        assert client.records[domain][0]["content"] == client.config.origin_ip
        assert client.records[domain][0]["proxied"] is True


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
        assert client.records[domain][0]["content"] == "mvn-by.pages.dev"


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
