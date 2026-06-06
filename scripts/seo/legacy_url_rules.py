"""Exact SEO cleanup URL rules for Yandex legacy storefront URLs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegacyRedirectRule:
    source: str
    target: str
    note: str = ""


@dataclass(frozen=True)
class LegacyGoneRule:
    source: str
    classification: str
    note: str = ""


DEAD_PRODUCT_GONE_RULES: tuple[LegacyGoneRule, ...] = (
    LegacyGoneRule("/split/mhi/mhi-zmx/mhi-25zmx", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/index.php?route=product/product&path=59_65_75&product_id=69", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/split?product_id=294", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/split/energolux/geneva/sas18g1-ai", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/index.php?_route_=split/daikin/ftxb20c", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/index.php?_route_=split/mhi/mhi-zr-s/mhi71zr-s", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/split/mdv/aurora-12", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/index.php?_route_=split/electrolux/elx-fusion/eacs-12hf", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/index.php?_route_=split/mhi/ZSPR-S/src25zspr-s", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/split/daikin-emura-silver-35", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/index.php?_route_=split/mhi/mhi-60zmx", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/split/cooperhunter/chs18ftxe", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/index.php?_route_=daikin-emura-silver-25&manufacturer_id=12", "old_missing_product_or_legacy_dead_url"),
    LegacyGoneRule("/index.php?_route_=split/cooperhunter/chs18ftxe", "old_missing_product_or_legacy_dead_url"),
)

# Verified on 2026-06-06 against https://api.mvn.by/api/v1/content/brands:
# there is no published hisense brand route, so the old manufacturer URL should
# not be redirected to /brands/hisense/.
BRAND_GONE_RULES: tuple[LegacyGoneRule, ...] = (
    LegacyGoneRule(
        "/index.php?_route_=m-hisence",
        "legacy_route_duplicate",
        "No verified /brands/<slug>/ canonical exists for HiSence/Hisense.",
    ),
    LegacyGoneRule(
        "/m-hisence",
        "brand_or_manufacturer_landing_page",
        "No verified /brands/<slug>/ canonical exists for HiSence/Hisense.",
    ),
)

LEGACY_REDIRECT_RULES: tuple[LegacyRedirectRule, ...] = (
    LegacyRedirectRule(
        "/index.php?_route_=split/haier/haier-home/",
        "/split/haier/haier-home/",
        "Legacy _route_ duplicate of the canonical Haier Home series page.",
    ),
    LegacyRedirectRule(
        "/index.php?_route_=split/haier/lightera/",
        "/split/haier/lightera/",
        "Legacy _route_ duplicate of the canonical Haier Lightera series page.",
    ),
)

GONE_RULES: tuple[LegacyGoneRule, ...] = DEAD_PRODUCT_GONE_RULES + BRAND_GONE_RULES
GONE_URLS = {rule.source: rule for rule in GONE_RULES}
REDIRECT_URLS = {rule.source: rule for rule in LEGACY_REDIRECT_RULES}
