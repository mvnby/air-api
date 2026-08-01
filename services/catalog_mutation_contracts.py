"""Explicit catalog mutation producers that must invalidate storefront caches."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class GlobalCatalogMutationContract:
    producer: str
    reason: str


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

PUBLIC_CATALOG_MUTATION_PRODUCERS = frozenset(
    {
        *IMPORTER_GLOBAL_MUTATION_PRODUCERS,
        *MANAGER_MEDIA_GLOBAL_MUTATION_PRODUCERS,
        *FEATURE_DELETE_GLOBAL_MUTATION_PRODUCERS,
    }
)

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
