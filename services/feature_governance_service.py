from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


REQUIRED_FEATURE_FIELDS = (
    "slug",
    "name",
    "category_slug",
    "short_description",
    "full_description",
    "scope",
    "assignment_mode",
    "aliases",
    "possible_derived_rules",
    "notes",
)
ALLOWED_SCOPES = {"universal", "brand"}
ALLOWED_ASSIGNMENT_MODES = {"manual", "derived", "mixed"}


def load_feature_governance_registry(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class FeatureGovernanceService:
    """Pure validation used by CI and catalog-specific migration audits."""

    @classmethod
    def validate_registry(cls, registry: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        categories = registry.get("categories") or []
        features = registry.get("features") or []
        category_slugs = [item.get("slug") for item in categories]
        feature_slugs = [item.get("slug") for item in features]

        cls._duplicates(category_slugs, "duplicate_category_slug", findings)
        cls._duplicates(feature_slugs, "duplicate_feature_slug", findings)
        known_categories = {slug for slug in category_slugs if slug}
        labels: dict[str, set[str]] = defaultdict(set)

        for feature in features:
            slug = feature.get("slug") or "<missing>"
            for field in REQUIRED_FEATURE_FIELDS:
                value = feature.get(field)
                if value is None or value == "":
                    cls._add(
                        findings,
                        "error",
                        "missing_required_field",
                        slug,
                        f"Не заполнено обязательное поле {field}.",
                    )
            category_slug = feature.get("category_slug")
            if category_slug not in known_categories:
                cls._add(
                    findings,
                    "error",
                    "unknown_category",
                    slug,
                    f"Неизвестная категория {category_slug!r}.",
                )
            if feature.get("scope") not in ALLOWED_SCOPES:
                cls._add(
                    findings,
                    "error",
                    "invalid_scope",
                    slug,
                    f"Недопустимый scope {feature.get('scope')!r}.",
                )
            if feature.get("assignment_mode") not in ALLOWED_ASSIGNMENT_MODES:
                cls._add(
                    findings,
                    "error",
                    "invalid_assignment_mode",
                    slug,
                    f"Недопустимый assignment_mode {feature.get('assignment_mode')!r}.",
                )
            for label in [feature.get("name"), *(feature.get("aliases") or [])]:
                normalized = cls.normalize_label(label)
                if normalized:
                    labels[normalized].add(slug)

        for label, slugs in sorted(labels.items()):
            if len(slugs) > 1:
                cls._add(
                    findings,
                    "error",
                    "alias_collision",
                    None,
                    f"Название или alias {label!r} ведёт к нескольким Feature: {sorted(slugs)}.",
                )
        return findings

    @classmethod
    def audit_manifest(
        cls,
        registry: dict[str, Any],
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        findings = cls.validate_registry(registry)
        canonical_by_label = cls._canonical_by_label(registry)
        categories = {item["slug"] for item in registry.get("categories", [])}
        canonical_matches: dict[str, list[str]] = defaultdict(list)
        active_features = [item for item in manifest.get("features", []) if item.get("is_active", True)]

        for feature in active_features:
            slug = feature.get("slug") or "<missing>"
            category_slug = feature.get("category_slug")
            if not category_slug:
                cls._add(findings, "error", "feature_without_category", slug, "Feature не имеет категории.")
            elif category_slug not in categories:
                cls._add(
                    findings,
                    "error",
                    "manifest_unknown_category",
                    slug,
                    f"Категория {category_slug!r} отсутствует в taxonomy.",
                )

            canonical = cls._match_canonical(feature, canonical_by_label)
            if canonical is not None:
                canonical_matches[canonical["slug"]].append(slug)
                if category_slug != canonical["category_slug"]:
                    cls._add(
                        findings,
                        "error",
                        "category_mismatch",
                        slug,
                        "Категория не совпадает с канонической.",
                        expected=canonical["category_slug"],
                        actual=category_slug,
                    )
                if canonical["scope"] == "universal" and feature.get("brand_slug"):
                    cls._add(
                        findings,
                        "error",
                        "universal_feature_brand_restricted",
                        slug,
                        "Универсальная Feature ошибочно ограничена брендом.",
                        expected=None,
                        actual=feature.get("brand_slug"),
                    )

            expected_category = cls._category_hint(feature)
            if expected_category and category_slug != expected_category:
                cls._add(
                    findings,
                    "warning",
                    "semantic_category_mismatch",
                    slug,
                    "Название похоже на другую покупательскую категорию.",
                    expected=expected_category,
                    actual=category_slug,
                )

            if (
                feature.get("scope_type") in {"universal", "derived"}
                and not feature.get("brand_slug")
                and cls._looks_brand_specific(feature, manifest)
            ):
                cls._add(
                    findings,
                    "warning",
                    "brand_feature_marked_universal",
                    slug,
                    "Название содержит брендовый маркер, но Feature объявлена универсальной.",
                )

        for canonical_slug, slugs in sorted(canonical_matches.items()):
            if len(slugs) > 1:
                cls._add(
                    findings,
                    "error",
                    "suspected_duplicate",
                    canonical_slug,
                    f"Несколько активных Feature выражают один канонический смысл: {sorted(slugs)}.",
                )

        cls._audit_assignment_width(findings, manifest, active_features)
        findings.sort(key=lambda item: (item["severity"] != "error", item["code"], item.get("feature") or ""))
        return {
            "registry": registry.get("library"),
            "manifest": manifest.get("catalog", {}).get("name"),
            "summary": {
                "categories": len(registry.get("categories", [])),
                "canonical_features": len(registry.get("features", [])),
                "manifest_active_features": len(active_features),
                "errors": sum(item["severity"] == "error" for item in findings),
                "warnings": sum(item["severity"] == "warning" for item in findings),
            },
            "findings": findings,
        }

    @staticmethod
    def normalize_label(value: Any) -> str:
        if value is None:
            return ""
        normalized = str(value).casefold().replace("ё", "е")
        normalized = re.sub(r"[^a-zа-я0-9]+", " ", normalized)
        return " ".join(normalized.split())

    @classmethod
    def _canonical_by_label(cls, registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for feature in registry.get("features", []):
            for value in [feature.get("slug"), feature.get("name"), *(feature.get("aliases") or [])]:
                label = cls.normalize_label(value)
                if label:
                    result[label] = feature
        return result

    @classmethod
    def _match_canonical(
        cls,
        feature: dict[str, Any],
        canonical_by_label: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        for value in [feature.get("slug"), feature.get("name"), *(feature.get("aliases") or [])]:
            canonical = canonical_by_label.get(cls.normalize_label(value))
            if canonical is not None:
                return canonical
        return None

    @classmethod
    def _category_hint(cls, feature: dict[str, Any]) -> str | None:
        text = " ".join(
            cls.normalize_label(value)
            for value in [feature.get("slug"), feature.get("name"), *(feature.get("aliases") or [])]
        )
        hints = (
            ("control", ("wifi", "wi fi", "голос", "voice", "таймер", "timer")),
            ("heating", ("обогрев", "heating", "heat pump", "nordic", " 8c", " 8 c")),
            ("comfort", ("шум", "noise", "quiet", "sleep", "gentle breeze")),
            ("performance", ("мощност", "capacity", "turbo", "powerful")),
        )
        for category, markers in hints:
            if any(marker in text for marker in markers):
                return category
        return None

    @classmethod
    def _looks_brand_specific(cls, feature: dict[str, Any], manifest: dict[str, Any]) -> bool:
        brand_slug = cls.normalize_label(manifest.get("catalog", {}).get("brand_slug"))
        if not brand_slug:
            return False
        return brand_slug in cls.normalize_label(feature.get("slug")) or brand_slug in cls.normalize_label(
            feature.get("name")
        )
    @classmethod
    def _audit_assignment_width(
        cls,
        findings: list[dict[str, Any]],
        manifest: dict[str, Any],
        active_features: list[dict[str, Any]],
    ) -> None:
        series_slugs = set((manifest.get("series_allowlist") or {}).keys())
        if len(series_slugs) < 2:
            return
        assignments: dict[str, set[str]] = defaultdict(set)
        for series_slug, feature_slugs in (manifest.get("series_links") or {}).items():
            for feature_slug in feature_slugs:
                assignments[feature_slug].add(series_slug)
        by_slug = {item.get("slug"): item for item in active_features}
        for feature_slug, assigned_series in assignments.items():
            feature = by_slug.get(feature_slug)
            if not feature or feature.get("scope_type") != "brand":
                continue
            if assigned_series == series_slugs:
                cls._add(
                    findings,
                    "warning",
                    "possibly_too_broad_assignment",
                    feature_slug,
                    "Брендовая Feature назначена всем сериям пилота; применимость стоит подтвердить.",
                )

    @staticmethod
    def _duplicates(values: list[Any], code: str, findings: list[dict[str, Any]]) -> None:
        seen: set[Any] = set()
        for value in values:
            if value in seen:
                FeatureGovernanceService._add(
                    findings,
                    "error",
                    code,
                    str(value) if value is not None else None,
                    f"Повторяющееся значение {value!r}.",
                )
            seen.add(value)

    @staticmethod
    def _add(
        findings: list[dict[str, Any]],
        severity: str,
        code: str,
        feature: str | None,
        message: str,
        **details: Any,
    ) -> None:
        findings.append(
            {
                "severity": severity,
                "code": code,
                "feature": feature,
                "message": message,
                **details,
            }
        )
