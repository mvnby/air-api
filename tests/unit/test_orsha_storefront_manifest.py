from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models import Storefront, StorefrontDomain, Tenant
from models.tenancy import TenantScope
from scripts.manage_orsha_storefront import (
    _read_manifest,
    action_and_mode,
    build_parser,
    load_offer_specs,
    validate_args,
)
from services.catalog_revision_service import CatalogRevisionService
from services.orsha_storefront_bootstrap_planner import (
    OrshaStorefrontBootstrapPlanner,
)
from services.orsha_storefront_bootstrap_state import LoadedOrshaStorefrontState
from services.orsha_storefront_manifest import (
    OrshaStorefrontManifest,
    OrshaStorefrontManifestError,
)
from services.tenant_offer_catalog_invalidation import (
    TenantOfferCatalogInvalidationAdapter,
    TenantOfferCatalogInvalidationUnavailableError,
)


def _offers(count: int = 5) -> list[dict]:
    return [
        {
            "product_slug": f"canary-{index}",
            "price": 1_000 + index,
            "old_price": 1_200 + index,
            "is_published": index == 0,
        }
        for index in range(count)
    ]


def test_manifest_normalizes_exact_bounded_offer_contract() -> None:
    values = _offers()
    values[1] = {
        "product_id": 42,
        "price": "1001",
        "old_price": None,
        "is_published": False,
    }

    result = OrshaStorefrontManifest.normalize(reversed(values))

    assert len(result) == 5
    assert {offer.reference for offer in result} == {
        "id:42",
        "slug:canary-0",
        "slug:canary-2",
        "slug:canary-3",
        "slug:canary-4",
    }
    assert next(offer for offer in result if offer.product_id == 42).price == 1001


@pytest.mark.parametrize("count", [0, 4, 21])
def test_manifest_rejects_unbounded_offer_counts(count: int) -> None:
    with pytest.raises(OrshaStorefrontManifestError, match="between 5 and 20"):
        OrshaStorefrontManifest.normalize(_offers(count))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"product_id": 1}, "exactly one"),
        ({"product_id": 1, "product_slug": "one"}, "exactly one"),
        ({"product_slug": "bad/path"}, "product_slug is invalid"),
        ({"is_published": "true"}, "true or false"),
        ({"price": -1}, "non-negative"),
        ({"old_price": 999}, "greater than or equal"),
        ({"unexpected": "value"}, "unknown fields"),
    ],
)
def test_manifest_rejects_ambiguous_or_inexact_values(
    mutation: dict,
    message: str,
) -> None:
    values = _offers()
    values[0].update(mutation)
    if mutation == {"product_id": 1}:
        values[0].pop("product_slug")
        values[0].pop("product_id")
    if mutation == {"price": -1}:
        values[0]["old_price"] = None

    with pytest.raises(OrshaStorefrontManifestError, match=message):
        OrshaStorefrontManifest.normalize(values)


def test_manifest_rejects_duplicate_references() -> None:
    values = _offers()
    values[1]["product_slug"] = values[0]["product_slug"]

    with pytest.raises(OrshaStorefrontManifestError, match="duplicate"):
        OrshaStorefrontManifest.normalize(values)


def test_cli_defaults_to_bootstrap_plan_and_requires_explicit_inputs() -> None:
    parser = build_parser()
    args = parser.parse_args(["--hostname", "orsha.mvn.by"])

    assert action_and_mode(args) == ("bootstrap", "plan")
    with pytest.raises(SystemExit):
        validate_args(args, parser)

    args = parser.parse_args(
        [
            "--disable",
            "--hostname",
            "orsha.mvn.by",
            "--plan-token",
            "a" * 64,
        ]
    )
    validate_args(args, parser)
    assert action_and_mode(args) == ("disable", "execute")


def test_cli_parses_exact_slug_and_id_offer_arguments() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--hostname",
            "orsha.mvn.by",
            "--offer-slug",
            "model-one",
            "1000",
            "-",
            "true",
            "--offer-id",
            "42",
            "2000",
            "2500",
            "false",
        ]
    )
    validate_args(args, parser)

    assert load_offer_specs(args) == [
        {
            "product_slug": "model-one",
            "price": "1000",
            "old_price": None,
            "is_published": True,
        },
        {
            "product_id": "42",
            "price": "2000",
            "old_price": "2500",
            "is_published": False,
        },
    ]


def test_cli_manifest_file_is_closed_schema_and_bounded(tmp_path) -> None:
    valid = tmp_path / "offers.json"
    valid.write_text(
        '{"version": 1, "offers": [{"product_slug": "one"}]}',
        encoding="utf-8",
    )
    assert _read_manifest(valid) == [{"product_slug": "one"}]

    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        '{"version": 1, "offers": [], "tenant_id": 2}',
        encoding="utf-8",
    )
    with pytest.raises(OrshaStorefrontManifestError, match="exactly"):
        _read_manifest(invalid)

    oversized = tmp_path / "large.json"
    oversized.write_text("x" * (64 * 1024 + 1), encoding="utf-8")
    with pytest.raises(OrshaStorefrontManifestError, match="64 KiB"):
        _read_manifest(oversized)


@pytest.mark.parametrize(
    "hostname",
    [
        "mvn.by",
        "orsha.example.com",
        "orsha.mvn.by:443",
        "other-orsha.mvn.by",
        "https://orsha.mvn.by",
    ],
)
def test_hostname_contract_rejects_non_orsha_mvn_hosts(hostname: str) -> None:
    with pytest.raises(ValueError, match="hostname"):
        OrshaStorefrontBootstrapPlanner.normalize_hostname(hostname)


