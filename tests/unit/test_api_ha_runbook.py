from pathlib import Path


RUNBOOK = Path(__file__).resolve().parents[2] / "docs/api-ha-runbook.md"


def test_emergency_failover_runbook_spells_out_primary_compose_swap():
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "helper is the source of truth for the host-local promotion mechanics" in text
    assert "cp docker-compose.primary.yml docker-compose.reserve.yml" in text
    assert "docker-compose.reserve.yml.pre-promote.$(date -u +%Y%m%d%H%M%S)" in text
