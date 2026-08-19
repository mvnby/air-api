"""Central route policy for platform-global Manager operations.

Tenant-scoped CRM and commerce routes intentionally do not use this route
class. The policy is keyed by stable operation IDs so adding a new global
mutation requires an explicit permission decision that is covered by tests.
"""

from collections.abc import Sequence
from typing import Any

from fastapi import Depends
from fastapi.params import Depends as DependsParam
from fastapi.routing import APIRoute

from core.security import (
    require_system_manager_tenant_scope,
    require_system_owner_access,
)
from routers import manager_operation_ids as operation_ids


PLATFORM_MANAGER_OPERATION_IDS = frozenset(
    {
        # Catalog products and imports.
        operation_ids.GET_MANAGER_PRODUCTS,
        operation_ids.GET_MANAGER_PRODUCT,
        operation_ids.SMART_SEARCH_PRODUCTS,
        operation_ids.CREATE_MANAGER_PRODUCT,
        operation_ids.DUPLICATE_MANAGER_PRODUCT,
        operation_ids.UPDATE_PRODUCT,
        operation_ids.DELETE_MANAGER_PRODUCT,
        operation_ids.BULK_ROUND_PRICE,
        operation_ids.BULK_SET_RRC_PRICE,
        operation_ids.BULK_DELETE_MANAGER_PRODUCTS,
        operation_ids.IMPORT_ONLINER,
        operation_ids.CATALOG_IMPORT,
        operation_ids.START_CATALOG_IMPORT_JOB,
        operation_ids.GET_CURRENT_CATALOG_IMPORT_JOB_STATUS,
        operation_ids.GET_CATALOG_IMPORT_JOB_STATUS,
        operation_ids.PREVIEW_MDV_CATALOG_IMPORT,
        operation_ids.START_MDV_CATALOG_IMPORT_JOB,
        operation_ids.GET_MANAGER_CATALOG_QUALITY_REPORT,
        operation_ids.GET_MANAGER_YANDEX_BUSINESS_QUALITY_REPORT,
        # Catalog dictionaries and projections.
        operation_ids.CREATE_MANAGER_BRAND,
        operation_ids.UPDATE_MANAGER_BRAND,
        operation_ids.DELETE_MANAGER_BRAND,
        operation_ids.CREATE_MANAGER_BRAND_FEATURE,
        operation_ids.UPDATE_MANAGER_BRAND_FEATURE,
        operation_ids.DELETE_MANAGER_BRAND_FEATURE,
        operation_ids.CREATE_MANAGER_BRAND_SERIES,
        operation_ids.UPDATE_MANAGER_BRAND_SERIES,
        operation_ids.APPLY_MANAGER_SERIES_GALLERY_TO_PRODUCTS,
        operation_ids.DELETE_MANAGER_BRAND_SERIES,
        operation_ids.CREATE_MANAGER_TAG_GROUP,
        operation_ids.UPDATE_MANAGER_TAG_GROUP,
        operation_ids.DELETE_MANAGER_TAG_GROUP,
        operation_ids.CREATE_MANAGER_TAG,
        operation_ids.UPDATE_MANAGER_TAG,
        operation_ids.DELETE_MANAGER_TAG,
        operation_ids.CREATE_MANAGER_FEATURE,
        operation_ids.UPDATE_MANAGER_FEATURE,
        operation_ids.ARCHIVE_MANAGER_FEATURE,
        operation_ids.UPSERT_MANAGER_FEATURE_TARGET_LINK,
        operation_ids.DELETE_MANAGER_FEATURE_TARGET_LINK,
        operation_ids.UPDATE_MANAGER_PRODUCT_FEATURES,
        operation_ids.DELETE_MANAGER_PRODUCT_FEATURE,
        operation_ids.APPLY_MANAGER_PRODUCT_FEATURE_SUGGESTIONS,
        operation_ids.PREVIEW_MANAGER_FEATURE_SERIES_MIGRATION,
        operation_ids.APPLY_MANAGER_FEATURE_SERIES_MIGRATION,
        operation_ids.CREATE_MANAGER_FEATURE_CONTENT_AI_DRAFT,
        operation_ids.CREATE_MANAGER_SERIES_CONTENT_AI_DRAFT,
        operation_ids.CREATE_MANAGER_BRAND_SHORT_DESCRIPTION_AI_DRAFT,
        operation_ids.BULK_UPDATE_SPECS,
        operation_ids.NORMALIZE_LEGACY_SPECS,
        # Storefront offer prices and publication remain operator-owned.
        operation_ids.UPSERT_MANAGER_TENANT_OFFER,
        operation_ids.UPDATE_MANAGER_TENANT_OFFER,
        operation_ids.CREATE_MANAGER_PRODUCT_COLLECTION,
        operation_ids.UPDATE_MANAGER_PRODUCT_COLLECTION,
        operation_ids.DUPLICATE_MANAGER_PRODUCT_COLLECTION,
        operation_ids.ARCHIVE_MANAGER_PRODUCT_COLLECTION,
        operation_ids.REPLACE_MANAGER_PRODUCT_COLLECTION_ITEMS,
        operation_ids.REPLACE_MANAGER_PRODUCT_COLLECTION_PLACEMENTS,
        # Platform-owned service dictionaries.
        operation_ids.CREATE_MANAGER_TARIFF,
        operation_ids.UPDATE_MANAGER_TARIFF,
        operation_ids.DELETE_MANAGER_TARIFF,
        operation_ids.CREATE_MANAGER_TARIFF_RULE,
        operation_ids.UPDATE_MANAGER_TARIFF_RULE,
        operation_ids.DELETE_MANAGER_TARIFF_RULE,
        operation_ids.CREATE_MANAGER_REPAIR_COMPLAINT_PRESET,
        operation_ids.UPDATE_MANAGER_REPAIR_COMPLAINT_PRESET,
        operation_ids.DELETE_MANAGER_REPAIR_COMPLAINT_PRESET,
        # Saved shared estimates and platform warranty definitions.
        operation_ids.CREATE_MANAGER_SERVICE_ESTIMATE,
        operation_ids.LIST_MANAGER_SERVICE_ESTIMATES,
        operation_ids.GET_MANAGER_SERVICE_ESTIMATE,
        operation_ids.GET_MANAGER_SERVICE_ESTIMATE_ORDER_LINES,
        operation_ids.DELETE_MANAGER_SERVICE_ESTIMATE,
        operation_ids.CREATE_MANAGER_WARRANTY_POLICY,
        operation_ids.PATCH_MANAGER_WARRANTY_POLICY,
        # Supplier data and supply workflows are platform-global today.
        operation_ids.CREATE_SUPPLIER,
        operation_ids.PATCH_SUPPLIER,
        operation_ids.DELETE_SUPPLIER,
        operation_ids.LIST_SUPPLIERS,
        operation_ids.LIST_SUPPLIER_CONTACTS,
        operation_ids.CREATE_SUPPLIER_CONTACT,
        operation_ids.PATCH_SUPPLIER_CONTACT,
        operation_ids.DELETE_SUPPLIER_CONTACT,
        operation_ids.LIST_SUPPLIER_WAREHOUSES,
        operation_ids.CREATE_SUPPLIER_WAREHOUSE,
        operation_ids.PATCH_SUPPLIER_WAREHOUSE,
        operation_ids.DELETE_SUPPLIER_WAREHOUSE,
        operation_ids.LIST_SUPPLIER_SHEETS,
        operation_ids.LIST_SUPPLIER_SOURCES,
        operation_ids.CREATE_SUPPLIER_SOURCE,
        operation_ids.PATCH_SUPPLIER_SOURCE,
        operation_ids.DELETE_SUPPLIER_SOURCE,
        operation_ids.ANALYZE_SUPPLIER_SOURCE,
        operation_ids.SYNC_SUPPLIER_SOURCE,
        operation_ids.SYNC_ALL_SUPPLIER_SOURCES,
        operation_ids.LIST_UNMAPPED_SUPPLIER_OFFERS,
        operation_ids.LIST_PRODUCT_SUPPLIER_OFFER_CANDIDATES,
        operation_ids.LIST_SUPPLIER_SOURCE_URL_IMPORT_CANDIDATES,
        operation_ids.START_SUPPLIER_SOURCE_URL_IMPORT,
        operation_ids.SUGGEST_SUPPLIER_OFFERS,
        operation_ids.CREATE_SUPPLIER_MAPPING,
        operation_ids.BULK_CREATE_SUPPLIER_MAPPINGS,
        operation_ids.DELETE_SUPPLIER_MAPPING,
        operation_ids.GET_PRODUCT_SUPPLIER_OFFERS,
        operation_ids.PUT_SUPPLIER_OFFER_MAPPING,
        operation_ids.UPSERT_PRODUCT_LOCAL_STOCK,
        operation_ids.LIST_SUPPLY_REQUESTS,
        operation_ids.CREATE_SUPPLY_REQUEST,
        operation_ids.CREATE_SUPPLY_REQUEST_FROM_ORDER_LINES,
        operation_ids.CREATE_STOCK_SUPPLY_REQUEST,
        operation_ids.PATCH_SUPPLY_REQUEST,
        operation_ids.PATCH_SUPPLY_REQUEST_LINE,
        operation_ids.GENERATE_SUPPLY_REQUEST_SUPPLIER_MESSAGE,
        operation_ids.GENERATE_SUPPLY_LOGISTICS_MESSAGE,
        # Product gallery, reusable media and cleanup workflows.
        operation_ids.UPLOAD_IMAGE,
        operation_ids.UPLOAD_LOCAL_IMAGES,
        operation_ids.LINK_SEARCH_RESULT,
        operation_ids.SET_MAIN_IMAGE,
        operation_ids.DELETE_IMAGE,
        operation_ids.CROP_PRODUCT_IMAGE,
        operation_ids.REMOVE_PRODUCT_IMAGE_BACKGROUND,
        operation_ids.REUSE_IMAGE,
        operation_ids.BULK_ADD_GALLERY_IMAGES,
        operation_ids.BULK_UPLOAD_LOCAL_IMAGES,
        operation_ids.BULK_DELETE_COMMON_GALLERY_IMAGES,
        operation_ids.APPLY_GALLERY_TO_SERIES,
        operation_ids.PROCESS_MISSING_IMAGE_VARIANTS,
        operation_ids.REPROCESS_IMAGE_VARIANT,
        operation_ids.GET_IMAGE_VARIANT_CANDIDATES,
        operation_ids.CLEANUP_MEDIA,
        operation_ids.LIST_MEDIA_ASSETS,
        operation_ids.GET_MEDIA_BACKGROUND_REMOVAL_CONFIG,
        operation_ids.UPLOAD_MEDIA_ASSETS,
        operation_ids.UPLOAD_MEDIA_ASSET_FROM_URL,
        operation_ids.BACKFILL_REFERENCED_MEDIA_ASSETS,
        operation_ids.UPDATE_MEDIA_ASSET,
        operation_ids.CROP_MEDIA_ASSET,
        operation_ids.REMOVE_MEDIA_ASSET_BACKGROUND,
        operation_ids.DELETE_MEDIA_ASSET,
        operation_ids.LIST_MEDIA_PROCESSING_JOBS,
        operation_ids.CREATE_MEDIA_PROCESSING_JOB,
        operation_ids.CREATE_MAIN_IMAGE_CLEANUP_BATCH,
        operation_ids.LIST_MAIN_IMAGE_CLEANUP_BATCHES,
        operation_ids.LIST_MAIN_IMAGE_CLEANUP_ITEMS,
        operation_ids.APPROVE_MAIN_IMAGE_CLEANUP_ITEMS,
        operation_ids.REJECT_MAIN_IMAGE_CLEANUP_ITEMS,
        operation_ids.SKIP_MAIN_IMAGE_CLEANUP_ITEMS,
        operation_ids.LIST_MAIN_IMAGE_CLEANUP_SKIP_REASONS,
        # Platform-wide telemetry, not tenant CRM data.
        operation_ids.GET_MANAGER_CRM_HEALTH_REPORT,
    }
)


