from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureCategory,
    FeatureProductLink,
    FeatureRule,
    FeatureSeriesLink,
    Product,
    ProductSeries,
)
from services.catalog_revision_service import CatalogRevisionService
from services.feature_resolver_service import FeatureResolverService
from services.feature_rule_engine import get_spec_value, matches_all_rules
from services.spec_normalizer import normalize_specs


WIFI_SPEC_KEYS = (
    "wifi_ready",
    "wifi_builtin",
    "wifi_state",
    "__filter_wifi",
    "__filter_wifi_builtin",
)


def load_tcl_feature_canary_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class TclFeatureCanaryError(RuntimeError):
    pass


class TclFeatureCanaryService:
    def __init__(self, session: AsyncSession, manifest: dict[str, Any]):
        self.session = session
        self.manifest = manifest
        self.actions: list[dict[str, Any]] = []
        self.source_reconciliations: list[dict[str, Any]] = []
        self.brand: Brand | None = None
        self.series: dict[str, ProductSeries] = {}
        self.products: list[Product] = []
        self.skipped_products: list[Product] = []
        self.features: dict[str, Feature] = {}
        self.initial_feature_slugs: set[str] = set()

    async def run(self, *, execute: bool) -> dict[str, Any]:
        await self._load_inventory()
        await self._upsert_features()
        await self._remove_legacy_brand_links()
        await self._remove_stale_series_links()
        await self._remove_stale_product_links()
        await self._normalize_product_states()
        await self._upsert_series_links()
        await self._upsert_derived_links()
        await self.session.flush()

        report = await self._build_report(execute=execute)
        violations = (
            report["cross_brand_violations"]
            + report["duplicate_feature_ids"]
            + report["unexpected_inheritance"]
            + report["missing_expected_features"]
            + report["unexpected_features"]
            + report["unresolved_source_conflicts"]
        )
        if violations:
            raise TclFeatureCanaryError(
                "Canary verification failed: " + json.dumps(violations, ensure_ascii=False)
            )

        if execute and self.actions:
            await CatalogRevisionService.stage_invalidation(
                self.session,
                reason="tcl_2026_feature_canary",
                brand_slugs=[self.manifest["catalog"]["brand_slug"]],
            )
            await self.session.commit()
        return report

    async def _load_inventory(self) -> None:
        brand_slug = self.manifest["catalog"]["brand_slug"]
        self.brand = (
            await self.session.execute(select(Brand).where(Brand.slug == brand_slug))
        ).scalar_one_or_none()
        if self.brand is None:
            raise TclFeatureCanaryError(f"Brand {brand_slug!r} not found")

        allowlist = set(self.manifest["series_allowlist"])
        rows = list(
            (
                await self.session.execute(
                    select(ProductSeries).where(
                        ProductSeries.brand_id == self.brand.id,
                        ProductSeries.slug.in_(allowlist),
                    )
                )
            ).scalars().all()
        )
        self.series = {item.slug: item for item in rows}
        missing = sorted(allowlist - set(self.series))
        if missing:
            raise TclFeatureCanaryError(f"Pilot series not found: {missing}")

        series_ids = [int(item.id) for item in rows]
        self.products = list(
            (
                await self.session.execute(
                    select(Product)
                    .where(Product.brand_id == self.brand.id, Product.series_id.in_(series_ids))
                    .options(selectinload(Product.series))
                    .order_by(Product.series_id, Product.id)
                )
            ).scalars().all()
        )
        if not self.products:
            raise TclFeatureCanaryError("Pilot contains no products")
        self.skipped_products = list(
            (
                await self.session.execute(
                    select(Product)
                    .where(
                        Product.brand_id == self.brand.id,
                        or_(Product.series_id.is_(None), Product.series_id.not_in(series_ids)),
                    )
                    .order_by(Product.id)
                )
            ).scalars().all()
        )

        feature_slugs = {item["slug"] for item in self.manifest["features"]}
        feature_slugs.update(self.manifest["legacy_brand_links_to_remove"])
        feature_slugs.update(
            slug
            for slugs in self.manifest.get("series_links_to_remove", {}).values()
            for slug in slugs
        )
        feature_slugs.update(self.manifest.get("product_links_to_remove", []))
        feature_rows = list(
            (
                await self.session.execute(
                    select(Feature)
                    .where(Feature.slug.in_(feature_slugs))
                    .options(selectinload(Feature.rules), selectinload(Feature.category))
                )
            ).scalars().all()
        )
        self.features = {item.slug: item for item in feature_rows}
        self.initial_feature_slugs = set(self.features)

    async def _upsert_features(self) -> None:
        categories = {
            item.slug: item
            for item in (
                await self.session.execute(select(FeatureCategory))
            ).scalars().all()
        }
        for spec in self.manifest["features"]:
            category = categories.get(spec["category_slug"])
            if category is None:
                raise TclFeatureCanaryError(
                    f"Feature category {spec['category_slug']!r} not found"
                )
            feature = self.features.get(spec["slug"])
            if feature is None and spec.get("reuse_required"):
                raise TclFeatureCanaryError(
                    f"Required legacy Feature {spec['slug']!r} not found"
                )
            if feature is None:
                feature = Feature(slug=spec["slug"], name=spec["name"], category_id=int(category.id))
                self.session.add(feature)
                await self.session.flush()
                self.features[feature.slug] = feature
                self._action("create_feature", feature=feature.slug)
            set_committed_value(feature, "category", category)

            is_active = bool(spec.get("is_active", True))
            desired = {
                "name": spec["name"],
                "short_description": spec.get("short_description"),
                "full_description": spec.get("full_description"),
                "category_id": int(category.id),
                "scope_type": spec["scope_type"],
                "brand_id": int(self.brand.id) if spec.get("brand_slug") else None,
                "aliases": self._strings(spec.get("aliases", [])),
                "source_url": self.manifest["catalog"]["source_url"],
                "source_notes": spec.get("source_notes"),
                "legal_notes": spec.get("legal_notes"),
                "sort_order": int(spec.get("sort_order", 0)),
                "is_active": is_active,
                "archived_at": None if is_active else feature.archived_at or datetime.now(),
            }
            changes = {}
            for field, value in desired.items():
                if getattr(feature, field) != value:
                    changes[field] = {"from": getattr(feature, field), "to": value}
                    setattr(feature, field, value)
            if changes:
                feature.updated_at = datetime.now()
                self.session.add(feature)
                self._action("update_feature", feature=feature.slug, changes=changes)
            await self._sync_rules(feature, spec.get("rules", []))

    async def _sync_rules(self, feature: Feature, desired: list[dict[str, Any]]) -> None:
        current_models = list(
            (
                await self.session.execute(
                    select(FeatureRule).where(FeatureRule.feature_id == feature.id)
                )
            ).scalars().all()
        )
        current = sorted(
            (
                {
                    "spec_key": rule.spec_key,
                    "operator": rule.operator,
                    "target_value": rule.target_value,
                    "is_active": bool(rule.is_active),
                    "sort_order": int(rule.sort_order),
                }
                for rule in current_models
            ),
            key=lambda item: (item["sort_order"], item["spec_key"], item["operator"]),
        )
        normalized = []
        for index, rule in enumerate(desired):
            normalized.append(
                {
                    "spec_key": rule["spec_key"],
                    "operator": rule["operator"],
                    "target_value": rule.get("target_value"),
                    "is_active": bool(rule.get("is_active", True)),
                    "sort_order": int(rule.get("sort_order", index * 10)),
                }
            )
        normalized.sort(key=lambda item: (item["sort_order"], item["spec_key"], item["operator"]))
        if current == normalized:
            set_committed_value(feature, "rules", current_models)
            return
        await self.session.execute(delete(FeatureRule).where(FeatureRule.feature_id == feature.id))
        for rule in normalized:
            self.session.add(FeatureRule(feature_id=int(feature.id), **rule))
        await self.session.flush()
        current_models = list(
            (
                await self.session.execute(
                    select(FeatureRule).where(FeatureRule.feature_id == feature.id)
                )
            ).scalars().all()
        )
        set_committed_value(feature, "rules", current_models)
        self._action("replace_rules", feature=feature.slug, rules=normalized)

    async def _remove_legacy_brand_links(self) -> None:
        slugs = self.manifest["legacy_brand_links_to_remove"]
        ids = [int(self.features[slug].id) for slug in slugs]
        links = list(
            (
                await self.session.execute(
                    select(FeatureBrandLink).where(
                        FeatureBrandLink.brand_id == self.brand.id,
                        FeatureBrandLink.feature_id.in_(ids),
                    )
                )
            ).scalars().all()
        )
        for link in links:
            feature = next(item for item in self.features.values() if item.id == link.feature_id)
            await self.session.delete(link)
            self._action("remove_legacy_brand_link", feature=feature.slug)

    async def _remove_stale_series_links(self) -> None:
        for series_slug, feature_slugs in self.manifest.get("series_links_to_remove", {}).items():
            series = self.series[series_slug]
            feature_ids = [int(self.features[slug].id) for slug in feature_slugs]
            links = list(
                (
                    await self.session.execute(
                        select(FeatureSeriesLink).where(
                            FeatureSeriesLink.series_id == series.id,
                            FeatureSeriesLink.feature_id.in_(feature_ids),
                        )
                    )
                ).scalars().all()
            )
            for link in links:
                feature = next(item for item in self.features.values() if item.id == link.feature_id)
                await self.session.delete(link)
                self._action(
                    "remove_stale_series_link",
                    series=series_slug,
                    feature=feature.slug,
                )

    async def _remove_stale_product_links(self) -> None:
        feature_slugs = self.manifest.get("product_links_to_remove", [])
        if not feature_slugs:
            return
        feature_ids = [int(self.features[slug].id) for slug in feature_slugs]
        product_ids = [int(product.id) for product in self.products]
        links = list(
            (
                await self.session.execute(
                    select(FeatureProductLink).where(
                        FeatureProductLink.product_id.in_(product_ids),
                        FeatureProductLink.feature_id.in_(feature_ids),
                    )
                )
            ).scalars().all()
        )
        for link in links:
            feature = next(item for item in self.features.values() if item.id == link.feature_id)
            await self.session.delete(link)
            self._action(
                "remove_stale_product_link",
                product_id=int(link.product_id),
                feature=feature.slug,
            )

    async def _normalize_product_states(self) -> None:
        matched_ids: set[int] = set()
        for state in self.manifest["product_states"]:
            matches = [
                product
                for product in self.products
                if product.series.slug == state["series_slug"]
                and state["model_marker"].casefold() in product.title.casefold()
            ]
            if not matches:
                raise TclFeatureCanaryError(f"Product selector matched nothing: {state}")
            for product in matches:
                if int(product.id) in matched_ids:
                    raise TclFeatureCanaryError(f"Product #{product.id} matched multiple state rules")
                matched_ids.add(int(product.id))
                before = dict(product.specs or {})
                after = self._normalized_specs(before, state)
                if before != after:
                    product.specs = after
                    self.session.add(product)
                    changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
                    self._action("update_product_specs", product_id=int(product.id), slug=product.slug, keys=changed)
                    self.source_reconciliations.append(
                        {
                            "product_id": int(product.id),
                            "product": product.title,
                            "catalog_source": state,
                            "changed_keys": changed,
                            "before": {key: self._report_spec_value(key, before.get(key)) for key in changed},
                            "after": {key: self._report_spec_value(key, after.get(key)) for key in changed},
                        }
                    )

    @staticmethod
    def _normalized_specs(specs: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        probe = dict(specs)
        if "wifi_state" in state:
            wifi_state = state["wifi_state"]
            probe["wifi_state"] = wifi_state
            probe["wifi_ready"] = wifi_state in {"builtin", "ready"}
            probe["wifi_builtin"] = wifi_state == "builtin"
        if "min_heat" in state:
            probe["temp_range_heat"] = f"от {state['min_heat']} до +30 °C"
        normalized = normalize_specs(probe, keep_units=True)
        updated = dict(specs)
        for key in WIFI_SPEC_KEYS:
            if key in normalized:
                updated[key] = normalized[key]
        if "min_heat" in state:
            updated["temp_range_heat"] = normalized["temp_range_heat"]
            updated["__filter_min_heat"] = normalized["__filter_min_heat"]
        typed = dict(updated.get("__typed_specs") or {})
        normalized_typed = normalized.get("__typed_specs") or {}
        typed_keys = ["wifi_state", "wifi_ready", "wifi_builtin"]
        if "min_heat" in state:
            typed_keys.append("temp_range_heat")
        for key in typed_keys:
            if key in normalized_typed:
                typed[key] = normalized_typed[key]
        if typed:
            updated["__typed_specs"] = typed
        return updated

    async def _upsert_series_links(self) -> None:
        for series_slug, feature_slugs in self.manifest["series_links"].items():
            series = self.series[series_slug]
            for index, feature_slug in enumerate(feature_slugs):
                feature = self.features[feature_slug]
                link = (
                    await self.session.execute(
                        select(FeatureSeriesLink).where(
                            FeatureSeriesLink.series_id == series.id,
                            FeatureSeriesLink.feature_id == feature.id,
                        )
                    )
                ).scalar_one_or_none()
                if link is None:
                    link = FeatureSeriesLink(series_id=int(series.id), feature_id=int(feature.id))
                    self.session.add(link)
                desired_order = int(feature.sort_order or 0) + index
                changed = (
                    link.id is None
                    or link.source != "manual"
                    or not link.is_enabled
                    or link.sort_order != desired_order
                )
                link.source = "manual"
                link.is_enabled = True
                link.sort_order = desired_order
                link.updated_at = datetime.now()
                if changed:
                    self._action("upsert_series_link", series=series_slug, feature=feature_slug)

    async def _upsert_derived_links(self) -> None:
        for apply in self.manifest["derived_apply"]:
            feature = self.features[apply["feature_slug"]]
            rules = list(feature.rules or [])
            for product in self.products:
                if product.series.slug not in apply["series_slugs"]:
                    continue
                if apply.get("wifi_state") and product.specs.get("wifi_state") != apply["wifi_state"]:
                    continue
                if not matches_all_rules(product.specs or {}, rules):
                    continue
                link = (
                    await self.session.execute(
                        select(FeatureProductLink).where(
                            FeatureProductLink.product_id == product.id,
                            FeatureProductLink.feature_id == feature.id,
                        )
                    )
                ).scalar_one_or_none()
                if link is not None and link.source == "manual":
                    continue
                if link is None:
                    link = FeatureProductLink(product_id=int(product.id), feature_id=int(feature.id))
                    self.session.add(link)
                changed = link.id is None or link.source != "derived" or not link.is_enabled
                link.source = "derived"
                link.is_enabled = True
                link.sort_order = int(feature.sort_order or 0)
                link.updated_at = datetime.now()
                if changed:
                    self._action("upsert_derived_link", product_id=int(product.id), feature=feature.slug)

    async def _build_report(self, *, execute: bool) -> dict[str, Any]:
        resolved = await FeatureResolverService.resolve_for_products(
            self.session, self.products, include_suggestions=True
        )
        managed_slugs = {item["slug"] for item in self.manifest["features"]}
        expected = self._expected_by_product()
        matrix = []
        missing = []
        unexpected = []
        duplicates = []
        unexpected_inheritance = []

        for product in self.products:
            actual_items = [item for item in resolved[int(product.id)]["effective"] if item.slug in managed_slugs]
            counts = Counter(item.id for item in actual_items)
            duplicates.extend(
                {"product_id": int(product.id), "feature_id": feature_id, "count": count}
                for feature_id, count in counts.items()
                if count > 1
            )
            actual = {item.slug: item for item in actual_items}
            expected_slugs = expected[int(product.id)]
            for slug in sorted(expected_slugs | set(actual)):
                item = actual.get(slug)
                should_exist = slug in expected_slugs
                matrix.append(
                    {
                        "brand": self.brand.slug,
                        "series": product.series.slug,
                        "product": product.slug,
                        "feature": slug,
                        "source": item.source if item else None,
                        "is_enabled": item is not None,
                        "is_overridden": item.is_overridden if item else False,
                        "applied_rule": item.applied_rule if item else None,
                        "expected": should_exist,
                        "actual": item is not None,
                    }
                )
                if should_exist and item is None:
                    missing.append({"product_id": int(product.id), "feature": slug})
                if not should_exist and item is not None:
                    unexpected.append({"product_id": int(product.id), "feature": slug})
                if item is not None and item.source in {"brand", "series"}:
                    allowed_series = {
                        series_slug
                        for series_slug, slugs in self.manifest["series_links"].items()
                        if slug in slugs
                    }
                    if product.series.slug not in allowed_series:
                        unexpected_inheritance.append(
                            {"product_id": int(product.id), "feature": slug, "source": item.source}
                        )

        return {
            "mode": "execute" if execute else "dry-run",
            "catalog": self.manifest["catalog"],
            "brand": {"id": int(self.brand.id), "slug": self.brand.slug},
            "series": [
                {"id": int(item.id), "slug": item.slug, "title": item.title}
                for item in self.series.values()
            ],
            "actions": self.actions,
            "feature_plan": [
                {
                    "slug": item["slug"],
                    "result": "reuse" if item["slug"] in self.initial_feature_slugs else "create",
                }
                for item in self.manifest["features"]
            ],
            "rule_audit": self._rule_audit(),
            "source_reconciliations": self.source_reconciliations,
            "ambiguities": [],
            "skipped_products": [
                {"id": int(item.id), "slug": item.slug, "reason": "outside_pilot_allowlist"}
                for item in self.skipped_products
            ],
            "result_matrix": matrix,
            "cross_brand_violations": await self._cross_brand_violations(),
            "duplicate_feature_ids": duplicates,
            "unexpected_inheritance": unexpected_inheritance,
            "missing_expected_features": missing,
            "unexpected_features": unexpected,
            "unresolved_source_conflicts": [],
        }

    def _expected_by_product(self) -> dict[int, set[str]]:
        expected: dict[int, set[str]] = {}
        for product in self.products:
            slugs = set(self.manifest["series_links"].get(product.series.slug, []))
            for apply in self.manifest["derived_apply"]:
                if product.series.slug not in apply["series_slugs"]:
                    continue
                if apply.get("wifi_state") and product.specs.get("wifi_state") != apply["wifi_state"]:
                    continue
                feature = self.features[apply["feature_slug"]]
                if matches_all_rules(product.specs or {}, list(feature.rules or [])):
                    slugs.add(feature.slug)
            expected[int(product.id)] = slugs
        return expected

    def _rule_audit(self) -> list[dict[str, Any]]:
        rows = []
        for feature_spec in self.manifest["features"]:
            feature = self.features[feature_spec["slug"]]
            rules = list(feature.rules or [])
            if not rules:
                continue
            values = Counter()
            matched = []
            unmatched = []
            for product in self.products:
                for rule in rules:
                    value = get_spec_value(product.specs or {}, rule.spec_key)
                    values[repr(value)] += 1
                target = matched if matches_all_rules(product.specs or {}, rules) else unmatched
                if len(target) < 5:
                    target.append({"id": int(product.id), "model": product.title})
            rows.append(
                {
                    "feature": feature.slug,
                    "rules": [
                        {
                            "spec_key": rule.spec_key,
                            "operator": rule.operator,
                            "target_value": rule.target_value,
                        }
                        for rule in rules
                    ],
                    "real_values": dict(values),
                    "match_count": sum(
                        matches_all_rules(product.specs or {}, rules) for product in self.products
                    ),
                    "matching_examples": matched,
                    "nonmatching_examples": unmatched,
                }
            )
        return rows

    async def _cross_brand_violations(self) -> list[dict[str, Any]]:
        feature_ids = [int(item.id) for item in self.features.values()]
        violations = []
        series_links = list(
            (
                await self.session.execute(
                    select(FeatureSeriesLink, ProductSeries)
                    .join(ProductSeries, ProductSeries.id == FeatureSeriesLink.series_id)
                    .where(FeatureSeriesLink.feature_id.in_(feature_ids))
                )
            ).all()
        )
        product_links = list(
            (
                await self.session.execute(
                    select(FeatureProductLink, Product)
                    .join(Product, Product.id == FeatureProductLink.product_id)
                    .where(FeatureProductLink.feature_id.in_(feature_ids))
                )
            ).all()
        )
        by_id = {int(item.id): item for item in self.features.values()}
        for link, target in [*series_links, *product_links]:
            feature = by_id[int(link.feature_id)]
            if feature.brand_id is not None and target.brand_id != feature.brand_id:
                violations.append(
                    {"feature": feature.slug, "target_id": int(target.id), "target_brand_id": target.brand_id}
                )
        return violations

    def _action(self, action: str, **payload: Any) -> None:
        self.actions.append({"action": action, **payload})

    @staticmethod
    def _report_spec_value(key: str, value: Any) -> Any:
        if key != "__typed_specs" or not isinstance(value, dict):
            return value
        return {
            typed_key: value.get(typed_key)
            for typed_key in ("wifi_state", "wifi_ready", "wifi_builtin", "temp_range_heat")
            if typed_key in value
        }

    @staticmethod
    def _strings(values: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in values if item and item.strip()))
