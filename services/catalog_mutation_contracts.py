"""Explicit catalog mutation producers that must invalidate storefront caches."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class GlobalCatalogMutationContract:
    producer: str
    reason: str


@dataclass(slots=True)
class CatalogMutationBatch:
    """Accumulate nested writes for one caller-owned invalidation boundary."""

    changed: bool = False
    product_ids: set[int] = field(default_factory=set)
    slugs: set[str] = field(default_factory=set)
    brand_slugs: set[str] = field(default_factory=set)

    def record(
        self,
        *,
        changed: bool,
        product_ids: Iterable[int | None] = (),
        slugs: Iterable[str | None] = (),
        brand_slugs: Iterable[str | None] = (),
    ) -> None:
        if not changed:
            return
        self.changed = True
        self.product_ids.update(int(value) for value in product_ids if value is not None)
        self.slugs.update(str(value) for value in slugs if value)
        self.brand_slugs.update(str(value) for value in brand_slugs if value)


def _contract(producer: str, reason: str) -> GlobalCatalogMutationContract:
    return GlobalCatalogMutationContract(producer=producer, reason=reason)


IMPORTER_GLOBAL_MUTATION_PRODUCERS = frozenset(
    {
        "importer.import_product",
    }
)

MANAGER_MEDIA_GLOBAL_MUTATION_PRODUCERS = frozenset(
    {
        "manager_media.set_main_image",
        "manager_media.delete_gallery_image",
        "manager_media.crop_gallery_image",
        "manager_media.remove_background_gallery_image",
        "manager_media.reuse_image_link",
        "manager_media.save_image_from_bytes",
        "manager_media.save_images_from_bytes",
        "manager_media.bulk_add_gallery_images",
        "manager_media.bulk_delete_common_gallery_images",
        "manager_media.apply_gallery_to_series",
        "manager_media.bulk_upload_local_images",
    }
)

FEATURE_DELETE_GLOBAL_MUTATION_PRODUCERS = frozenset(
    {
        "feature_assignment.delete_product_assignment",
        "feature_assignment.delete_target_link.brand",
        "feature_assignment.delete_target_link.series",
    }
)

PRODUCT_IMAGE_VARIANT_GLOBAL_MUTATION_PRODUCERS = frozenset(
    {
        "product_image_variant.reprocess_variant",
        "product_image_variant.process_missing_variants",
        "yandex_feed_image.backfill",
    }
)

MANAGER_BRAND_GLOBAL_MUTATION_PRODUCERS = frozenset(
    {
        "manager_brand.create_brand",
        "manager_brand.update_brand",
        "manager_brand.delete_brand",
        "manager_brand.create_brand_feature",
        "manager_brand.update_brand_feature",
        "manager_brand.delete_brand_feature",
        "manager_brand.list_brand_series",
        "manager_brand.create_brand_series",
        "manager_brand.update_brand_series",
        "manager_brand.apply_series_gallery_to_products",
        "manager_brand.delete_brand_series",
    }
)

PUBLIC_CATALOG_MUTATION_PRODUCERS = frozenset(
    {
        *IMPORTER_GLOBAL_MUTATION_PRODUCERS,
        *MANAGER_MEDIA_GLOBAL_MUTATION_PRODUCERS,
        *FEATURE_DELETE_GLOBAL_MUTATION_PRODUCERS,
        *PRODUCT_IMAGE_VARIANT_GLOBAL_MUTATION_PRODUCERS,
        *MANAGER_BRAND_GLOBAL_MUTATION_PRODUCERS,
    }
)

# This mapping is the single reviewed facade inventory used by the scoped route
# scanner. An empty producer set marks an explicitly non-mutating route.
PUBLIC_CATALOG_MUTATION_ENTRYPOINTS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "ImporterService.import_product": frozenset({"importer.import_product"}),
        "ManagerMediaService.set_main_image": frozenset(
            {"manager_media.set_main_image"}
        ),
        "ManagerMediaService.delete_gallery_image": frozenset(
            {"manager_media.delete_gallery_image"}
        ),
        "ManagerMediaService.crop_gallery_image": frozenset(
            {"manager_media.crop_gallery_image"}
        ),
        "ManagerMediaService.remove_background_gallery_image": frozenset(
            {"manager_media.remove_background_gallery_image"}
        ),
        "ManagerMediaService.reuse_image_link": frozenset(
            {"manager_media.reuse_image_link"}
        ),
        "ManagerMediaService.process_and_save_image": frozenset(
            {"manager_media.save_image_from_bytes"}
        ),
        "ManagerMediaService.save_image_from_bytes": frozenset(
            {"manager_media.save_image_from_bytes"}
        ),
        "ManagerMediaService.save_images_from_bytes": frozenset(
            {"manager_media.save_images_from_bytes"}
        ),
        "ManagerMediaService.bulk_add_gallery_images": frozenset(
            {"manager_media.bulk_add_gallery_images"}
        ),
        "ManagerMediaService.bulk_delete_common_gallery_images": frozenset(
            {"manager_media.bulk_delete_common_gallery_images"}
        ),
        "ManagerMediaService.apply_gallery_to_series": frozenset(
            {"manager_media.apply_gallery_to_series"}
        ),
        "ManagerMediaService.bulk_upload_local_images": frozenset(
            {"manager_media.bulk_upload_local_images"}
        ),
        "ManagerMediaService.cleanup_media": frozenset(),
        "ManagerMediaOrchestratorService.upload_image_from_url": frozenset(
            {"manager_media.save_image_from_bytes"}
        ),
        "ManagerMediaOrchestratorService.upload_local_images": frozenset(
            {"manager_media.save_images_from_bytes"}
        ),
        "ManagerMediaOrchestratorService.link_search_result": frozenset(
            {"manager_media.save_image_from_bytes"}
        ),
        "ManagerMediaOrchestratorService.bulk_upload_local_images": frozenset(
            {"manager_media.bulk_upload_local_images"}
        ),
        "FeatureAssignmentService.delete_product_assignment": frozenset(
            {"feature_assignment.delete_product_assignment"}
        ),
        "FeatureAssignmentService.delete_target_link": frozenset(
            {
                "feature_assignment.delete_target_link.brand",
                "feature_assignment.delete_target_link.series",
            }
        ),
        "ProductImageVariantService.reprocess_variant": frozenset(
            {"product_image_variant.reprocess_variant"}
        ),
        "ProductImageVariantService.process_missing_variants": frozenset(
            {"product_image_variant.process_missing_variants"}
        ),
        "YandexFeedImageService.backfill": frozenset(
            {"yandex_feed_image.backfill"}
        ),
        "ManagerBrandService.list_brands": frozenset(),
        "ManagerBrandService.list_brand_features": frozenset(),
        "ManagerBrandService.create_brand": frozenset(
            {"manager_brand.create_brand"}
        ),
        "ManagerBrandService.update_brand": frozenset(
            {"manager_brand.update_brand"}
        ),
        "ManagerBrandService.delete_brand": frozenset(
            {"manager_brand.delete_brand"}
        ),
        "ManagerBrandService.create_brand_feature": frozenset(
            {"manager_brand.create_brand_feature"}
        ),
        "ManagerBrandService.update_brand_feature": frozenset(
            {"manager_brand.update_brand_feature"}
        ),
        "ManagerBrandService.delete_brand_feature": frozenset(
            {"manager_brand.delete_brand_feature"}
        ),
        "ManagerBrandService.list_brand_series": frozenset(
            {"manager_brand.list_brand_series"}
        ),
        "ManagerBrandService.create_brand_series": frozenset(
            {"manager_brand.create_brand_series"}
        ),
        "ManagerBrandService.update_brand_series": frozenset(
            {"manager_brand.update_brand_series"}
        ),
        "ManagerBrandService.apply_series_gallery_to_products": frozenset(
            {"manager_brand.apply_series_gallery_to_products"}
        ),
        "ManagerBrandService.delete_brand_series": frozenset(
            {"manager_brand.delete_brand_series"}
        ),
    }
)


GLOBAL_CATALOG_MUTATION_CONTRACTS: Mapping[
    str,
    GlobalCatalogMutationContract,
] = MappingProxyType(
    {
        "importer.import_product": _contract(
            "importer.import_product",
            "product_import",
        ),
        "manager_media.set_main_image": _contract(
            "manager_media.set_main_image",
            "product_media_set_main",
        ),
        "manager_media.delete_gallery_image": _contract(
            "manager_media.delete_gallery_image",
            "product_media_gallery_delete",
        ),
        "manager_media.crop_gallery_image": _contract(
            "manager_media.crop_gallery_image",
            "product_media_crop",
        ),
        "manager_media.remove_background_gallery_image": _contract(
            "manager_media.remove_background_gallery_image",
            "product_media_background_remove",
        ),
        "manager_media.reuse_image_link": _contract(
            "manager_media.reuse_image_link",
            "product_media_reuse",
        ),
        "manager_media.save_image_from_bytes": _contract(
            "manager_media.save_image_from_bytes",
            "product_media_upload",
        ),
        "manager_media.save_images_from_bytes": _contract(
            "manager_media.save_images_from_bytes",
            "product_media_upload_batch",
        ),
        "manager_media.bulk_add_gallery_images": _contract(
            "manager_media.bulk_add_gallery_images",
            "product_media_bulk_add",
        ),
        "manager_media.bulk_delete_common_gallery_images": _contract(
            "manager_media.bulk_delete_common_gallery_images",
            "product_media_bulk_delete",
        ),
        "manager_media.apply_gallery_to_series": _contract(
            "manager_media.apply_gallery_to_series",
            "product_series_gallery_apply",
        ),
        "manager_media.bulk_upload_local_images": _contract(
            "manager_media.bulk_upload_local_images",
            "product_media_bulk_upload",
        ),
        "feature_assignment.delete_product_assignment": _contract(
            "feature_assignment.delete_product_assignment",
            "product_feature_delete",
        ),
        "feature_assignment.delete_target_link.brand": _contract(
            "feature_assignment.delete_target_link.brand",
            "feature_brand_link_delete",
        ),
        "feature_assignment.delete_target_link.series": _contract(
            "feature_assignment.delete_target_link.series",
            "feature_series_link_delete",
        ),
        "product_image_variant.reprocess_variant": _contract(
            "product_image_variant.reprocess_variant",
            "product_media_variant_reprocess",
        ),
        "product_image_variant.process_missing_variants": _contract(
            "product_image_variant.process_missing_variants",
            "product_media_variant_batch",
        ),
        "yandex_feed_image.backfill": _contract(
            "yandex_feed_image.backfill",
            "product_media_yandex_feed_backfill",
        ),
        "manager_brand.create_brand": _contract(
            "manager_brand.create_brand",
            "brand_create",
        ),
        "manager_brand.update_brand": _contract(
            "manager_brand.update_brand",
            "brand_update",
        ),
        "manager_brand.delete_brand": _contract(
            "manager_brand.delete_brand",
            "brand_delete",
        ),
        "manager_brand.create_brand_feature": _contract(
            "manager_brand.create_brand_feature",
            "brand_feature_create",
        ),
        "manager_brand.update_brand_feature": _contract(
            "manager_brand.update_brand_feature",
            "brand_feature_update",
        ),
        "manager_brand.delete_brand_feature": _contract(
            "manager_brand.delete_brand_feature",
            "brand_feature_delete",
        ),
        "manager_brand.list_brand_series": _contract(
            "manager_brand.list_brand_series",
            "brand_series_auto_sync",
        ),
        "manager_brand.create_brand_series": _contract(
            "manager_brand.create_brand_series",
            "brand_series_create",
        ),
        "manager_brand.update_brand_series": _contract(
            "manager_brand.update_brand_series",
            "brand_series_update",
        ),
        "manager_brand.apply_series_gallery_to_products": _contract(
            "manager_brand.apply_series_gallery_to_products",
            "brand_series_gallery_apply",
        ),
        "manager_brand.delete_brand_series": _contract(
            "manager_brand.delete_brand_series",
            "brand_series_delete",
        ),
    }
)

if frozenset(GLOBAL_CATALOG_MUTATION_CONTRACTS) != PUBLIC_CATALOG_MUTATION_PRODUCERS:
    raise RuntimeError("Catalog mutation producer inventory is incomplete")

_entrypoint_producers = frozenset(
    producer
    for producers in PUBLIC_CATALOG_MUTATION_ENTRYPOINTS.values()
    for producer in producers
)
if _entrypoint_producers != PUBLIC_CATALOG_MUTATION_PRODUCERS:
    raise RuntimeError("Catalog mutation entrypoint inventory is incomplete")


def require_global_catalog_mutation_contract(
    producer: str,
) -> GlobalCatalogMutationContract:
    normalized = str(producer or "").strip()
    try:
        return GLOBAL_CATALOG_MUTATION_CONTRACTS[normalized]
    except KeyError as exc:
        raise ValueError(
            f"Unregistered global catalog mutation producer: {normalized or '<empty>'}"
        ) from exc