def test_hostname_contract_normalizes_case_and_trailing_dot() -> None:
    assert (
        OrshaStorefrontBootstrapPlanner.normalize_hostname("ORSHA-INTERNAL.MVN.BY.")
        == "orsha-internal.mvn.by"
    )


def test_domain_cardinality_and_primary_ownership_fail_closed() -> None:
    tenant = Tenant(
        id=1,
        slug="mvn",
        display_name="MVN",
        kind="operator",
        status="active",
        is_system=True,
    )
    storefront = Storefront(
        id=2,
        tenant_id=1,
        slug="orsha",
        display_name="MVN Орша",
        status="draft",
        city="Орша",
        default_locale="ru-BY",
        currency="BYN",
        is_default=False,
    )
    domains = [
        StorefrontDomain(
            id=3,
            storefront_id=2,
            hostname="orsha.mvn.by",
            status="pending",
            is_primary=False,
        ),
        StorefrontDomain(
            id=4,
            storefront_id=2,
            hostname="orsha-extra.mvn.by",
            status="pending",
            is_primary=False,
        ),
    ]
    state = LoadedOrshaStorefrontState(
        tenant=tenant,
        storefront=storefront,
        domains=domains,
        hostname_owner=domains[0],
        offers=[],
        resolved_offers=[],
        resolution_blockers=[],
        crm_counts={"customers_in_tenant": 0, "leads": 0, "orders": 0},
    )

    blockers = OrshaStorefrontBootstrapPlanner.base_blockers(
        state,
        hostname="orsha.mvn.by",
    )

    assert "Orsha storefront has more than one domain" in blockers
    assert "Orsha storefront domain is not primary" in blockers


def test_routable_disable_requires_catalog_invalidation_foundation(
    monkeypatch,
) -> None:
    monkeypatch.delattr(CatalogRevisionService, "stage_invalidation", raising=False)
    tenant = Tenant(
        id=1,
        slug="mvn",
        display_name="MVN",
        kind="operator",
        status="active",
        is_system=True,
    )
    storefront = Storefront(
        id=2,
        tenant_id=1,
        slug="orsha",
        display_name="MVN Орша",
        status="active",
        city="Орша",
        is_default=False,
    )
    domain = StorefrontDomain(
        id=3,
        storefront_id=2,
        hostname="orsha.mvn.by",
        status="active",
        is_primary=True,
    )
    state = LoadedOrshaStorefrontState(
        tenant=tenant,
        storefront=storefront,
        domains=[domain],
        hostname_owner=domain,
        offers=[],
        resolved_offers=[],
        resolution_blockers=[],
        crm_counts={"customers_in_tenant": 0, "leads": 0, "orders": 0},
    )

    blockers, changes = OrshaStorefrontBootstrapPlanner._plan_disable(state)

    assert blockers == ["storefront catalog invalidation staging is unavailable"]
    assert len(changes) == 2


def test_lifecycle_modules_do_not_own_transactions_or_delete_rows() -> None:
    root = Path(__file__).resolve().parents[2]
    paths = (
        root / "crud/orsha_storefront_bootstrap.py",
        root / "services/orsha_storefront_bootstrap_service.py",
        root / "services/tenant_offer_mutation_staging_service.py",
        root / "services/orsha_storefront_lifecycle_staging.py",
    )
    forbidden: list[tuple[str, int, str]] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"commit", "rollback", "delete"}
            ):
                forbidden.append((path.name, node.lineno, node.func.attr))

    assert forbidden == []


@pytest.mark.asyncio
async def test_catalog_invalidation_adapter_is_safe_before_revision_release(
    monkeypatch,
) -> None:
    monkeypatch.delattr(CatalogRevisionService, "stage_invalidation", raising=False)

    result = await TenantOfferCatalogInvalidationAdapter.stage(
        SimpleNamespace(),
        reason="tenant_offer_updated",
        tenant_scope=TenantScope(tenant_id=1, storefront_id=9, is_system=True),
        product_ids=[1],
        slugs=["one"],
    )

    assert result is False

    with pytest.raises(TenantOfferCatalogInvalidationUnavailableError):
        await TenantOfferCatalogInvalidationAdapter.stage(
            SimpleNamespace(),
            reason="orsha_storefront_activated",
            tenant_scope=TenantScope(
                tenant_id=1,
                storefront_id=9,
                is_system=True,
            ),
            product_ids=[1],
            slugs=["one"],
            required=True,
        )


@pytest.mark.asyncio
async def test_catalog_invalidation_adapter_is_future_safe(monkeypatch) -> None:
    stage = AsyncMock(return_value={"staged": True})
    monkeypatch.setattr(
        CatalogRevisionService,
        "stage_invalidation",
        stage,
        raising=False,
    )
    session = SimpleNamespace()
    scope = TenantScope(tenant_id=1, storefront_id=9, is_system=True)

    result = await TenantOfferCatalogInvalidationAdapter.stage(
        session,
        reason="tenant_offer_updated",
        tenant_scope=scope,
        product_ids=[2, 1, 2],
        slugs=["two", "one", "two"],
    )

    assert result is True
    stage.assert_awaited_once_with(
        session,
        reason="tenant_offer_updated",
        tenant_scope=scope,
        product_ids=(1, 2),
        slugs=("one", "two"),
    )
