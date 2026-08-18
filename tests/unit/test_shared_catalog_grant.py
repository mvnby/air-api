from __future__ import annotations

import pytest

from models import Product, Storefront, Tenant, TenantCatalogGrant, TenantOffer
from services.shared_catalog_grant_manifest import (
    SharedCatalogGrantManifest,
    SharedCatalogGrantManifestError,
)
from services.shared_catalog_grant_plan_token import SharedCatalogGrantPlanToken
from services.shared_catalog_grant_planner import SharedCatalogGrantPlanner
from services.tenant_offer_mutation_staging_service import (
    TenantOfferMutationStagingService,
)


def _manifest(**overrides) -> SharedCatalogGrantManifest:
    payload = {
        "version": 1,
        "tenant_slug": "polotsk",
        "storefront_slug": "main",
        "mode": "all_published",
        "price_policy": "inherit_master",
        "owner_type": "system",
        "actor_username": "system:catalog-grant-sync",
        "batch_size": 100,
    }
    payload.update(overrides)
    return SharedCatalogGrantManifest.normalize(payload)


def test_manifest_is_closed_deterministic_and_system_owned() -> None:
    assert _manifest().fingerprint == _manifest().fingerprint
    with pytest.raises(SharedCatalogGrantManifestError, match="unknown or missing"):
        _manifest(tenant_price_override=True)
    with pytest.raises(SharedCatalogGrantManifestError, match="system-owned"):
        _manifest(owner_type="tenant")
    with pytest.raises(SharedCatalogGrantManifestError, match="between 1 and 200"):
        _manifest(batch_size=201)


def test_plan_token_is_domain_separated_expiring_and_tamper_evident() -> None:
    digest = "a" * 64
    token = SharedCatalogGrantPlanToken.issue(
        plan_digest=digest,
        now=1_000,
        nonce="b" * 32,
    )
    assert SharedCatalogGrantPlanToken.verify(token, now=1_010).plan_digest == digest
    with pytest.raises(RuntimeError, match="signature"):
        SharedCatalogGrantPlanToken.verify(token[:-1] + "A", now=1_010)
    with pytest.raises(RuntimeError, match="expired"):
        SharedCatalogGrantPlanToken.verify(token, now=2_000)


def test_inherited_offer_tracks_master_but_adopted_manual_price_is_preserved() -> None:
    grant = TenantCatalogGrant(
        id=9,
        tenant_id=2,
        storefront_id=3,
        mode="all_published",
        price_policy="inherit_master",
        owner_type="system",
        status="active",
        revision=1,
        created_by_username="system:catalog-grant-sync",
        updated_by_username="system:catalog-grant-sync",
    )
    inherited_product = Product(
        id=10,
        title="Inherited",
        slug="inherited",
        price=2200,
        old_price=2400,
        is_published=True,
    )
    inherited_offer = TenantOffer(
        id=11,
        tenant_id=2,
        storefront_id=3,
        product_id=10,
        catalog_grant_id=9,
        price=2000,
        old_price=2300,
        price_source="inherited_master",
        status="active",
        is_published=True,
        created_by_username="system",
        updated_by_username="system",
    )
    manual_product = Product(
        id=12,
        title="Manual",
        slug="manual",
        price=5000,
        old_price=5500,
        is_published=True,
    )
    manual_offer = TenantOffer(
        id=13,
        tenant_id=2,
        storefront_id=3,
        product_id=12,
        price=4900,
        old_price=5200,
        price_source="manual",
        status="disabled",
        is_published=False,
        created_by_username="system",
        updated_by_username="system",
    )

    changes, blockers = SharedCatalogGrantPlanner._offer_changes(
        rows=[
            (inherited_product, inherited_offer),
            (manual_product, manual_offer),
        ],
        grant=grant,
        desired_status="active",
    )

    assert blockers == []
    inherited = changes[0]["fields"]
    assert inherited["price"]["after"] == 2200
    assert inherited["old_price"]["after"] == 2400
    manual = changes[1]["fields"]
    assert manual["catalog_grant_id"]["after"] == 9
    assert manual["status"]["after"] == "active"
    assert "price" not in manual
    assert "old_price" not in manual


