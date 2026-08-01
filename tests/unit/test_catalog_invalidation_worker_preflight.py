import pytest

from services.catalog_invalidation_worker import CatalogInvalidationWorker
from services.catalog_invalidation_contracts import (
    CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
)
from services.catalog_purge_service import CloudflarePurgeConfig
from services.communications.processing_scope import (
    ALL_EVENT_TYPES,
    CANARY_EVENT_TYPES,
    STAFF_BOT_EVENT_TYPES,
)
from services.communications.template_registry import SUPPORTED_EVENT_TYPES


def test_communications_dispatcher_cannot_claim_catalog_invalidation_events():
    assert CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT not in ALL_EVENT_TYPES
    assert CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT not in CANARY_EVENT_TYPES
    assert CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT not in STAFF_BOT_EVENT_TYPES
    assert CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT not in SUPPORTED_EVENT_TYPES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "expected_mode"),
    [
        (
            CloudflarePurgeConfig(enabled=False, dry_run=True),
            "disabled",
        ),
        (
            CloudflarePurgeConfig(
                zone_id="zone",
                api_token="token",
                enabled=True,
                dry_run=True,
            ),
            "dry_run",
        ),
        (
            CloudflarePurgeConfig(
                enabled=True,
                dry_run=False,
            ),
            "missing_config",
        ),
        (
            CloudflarePurgeConfig(
                zone_id="zone",
                api_token="token",
                enabled=True,
                dry_run=False,
                zone_hostnames=("https://mvn.by",),
            ),
            "invalid_config",
        ),
    ],
)
async def test_configuration_preflight_does_not_claim_or_consume_attempts(
    config,
    expected_mode,
):
    def fail_session_factory():
        raise AssertionError("database must not be opened before live preflight")

    worker = CatalogInvalidationWorker(
        worker_id="test-worker",
        session_factory=fail_session_factory,
        purge_config=config,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "configuration_blocked"
    assert outcome.configuration_mode == expected_mode