SYSTEM_OWNER_OPERATION_IDS = frozenset(
    {
        operation_ids.LIST_MANAGER_SETTINGS,
        operation_ids.UPDATE_MANAGER_SETTING,
        operation_ids.CREATE_MANAGER_SETTING,
        operation_ids.GET_MANAGER_GOOGLE_AUTH_STATUS,
        operation_ids.GET_MANAGER_GOOGLE_AUTH_URL,
        operation_ids.LIST_MANAGER_BACKUPS,
        operation_ids.START_MANAGER_BACKUP_RUN,
        operation_ids.GET_MANAGER_BACKUP_RUN_STATUS,
        operation_ids.START_MANAGER_BACKUP_RESTORE,
        operation_ids.GET_MANAGER_BACKUP_RESTORE_STATUS,
    }
)


def required_permission_dependency(operation_id: str | None):
    if operation_id in PLATFORM_MANAGER_OPERATION_IDS:
        return require_system_manager_tenant_scope
    if operation_id in SYSTEM_OWNER_OPERATION_IDS:
        return require_system_owner_access
    return None


class ManagerPermissionRoute(APIRoute):
    """Attach the centralized Manager permission selected by operation ID."""

    def __init__(
        self,
        *args: Any,
        operation_id: str | None = None,
        dependencies: Sequence[DependsParam] | None = None,
        **kwargs: Any,
    ) -> None:
        permission_dependency = required_permission_dependency(operation_id)
        route_dependencies = list(dependencies or ())
        if permission_dependency is not None and not any(
            dependency.dependency is permission_dependency
            for dependency in route_dependencies
        ):
            route_dependencies.insert(0, Depends(permission_dependency))
        super().__init__(
            *args,
            operation_id=operation_id,
            dependencies=route_dependencies,
            **kwargs,
        )
