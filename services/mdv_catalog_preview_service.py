from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from parsers.mdv_catalog import MDV_EXPORT_URLS, MDV_PROMOTED_PROP_KEYS, MdvCatalogParser
from services.mdv_legacy_replace_service import MdvLegacyReplaceService
from services.product_import_match_service import find_existing_product_for_import
from services.spec_normalizer import normalize_specs


class MdvCatalogPreviewService:
    @staticmethod
    def normalize_catalogs(catalogs: list[str] | None) -> list[str]:
        if not catalogs:
            return list(MDV_EXPORT_URLS.keys())
        result = []
        for catalog in catalogs:
            value = str(catalog or "").strip()
            if value in MDV_EXPORT_URLS and value not in result:
                result.append(value)
        return result or list(MDV_EXPORT_URLS.keys())

    @staticmethod
    async def build_preview(
        session: AsyncSession,
        *,
        catalogs: list[str] | None = None,
        sample_limit: int = 30,
        replace_legacy_catalogs: list[str] | None = None,
    ) -> dict[str, Any]:
        selected_catalogs = MdvCatalogPreviewService.normalize_catalogs(catalogs)
        selected_replace_catalogs = MdvLegacyReplaceService.normalize_catalogs(
            replace_legacy_catalogs
        )
        parser = MdvCatalogParser()
        records = await parser.collect_records(catalogs=selected_catalogs, include_manuals=False)

        by_catalog: Counter[str] = Counter()
        actions: Counter[str] = Counter()
        unmatched_source_urls = 0
        raw_key_counter: Counter[str] = Counter()
        unpromoted_key_counter: Counter[str] = Counter()
        samples: list[dict[str, Any]] = []

        for record in records:
            by_catalog[record.catalog] += 1
            payload = await parser.build_import_payload(record, include_manuals=False)
            normalized_specs = normalize_specs(
                payload.get("specs") or {},
                title=payload.get("title") or "",
                strict_wifi_from_tags=False,
            )
            existing = await find_existing_product_for_import(
                session,
                source_url=payload.get("source_url") or record.source_url,
                normalized_specs=normalized_specs,
                update_existing=True,
            )
            action = "update" if existing else "create"
            actions[action] += 1
            if str(record.source_url).startswith("mdv-catalog://"):
                unmatched_source_urls += 1

            raw_specs = (payload.get("specs") or {}).get("__mdv_raw_specs") or {}
            if isinstance(raw_specs, dict):
                for key in raw_specs:
                    raw_key_counter[key] += 1
                    if key not in MDV_PROMOTED_PROP_KEYS:
                        unpromoted_key_counter[key] += 1

            if len(samples) < sample_limit:
                samples.append(
                    {
                        "catalog": record.catalog,
                        "action": action,
                        "title": payload.get("title") or "",
                        "source_url": payload.get("source_url") or record.source_url,
                        "existing_product_id": getattr(existing, "id", None),
                        "price_rub": payload.get("price") or 0,
                        "series": normalized_specs.get("series") or "",
                        "type": normalized_specs.get("type") or "",
                        "model_indoor": normalized_specs.get("model_indoor") or "",
                        "model_outdoor": normalized_specs.get("model_outdoor") or "",
                    }
                )

        legacy_replace = await MdvLegacyReplaceService.preview(
            session,
            catalogs=selected_replace_catalogs,
        )

        return {
            "catalogs": selected_catalogs,
            "total": len(records),
            "by_catalog": dict(by_catalog),
            "actions": dict(actions),
            "unmatched_source_urls": unmatched_source_urls,
            "raw_spec_key_count": len(raw_key_counter),
            "top_raw_spec_keys": [
                {"key": key, "count": count}
                for key, count in raw_key_counter.most_common(20)
            ],
            "top_unpromoted_spec_keys": [
                {"key": key, "count": count}
                for key, count in unpromoted_key_counter.most_common(20)
            ],
            "samples": samples,
            "legacy_replace": legacy_replace,
            "source_urls": {catalog: MDV_EXPORT_URLS[catalog] for catalog in selected_catalogs},
            "next_step": "После проверки dry-run можно запускать импорт с update_existing=true; цены RUB затем связываются с прайсом Биоконда.",
        }