def test_unpublished_linked_offer_is_always_deactivated() -> None:
    grant = TenantCatalogGrant(
        id=4,
        tenant_id=2,
        storefront_id=3,
        status="active",
        revision=1,
        created_by_username="system",
        updated_by_username="system",
    )
    product = Product(
        id=20,
        title="Hidden",
        slug="hidden",
        price=1000,
        is_published=False,
    )
    offer = TenantOffer(
        id=21,
        tenant_id=2,
        storefront_id=3,
        product_id=20,
        catalog_grant_id=4,
        price=1000,
        price_source="inherited_master",
        status="active",
        is_published=True,
        created_by_username="system",
        updated_by_username="system",
    )

    changes, blockers = SharedCatalogGrantPlanner._offer_changes(
        rows=[(product, offer)],
        grant=grant,
        desired_status="active",
    )

    assert blockers == []
    assert changes[0]["fields"]["status"]["after"] == "disabled"
    assert changes[0]["fields"]["is_published"]["after"] is False


@pytest.mark.parametrize(
    ("price", "old_price"),
    [(-1, None), (1000, 999)],
)
def test_invalid_master_price_is_a_plan_blocker(
    price: int,
    old_price: int | None,
) -> None:
    product = Product(
        id=30,
        title="Invalid master price",
        slug="invalid-master-price",
        price=price,
        old_price=old_price,
        is_published=True,
    )

    changes, blockers = SharedCatalogGrantPlanner._offer_changes(
        rows=[(product, None)],
        grant=None,
        desired_status="active",
    )

    assert changes == []
    assert blockers == ["product 30 has invalid master price semantics"]


def test_initial_grant_activation_requires_draft_but_active_resync_is_allowed() -> None:
    manifest = _manifest()
    tenant = Tenant(
        id=2,
        slug="polotsk",
        display_name="Двина Климат",
        status="active",
        is_system=False,
    )
    storefront = Storefront(
        id=3,
        tenant_id=2,
        slug="main",
        display_name="Двина Климат",
        status="active",
        is_default=True,
    )
    blocked = SharedCatalogGrantPlanner._scope_blockers(
        tenant=tenant,
        storefront=storefront,
        grant=None,
        desired_status="active",
        manifest=manifest,
    )
    assert blocked == [
        "initial grant activation requires a non-routable draft storefront"
    ]

    grant = TenantCatalogGrant(
        id=4,
        tenant_id=2,
        storefront_id=3,
        status="active",
        revision=1,
        created_by_username="system",
        updated_by_username="system",
    )
    assert (
        SharedCatalogGrantPlanner._scope_blockers(
            tenant=tenant,
            storefront=storefront,
            grant=grant,
            desired_status="active",
            manifest=manifest,
        )
        == []
    )


def test_operator_price_change_promotes_inherited_offer_to_manual_override() -> None:
    offer = TenantOffer(
        id=40,
        tenant_id=2,
        storefront_id=3,
        product_id=30,
        catalog_grant_id=4,
        price=1000,
        old_price=1200,
        price_source="inherited_master",
        status="active",
        is_published=True,
        created_by_username="system",
        updated_by_username="system",
    )

    status_only = TenantOfferMutationStagingService.with_manual_price_provenance(
        offer,
        {
            "price": 1000,
            "old_price": 1200,
            "status": "disabled",
            "is_published": False,
        },
    )
    assert "price_source" not in status_only

    price_change = TenantOfferMutationStagingService.with_manual_price_provenance(
        offer,
        {
            "price": 1100,
            "old_price": 1200,
            "status": "active",
            "is_published": True,
        },
    )
    assert price_change["price_source"] == "manual"
    changes = TenantOfferMutationStagingService.apply_changes(
        offer,
        price_change,
        actor_username="root",
    )
    assert changes["price_source"] == {
        "before": "inherited_master",
        "after": "manual",
    }
    assert offer.catalog_grant_id == 4
