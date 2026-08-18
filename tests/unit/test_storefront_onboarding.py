from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts.manage_storefront_onboarding import (
    build_parser,
    read_manifest,
    validate_args,
)
from services.storefront_onboarding_manifest import (
    StorefrontOnboardingManifest,
    StorefrontOnboardingManifestError,
)
from services.storefront_onboarding_plan_token import StorefrontOnboardingPlanToken
from services.storefront_onboarding_staging import (
    StorefrontOnboardingStagingService,
)
from services.storefront_onboarding_state import StorefrontOnboardingBlockedError


def _payload(*, hostname: str = "polotsk.mvn.by") -> dict:
    return {
        "version": 1,
        "tenant": {
            "slug": "polotsk",
            "display_name": "MVN Полоцк",
            "kind": "independent_seller",
            "is_system": False,
            "lifecycle": "managed",
        },
        "storefront": {
            "slug": "main",
            "display_name": "MVN Полоцк",
            "city": "Полоцк",
            "default_locale": "ru-BY",
            "currency": "BYN",
            "is_default": True,
        },
        "allowed_hostnames": [hostname],
        "offers": [
            {
                "product_slug": "polotsk-model",
                "price": 1_000,
                "old_price": 1_200,
                "is_published": True,
            }
        ],
    }


def test_polotsk_manifest_is_closed_bounded_and_deterministic() -> None:
    first = StorefrontOnboardingManifest.normalize(_payload())
    second = StorefrontOnboardingManifest.normalize(_payload())

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert first.tenant.slug == "polotsk"
    assert first.tenant.lifecycle == "managed"
    assert first.tenant.is_system is False
    assert first.storefront.slug == "main"
    assert first.storefront.is_default is True
    assert first.allowed_hostnames == ("polotsk.mvn.by",)
    assert first.normalize_selected_hostname("POLOTSK.MVN.BY.") == (
        "polotsk.mvn.by"
    )
    assert "password" not in json.dumps(first.to_dict()).casefold()
    assert "secret" not in json.dumps(first.to_dict()).casefold()


def test_non_system_default_storefront_is_not_canonical_mvn_scope() -> None:
    manifest = StorefrontOnboardingManifest.normalize(_payload())

    scope = StorefrontOnboardingStagingService._tenant_scope(
        manifest=manifest,
        tenant_id=2,
        storefront_id=20,
    )

    assert scope.is_system is False
    assert scope.is_canonical_storefront is False


@pytest.mark.parametrize(
    "hostname",
    [
        "mvn.by",
        "www.mvn.by",
        "api.mvn.by",
        "dev.mvn.by",
        "manager.mvn.by",
        "polotsk.mvn.by:443",
        "https://polotsk.mvn.by",
        "localhost",
    ],
)
def test_reserved_or_non_fqdn_hosts_are_denied(hostname: str) -> None:
    with pytest.raises(StorefrontOnboardingManifestError, match="host|Host"):
        StorefrontOnboardingManifest.normalize(_payload(hostname=hostname))


def test_selected_hostname_must_match_exact_manifest_allowlist() -> None:
    manifest = StorefrontOnboardingManifest.normalize(_payload())

    with pytest.raises(StorefrontOnboardingManifestError, match="exact allowlist"):
        manifest.normalize_selected_hostname("polotsk-preview.mvn.by")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"unexpected": True}),
        lambda payload: payload["tenant"].update({"password": "not-allowed"}),
        lambda payload: payload["storefront"].update({"api_secret": "not-allowed"}),
        lambda payload: payload["tenant"].update({"is_system": True}),
        lambda payload: payload["tenant"].update({"kind": "operator"}),
        lambda payload: payload.update({"offers": payload["offers"] * 101}),
    ],
)
def test_manifest_rejects_open_sensitive_or_unbounded_inputs(mutate) -> None:
    payload = _payload()
    mutate(payload)

    with pytest.raises(StorefrontOnboardingManifestError):
        StorefrontOnboardingManifest.normalize(payload)


def test_plan_token_is_signed_fresh_and_bound_to_immutable_digest() -> None:
    digest = "a" * 64
    token = StorefrontOnboardingPlanToken.issue(
        plan_digest=digest,
        now=1_000,
        nonce="b" * 32,
    )

    verified = StorefrontOnboardingPlanToken.verify(token, now=1_100)
    assert verified.plan_digest == digest
    assert verified.issued_at == 1_000
    assert verified.nonce == "b" * 32

    replacement = "A" if token[-1] != "A" else "B"
    with pytest.raises(StorefrontOnboardingBlockedError, match="signature"):
        StorefrontOnboardingPlanToken.verify(token[:-1] + replacement, now=1_100)
    with pytest.raises(StorefrontOnboardingBlockedError, match="expired"):
        StorefrontOnboardingPlanToken.verify(
            token,
            now=1_000 + StorefrontOnboardingPlanToken.MAX_AGE_SECONDS + 1,
        )


def test_each_plan_token_has_a_fresh_nonce() -> None:
    first = StorefrontOnboardingPlanToken.issue(plan_digest="c" * 64, now=2_000)
    second = StorefrontOnboardingPlanToken.issue(plan_digest="c" * 64, now=2_000)

    assert first != second
    assert StorefrontOnboardingPlanToken.verify(first, now=2_000).plan_digest == (
        StorefrontOnboardingPlanToken.verify(second, now=2_000).plan_digest
    )


def test_cli_has_explicit_plan_and_lifecycle_actions() -> None:
    parser = build_parser()
    plan = parser.parse_args(
        [
            "plan",
            "--for-action",
            "verify-domain",
            "--manifest",
            "polotsk.json",
            "--hostname",
            "polotsk.mvn.by",
        ]
    )
    validate_args(plan, parser)

    mutation = parser.parse_args(
        [
            "activate",
            "--manifest",
            "polotsk.json",
            "--hostname",
            "polotsk.mvn.by",
            "--plan-token",
            "reviewed-token",
        ]
    )
    validate_args(mutation, parser)


def test_reviewed_polotsk_example_loads_without_credentials() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = read_manifest(
        root / "config/storefront_onboarding/polotsk.json"
    )

    assert manifest.tenant.slug == "polotsk"
    assert manifest.tenant.display_name == "Двина Климат"
    assert manifest.storefront.slug == "main"
    assert manifest.storefront.display_name == "Двина Климат"
    assert manifest.allowed_hostnames == ("polotsk.mvn.by",)
    assert manifest.offers == ()


def test_generic_lifecycle_modules_do_not_own_transactions_or_delete_rows() -> None:
    root = Path(__file__).resolve().parents[2]
    paths = (
        root / "crud/storefront_onboarding.py",
        root / "services/storefront_onboarding_planner.py",
        root / "services/storefront_onboarding_service.py",
        root / "services/storefront_onboarding_staging.py",
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
    assert all(len(path.read_text(encoding="utf-8").splitlines()) < 700 for path in paths)
