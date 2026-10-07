/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_bulk_upload_local_images } from '../models/Body_bulk_upload_local_images';
import type { Body_recognize_manager_customer_requisites } from '../models/Body_recognize_manager_customer_requisites';
import type { Body_replace_product_image_local } from '../models/Body_replace_product_image_local';
import type { Body_upload_local_images } from '../models/Body_upload_local_images';
import type { BulkGalleryAddRequest } from '../models/BulkGalleryAddRequest';
import type { BulkGalleryDeleteRequest } from '../models/BulkGalleryDeleteRequest';
import type { BulkProductIdsRequest } from '../models/BulkProductIdsRequest';
import type { BulkRoundRequest } from '../models/BulkRoundRequest';
import type { BulkSpecUpdate } from '../models/BulkSpecUpdate';
import type { CatalogImportJobStartResponse } from '../models/CatalogImportJobStartResponse';
import type { CatalogImportJobStatusResponse } from '../models/CatalogImportJobStatusResponse';
import type { CatalogImportPayload } from '../models/CatalogImportPayload';
import type { CatalogImportResultResponse } from '../models/CatalogImportResultResponse';
import type { CommonGalleryImageResponse } from '../models/CommonGalleryImageResponse';
import type { CustomerRequisitesConfirmPayload } from '../models/CustomerRequisitesConfirmPayload';
import type { CustomerRequisitesConfirmResponse } from '../models/CustomerRequisitesConfirmResponse';
import type { CustomerRequisitesRecognitionResponse } from '../models/CustomerRequisitesRecognitionResponse';
import type { CustomerRequisitesTextPayload } from '../models/CustomerRequisitesTextPayload';
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerAuthStatusResponse } from '../models/ManagerAuthStatusResponse';
import type { ManagerBulkDeleteProductsResponse } from '../models/ManagerBulkDeleteProductsResponse';
import type { ManagerBulkRoundPriceResponse } from '../models/ManagerBulkRoundPriceResponse';
import type { ManagerBulkSetRrcPriceResponse } from '../models/ManagerBulkSetRrcPriceResponse';
import type { ManagerBulkSpecsResponse } from '../models/ManagerBulkSpecsResponse';
import type { ManagerCatalogCustomerItemResponse } from '../models/ManagerCatalogCustomerItemResponse';
import type { ManagerCatalogCustomerListResponse } from '../models/ManagerCatalogCustomerListResponse';
import type { ManagerCatalogProductItemResponse } from '../models/ManagerCatalogProductItemResponse';
import type { ManagerCatalogProductListResponse } from '../models/ManagerCatalogProductListResponse';
import type { ManagerCustomerBranchCreatePayload } from '../models/ManagerCustomerBranchCreatePayload';
import type { ManagerCustomerBranchItemResponse } from '../models/ManagerCustomerBranchItemResponse';
import type { ManagerCustomerBranchListResponse } from '../models/ManagerCustomerBranchListResponse';
import type { ManagerCustomerBranchUpdatePayload } from '../models/ManagerCustomerBranchUpdatePayload';
import type { ManagerCustomerContactCreatePayload } from '../models/ManagerCustomerContactCreatePayload';
import type { ManagerCustomerContactHistoryResponse } from '../models/ManagerCustomerContactHistoryResponse';
import type { ManagerCustomerContactItemResponse } from '../models/ManagerCustomerContactItemResponse';
import type { ManagerCustomerContactListResponse } from '../models/ManagerCustomerContactListResponse';
import type { ManagerCustomerContactUpdatePayload } from '../models/ManagerCustomerContactUpdatePayload';
import type { ManagerCustomerCreatePayload } from '../models/ManagerCustomerCreatePayload';
import type { ManagerCustomerDocumentListResponse } from '../models/ManagerCustomerDocumentListResponse';
import type { ManagerCustomerReconciliationDocumentResponse } from '../models/ManagerCustomerReconciliationDocumentResponse';
import type { ManagerCustomerReconciliationEventRelationPayload } from '../models/ManagerCustomerReconciliationEventRelationPayload';
import type { ManagerCustomerReconciliationEventRelationResponse } from '../models/ManagerCustomerReconciliationEventRelationResponse';
import type { ManagerCustomerReconciliationResponse } from '../models/ManagerCustomerReconciliationResponse';
import type { ManagerCustomerUpdatePayload } from '../models/ManagerCustomerUpdatePayload';
import type { ManagerLegacyReconciliationConfirmPayload } from '../models/ManagerLegacyReconciliationConfirmPayload';
import type { ManagerLegacyReconciliationConfirmResponse } from '../models/ManagerLegacyReconciliationConfirmResponse';
import type { ManagerLegacyReconciliationReviewResponse } from '../models/ManagerLegacyReconciliationReviewResponse';
import type { ManagerMediaApplySeriesResponse } from '../models/ManagerMediaApplySeriesResponse';
import type { ManagerMediaBulkAddResponse } from '../models/ManagerMediaBulkAddResponse';
import type { ManagerMediaBulkDeleteResponse } from '../models/ManagerMediaBulkDeleteResponse';
import type { ManagerMediaBulkUploadResponse } from '../models/ManagerMediaBulkUploadResponse';
import type { ManagerMediaCleanupResponse } from '../models/ManagerMediaCleanupResponse';
import type { ManagerMediaDeleteImageResponse } from '../models/ManagerMediaDeleteImageResponse';
import type { ManagerMediaImageLinkResponse } from '../models/ManagerMediaImageLinkResponse';
import type { ManagerMediaImageSearchResultResponse } from '../models/ManagerMediaImageSearchResultResponse';
import type { ManagerMediaReuseImageResponse } from '../models/ManagerMediaReuseImageResponse';
import type { ManagerMediaReuseSearchItemResponse } from '../models/ManagerMediaReuseSearchItemResponse';
import type { ManagerMediaSetMainImageResponse } from '../models/ManagerMediaSetMainImageResponse';
import type { ManagerMediaUploadLocalImagesResponse } from '../models/ManagerMediaUploadLocalImagesResponse';
import type { ManagerNormalizeLegacySpecsResponse } from '../models/ManagerNormalizeLegacySpecsResponse';
import type { ManagerPasswordChangePayload } from '../models/ManagerPasswordChangePayload';
import type { ManagerStorefrontListResponse } from '../models/ManagerStorefrontListResponse';
import type { ManagerTagGroupResponse } from '../models/ManagerTagGroupResponse';
import type { MdvCatalogImportPayload } from '../models/MdvCatalogImportPayload';
import type { MdvCatalogPreviewPayload } from '../models/MdvCatalogPreviewPayload';
import type { MdvCatalogPreviewResponse } from '../models/MdvCatalogPreviewResponse';
import type { ProductCreate } from '../models/ProductCreate';
import type { ProductDuplicatePayload } from '../models/ProductDuplicatePayload';
import type { ProductImageCropPayload } from '../models/ProductImageCropPayload';
import type { ProductImageVariantBatchProcessResponse } from '../models/ProductImageVariantBatchProcessResponse';
import type { ProductImageVariantCandidatesResponse } from '../models/ProductImageVariantCandidatesResponse';
import type { ProductImageVariantResponse } from '../models/ProductImageVariantResponse';
import type { ProductLocalStockPayload } from '../models/ProductLocalStockPayload';
import type { ProductLocalStockResponse } from '../models/ProductLocalStockResponse';
import type { ProductMainImageCleanupApprovePayload } from '../models/ProductMainImageCleanupApprovePayload';
import type { ProductMainImageCleanupBatchCreatePayload } from '../models/ProductMainImageCleanupBatchCreatePayload';
import type { ProductMainImageCleanupBatchCreateResponse } from '../models/ProductMainImageCleanupBatchCreateResponse';
import type { ProductMainImageCleanupBatchListResponse } from '../models/ProductMainImageCleanupBatchListResponse';
import type { ProductMainImageCleanupDecisionResponse } from '../models/ProductMainImageCleanupDecisionResponse';
import type { ProductMainImageCleanupItemListResponse } from '../models/ProductMainImageCleanupItemListResponse';
import type { ProductMainImageCleanupRejectPayload } from '../models/ProductMainImageCleanupRejectPayload';
import type { ProductMainImageCleanupSkipPayload } from '../models/ProductMainImageCleanupSkipPayload';
import type { ProductMainImageCleanupSkipReasonsResponse } from '../models/ProductMainImageCleanupSkipReasonsResponse';
import type { ProductUpdate } from '../models/ProductUpdate';
import type { SupplierContactCreatePayload } from '../models/SupplierContactCreatePayload';
import type { SupplierContactListResponse } from '../models/SupplierContactListResponse';
import type { SupplierContactResponse } from '../models/SupplierContactResponse';
import type { SupplierContactUpdatePayload } from '../models/SupplierContactUpdatePayload';
import type { SupplierCreatePayload } from '../models/SupplierCreatePayload';
import type { SupplierListResponse } from '../models/SupplierListResponse';
import type { SupplierMappingBulkCreatePayload } from '../models/SupplierMappingBulkCreatePayload';
import type { SupplierMappingBulkCreateResponse } from '../models/SupplierMappingBulkCreateResponse';
import type { SupplierMappingCreatePayload } from '../models/SupplierMappingCreatePayload';
import type { SupplierMappingResponse } from '../models/SupplierMappingResponse';
import type { SupplierOfferCandidateListResponse } from '../models/SupplierOfferCandidateListResponse';
import type { SupplierOfferListResponse } from '../models/SupplierOfferListResponse';
import type { SupplierOfferMappingPutPayload } from '../models/SupplierOfferMappingPutPayload';
import type { SupplierOfferMappingResponse } from '../models/SupplierOfferMappingResponse';
import type { SupplierOfferSuggestionsPayload } from '../models/SupplierOfferSuggestionsPayload';
import type { SupplierOfferSuggestionsResponse } from '../models/SupplierOfferSuggestionsResponse';
import type { SupplierPriceSourceCreatePayload } from '../models/SupplierPriceSourceCreatePayload';
import type { SupplierPriceSourceListResponse } from '../models/SupplierPriceSourceListResponse';
import type { SupplierPriceSourceResponse } from '../models/SupplierPriceSourceResponse';
import type { SupplierPriceSourceUpdatePayload } from '../models/SupplierPriceSourceUpdatePayload';
import type { SupplierResponse } from '../models/SupplierResponse';
import type { SupplierSheetTabListResponse } from '../models/SupplierSheetTabListResponse';
import type { SupplierSourceAnalysisResponse } from '../models/SupplierSourceAnalysisResponse';
import type { SupplierSourceUrlImportCandidateListResponse } from '../models/SupplierSourceUrlImportCandidateListResponse';
import type { SupplierSourceUrlImportPayload } from '../models/SupplierSourceUrlImportPayload';
import type { SupplierSyncRunResponse } from '../models/SupplierSyncRunResponse';
import type { SupplierUpdatePayload } from '../models/SupplierUpdatePayload';
import type { SupplierWarehouseCreatePayload } from '../models/SupplierWarehouseCreatePayload';
import type { SupplierWarehouseListResponse } from '../models/SupplierWarehouseListResponse';
import type { SupplierWarehouseResponse } from '../models/SupplierWarehouseResponse';
import type { SupplierWarehouseUpdatePayload } from '../models/SupplierWarehouseUpdatePayload';
import type { SupplyLogisticsMessagePayload } from '../models/SupplyLogisticsMessagePayload';
import type { SupplyMessageResponse } from '../models/SupplyMessageResponse';
import type { SupplyRequestCreatePayload } from '../models/SupplyRequestCreatePayload';
import type { SupplyRequestCreateResponse } from '../models/SupplyRequestCreateResponse';
import type { SupplyRequestFromOrderLinesPayload } from '../models/SupplyRequestFromOrderLinesPayload';
import type { SupplyRequestLineUpdatePayload } from '../models/SupplyRequestLineUpdatePayload';
import type { SupplyRequestListResponse } from '../models/SupplyRequestListResponse';
import type { SupplyRequestMessagePayload } from '../models/SupplyRequestMessagePayload';
import type { SupplyRequestResponse } from '../models/SupplyRequestResponse';
import type { SupplyRequestStockCreatePayload } from '../models/SupplyRequestStockCreatePayload';
import type { SupplyRequestUpdatePayload } from '../models/SupplyRequestUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerService {
    /**
     * List Products For Manager
     * Read a paginated shared product list for editing, including unpublished cards unless
     * filtered. page starts at 1 and limit is 1–100. Brand/category/series and technical
     * filters apply to the master catalog; publication here is not a tenant-offer publication
     * flag.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param page
     * @param limit
     * @param search
     * @param isPublished
     * @param areaMin
     * @param areaMax
     * @param isInverter
     * @param heatingMin
     * @param hasWifi
     * @param hasFreshAir
     * @param brandSlugs Brand slugs to include
     * @param seriesId Exact product series ID
     * @param categorySlug Category tag slug: cat-household/cat-multi/cat-industrial
     * @param categoryStatus Catalog category status: assigned/missing
     * @param sort
     * @returns ManagerCatalogProductListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerProducts(
        page: number = 1,
        limit: number = 40,
        search?: (string | null),
        isPublished?: (boolean | null),
        areaMin?: (number | null),
        areaMax?: (number | null),
        isInverter?: (boolean | null),
        heatingMin?: (number | null),
        hasWifi?: (boolean | null),
        hasFreshAir?: (boolean | null),
        brandSlugs?: (Array<string> | null),
        seriesId?: (number | null),
        categorySlug?: (string | null),
        categoryStatus?: ('assigned' | 'missing' | null),
        sort: string = 'recommended',
    ): CancelablePromise<ManagerCatalogProductListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/products/list',
            query: {
                'page': page,
                'limit': limit,
                'search': search,
                'is_published': isPublished,
                'area_min': areaMin,
                'area_max': areaMax,
                'is_inverter': isInverter,
                'heating_min': heatingMin,
                'has_wifi': hasWifi,
                'has_fresh_air': hasFreshAir,
                'brand_slugs': brandSlugs,
                'series_id': seriesId,
                'category_slug': categorySlug,
                'category_status': categoryStatus,
                'sort': sort,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Customers For Manager
     * Page customers in the current tenant with order counts and contact summaries. Archived
     * customers are hidden by default; only_with_orders defaults true, and supplied
     * type/search/favorite filters narrow the result. limit is at most 100. This does not
     * expose another tenant’s customer directory.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param page
     * @param limit
     * @param search
     * @param type
     * @param onlyWithOrders
     * @param onlyFavorites
     * @param includeArchived
     * @returns ManagerCatalogCustomerListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCustomers(
        page: number = 1,
        limit: number = 20,
        search?: (string | null),
        type?: (string | null),
        onlyWithOrders: boolean = true,
        onlyFavorites: boolean = false,
        includeArchived: boolean = false,
    ): CancelablePromise<ManagerCatalogCustomerListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/customers',
            query: {
                'page': page,
                'limit': limit,
                'search': search,
                'type': type,
                'only_with_orders': onlyWithOrders,
                'only_favorites': onlyFavorites,
                'include_archived': includeArchived,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Customer For Manager
     * Create a customer in the current tenant after party/signing-mode and duplicate checks.
     * Invalid customer values return 400; matching existing identity returns 409 with
     * duplicate customer/field hints. Repeating POST is not replayed through an idempotency
     * receipt. See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ManagerCatalogCustomerItemResponse Successful Response
     * @throws ApiError
     */
    public static createManagerCustomer(
        requestBody: ManagerCustomerCreatePayload,
    ): CancelablePromise<ManagerCatalogCustomerItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Recognize Customer Requisites For Manager
     * Recognize uploaded customer requisites and save a review draft in the current tenant
     * without creating/updating a customer. Requires system-tenant Manager access for this OCR
     * operation. Accepts JPG/PNG/WEBP/PDF/DOC/DOCX files up to 10 MB; PDFs are bounded to five
     * pages. Invalid/unsupported/oversized content returns 400. Returns inferred party/signing
     * context and duplicate hints for explicit confirmation. See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param formData
     * @returns CustomerRequisitesRecognitionResponse Successful Response
     * @throws ApiError
     */
    public static recognizeManagerCustomerRequisites(
        formData: Body_recognize_manager_customer_requisites,
    ): CancelablePromise<CustomerRequisitesRecognitionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/requisites/recognize',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Recognize Customer Requisites Text For Manager
     * Parse requisites text and save a review draft in the current tenant without changing a
     * customer. Requires system-tenant Manager access; submitted text is bounded to 12000
     * characters by the request model. Invalid text returns 400. Duplicate hints are
     * suggestions, not an automatic choice of customer to update. See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns CustomerRequisitesRecognitionResponse Successful Response
     * @throws ApiError
     */
    public static recognizeManagerCustomerRequisitesText(
        requestBody: CustomerRequisitesTextPayload,
    ): CancelablePromise<CustomerRequisitesRecognitionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/requisites/recognize-text',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Confirm Customer Requisites For Manager
     * Confirm a saved recognition belonging to the current tenant, explicitly creating a
     * customer or updating the selected one. Selected-field updates require baseline values
     * and preserve unselected fields; a changed baseline or duplicate identity returns 409.
     * Missing recognition/customer returns 404, invalid confirmation 400. Repeating an already
     * confirmed recognition returns its customer. See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param recognitionId
     * @param requestBody
     * @returns CustomerRequisitesConfirmResponse Successful Response
     * @throws ApiError
     */
    public static confirmManagerCustomerRequisites(
        recognitionId: number,
        requestBody: CustomerRequisitesConfirmPayload,
    ): CancelablePromise<CustomerRequisitesConfirmResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/requisites/{recognition_id}/confirm',
            path: {
                'recognition_id': recognitionId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Customer For Manager
     * Read the detailed customer projection owned by the current tenant, including contact
     * summary and latest delivery-address context. Missing or inaccessible customer returns
     * 404; the detail does not grant access to foreign-tenant relationship IDs.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @returns ManagerCatalogCustomerItemResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCustomerDetail(
        customerId: number,
    ): CancelablePromise<ManagerCatalogCustomerItemResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/customers/{customer_id}',
            path: {
                'customer_id': customerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Customer For Manager
     * Patch supplied customer fields in the current tenant. Optional text can be cleared;
     * phone/email changes synchronize the primary contact, and a party-type change derives a
     * compatible signing mode unless explicitly supplied. Missing customer returns 404;
     * incompatible signing mode or invalid values returns 400. This direct patch has no
     * baseline/expected_version conflict check; selective requisites confirmation has its own
     * contract. See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param requestBody
     * @returns ManagerCatalogCustomerItemResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerCustomer(
        customerId: number,
        requestBody: ManagerCustomerUpdatePayload,
    ): CancelablePromise<ManagerCatalogCustomerItemResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/customers/{customer_id}',
            path: {
                'customer_id': customerId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Customer For Manager
     * Delete a current-tenant customer only when it has no linked orders. Missing customer
     * returns 404; linked orders block deletion with 400. Repeating deletion returns 404
     * rather than replaying a receipt. Use the customer archive field when the record and
     * order history must remain.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteManagerCustomer(
        customerId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/customers/{customer_id}',
            path: {
                'customer_id': customerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Customer Docs For Manager
     * List documents attached to the current-tenant customer’s accessible orders, with
     * document basis, scope and official or confirmed-legacy identity. Missing customer
     * returns 404. Internal file titles are not promoted to official document numbers;
     * is_downloadable reflects the legacy provider file reference. See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @returns ManagerCustomerDocumentListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCustomerDocs(
        customerId: number,
    ): CancelablePromise<ManagerCustomerDocumentListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/customers/{customer_id}/docs',
            path: {
                'customer_id': customerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Customer Reconciliation For Manager
     * Calculate a customer ledger over the selected period and optional customer-owned
     * contract using orders in the current tenant/storefront. Returns readiness and warnings
     * for uncertain originals, delivery-event relationships and allocations; does not generate
     * a file or confirm evidence. Missing customer returns 404; invalid period/contract
     * returns 400. See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param dateFrom
     * @param dateTo
     * @param contractId
     * @returns ManagerCustomerReconciliationResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCustomerReconciliation(
        customerId: number,
        dateFrom?: (string | null),
        dateTo?: (string | null),
        contractId?: (number | null),
    ): CancelablePromise<ManagerCustomerReconciliationResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/customers/{customer_id}/reconciliation',
            path: {
                'customer_id': customerId,
            },
            query: {
                'date_from': dateFrom,
                'date_to': dateTo,
                'contract_id': contractId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Customer Reconciliation Document For Manager
     * Create a Google reconciliation statement for the current-tenant customer and
     * current-storefront orders after recalculating the selected period/contract and
     * rechecking confirmed legacy source hashes. Missing customer returns 404; invalid scope
     * or incomplete/changed evidence returns 409 with warnings where available. Each
     * successful POST creates a new provider file; no replay receipt is supplied. See the
     * [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param dateFrom
     * @param dateTo
     * @param contractId
     * @returns ManagerCustomerReconciliationDocumentResponse Successful Response
     * @throws ApiError
     */
    public static createManagerCustomerReconciliationDocument(
        customerId: number,
        dateFrom?: (string | null),
        dateTo?: (string | null),
        contractId?: (number | null),
    ): CancelablePromise<ManagerCustomerReconciliationDocumentResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/{customer_id}/reconciliation/document',
            path: {
                'customer_id': customerId,
            },
            query: {
                'date_from': dateFrom,
                'date_to': dateTo,
                'contract_id': contractId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Review Customer Reconciliation Legacy Document For Manager
     * Read an accessible legacy Google delivery original for the customer in the current
     * tenant/storefront and propose number/date/amount/contract with source text/hash. Does
     * not confirm evidence or rewrite the original. Missing scope/document returns 404;
     * unsupported/unreadable/oversized original returns 422. See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param documentId
     * @returns ManagerLegacyReconciliationReviewResponse Successful Response
     * @throws ApiError
     */
    public static reviewManagerCustomerReconciliationLegacyDocument(
        customerId: number,
        documentId: number,
    ): CancelablePromise<ManagerLegacyReconciliationReviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/{customer_id}/reconciliation/legacy-documents/{document_id}/review',
            path: {
                'customer_id': customerId,
                'document_id': documentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Confirm Customer Reconciliation Legacy Document For Manager
     * Store explicitly checked reconciliation identity for an accessible legacy original in
     * the current tenant/storefront, with source hash, excerpt and authenticated author.
     * Re-reads the original and checks submitted number/date/amount/contract against it;
     * changed or unsupported evidence returns 409, missing document 404. Updates metadata
     * without rewriting the Google original. No generic expected_version receipt is provided.
     * See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param documentId
     * @param requestBody
     * @returns ManagerLegacyReconciliationConfirmResponse Successful Response
     * @throws ApiError
     */
    public static confirmManagerCustomerReconciliationLegacyDocument(
        customerId: number,
        documentId: number,
        requestBody: ManagerLegacyReconciliationConfirmPayload,
    ): CancelablePromise<ManagerLegacyReconciliationConfirmResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/{customer_id}/reconciliation/legacy-documents/{document_id}/confirm',
            path: {
                'customer_id': customerId,
                'document_id': documentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Confirm Customer Reconciliation Event Relation For Manager
     * Confirm whether 2–10 distinct delivery documents represent one event or separate events
     * within one accessible order for this current-tenant customer/storefront. Requires active
     * authoritative identities and amounts; same-event documents must agree on date, amount
     * and contract. Invalid/inaccessible context returns 409. Stores reason/author and
     * fingerprints: changed document identity invalidates the relation for later
     * reconciliation. See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param requestBody
     * @returns ManagerCustomerReconciliationEventRelationResponse Successful Response
     * @throws ApiError
     */
    public static confirmManagerCustomerReconciliationEventRelation(
        customerId: number,
        requestBody: ManagerCustomerReconciliationEventRelationPayload,
    ): CancelablePromise<ManagerCustomerReconciliationEventRelationResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/{customer_id}/reconciliation/event-relation',
            path: {
                'customer_id': customerId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Customer Branches For Manager
     * List branches of a current-tenant customer with the default branch first. Missing or
     * inaccessible customer returns 404; reading does not create a default branch.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @returns ManagerCustomerBranchListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCustomerBranches(
        customerId: number,
    ): CancelablePromise<ManagerCustomerBranchListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/customers/{customer_id}/branches',
            path: {
                'customer_id': customerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Customer Branch For Manager
     * Create an address branch for a current-tenant customer. A first branch becomes default,
     * and explicitly selecting a default demotes siblings. Missing customer returns 404; blank
     * address returns 400. Repeating POST can create another branch; no replay receipt is
     * provided.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param requestBody
     * @returns ManagerCustomerBranchItemResponse Successful Response
     * @throws ApiError
     */
    public static createManagerCustomerBranch(
        customerId: number,
        requestBody: ManagerCustomerBranchCreatePayload,
    ): CancelablePromise<ManagerCustomerBranchItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/{customer_id}/branches',
            path: {
                'customer_id': customerId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Customer Branch For Manager
     * Patch supplied address/branch fields under a current-tenant customer. Selecting
     * default=true demotes siblings; default=false can leave no branch selected. Missing
     * customer/branch returns 404; blank address returns 400. No expected_version precondition
     * is supplied; existing document scope snapshots are independent of later branch edits.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param branchId
     * @param requestBody
     * @returns ManagerCustomerBranchItemResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerCustomerBranch(
        customerId: number,
        branchId: number,
        requestBody: ManagerCustomerBranchUpdatePayload,
    ): CancelablePromise<ManagerCustomerBranchItemResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/customers/{customer_id}/branches/{branch_id}',
            path: {
                'customer_id': customerId,
                'branch_id': branchId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Customer Branch For Manager
     * Delete a branch of a current-tenant customer; deleting the default selects the oldest
     * remaining branch as default. Missing customer/branch returns 404, including a repeated
     * delete. This removes the branch record rather than altering saved document scope
     * snapshots.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param branchId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerCustomerBranch(
        customerId: number,
        branchId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/customers/{customer_id}/branches/{branch_id}',
            path: {
                'customer_id': customerId,
                'branch_id': branchId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Customer Contacts
     * Read current-tenant customer contacts, ordered primary first and active first. When no
     * persisted contacts exist, returns a virtual legacy primary contact with id=null from the
     * customer phone/email; this read does not materialize it. Missing customer returns 404.
     * See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @returns ManagerCustomerContactListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCustomerContacts(
        customerId: number,
    ): CancelablePromise<ManagerCustomerContactListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/customers/{customer_id}/contacts',
            path: {
                'customer_id': customerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Customer Contact
     * Create a contact for a current-tenant customer and record field history with the
     * authenticated staff author. The first write materializes the legacy contact; creating a
     * primary contact can reuse that fallback. Selecting a primary demotes siblings and
     * synchronizes customer phone/email. Missing customer returns 404; blank name, inactive
     * primary or primary conflict returns 400. No replay receipt prevents duplicate
     * non-primary contacts. See the [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param requestBody
     * @returns ManagerCustomerContactItemResponse Successful Response
     * @throws ApiError
     */
    public static createManagerCustomerContact(
        customerId: number,
        requestBody: ManagerCustomerContactCreatePayload,
    ): CancelablePromise<ManagerCustomerContactItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/{customer_id}/contacts',
            path: {
                'customer_id': customerId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Customer Contact
     * Patch supplied fields on a persisted contact of a current-tenant customer and record
     * changed values/author. Primary changes synchronize customer phone/email;
     * removing/deactivating the primary selects another active contact when available and
     * refuses leaving no active replacement. Missing customer/contact returns 404; invalid
     * name/primary state returns 400. No expected_version precondition is provided. See the
     * [customer workspace
     * contract](https://github.com/mvnby/air-api/blob/main/docs/customer-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param contactId
     * @param requestBody
     * @returns ManagerCustomerContactItemResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerCustomerContact(
        customerId: number,
        contactId: number,
        requestBody: ManagerCustomerContactUpdatePayload,
    ): CancelablePromise<ManagerCustomerContactItemResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/customers/{customer_id}/contacts/{contact_id}',
            path: {
                'customer_id': customerId,
                'contact_id': contactId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Customer Contact History
     * Page field-change history for a current-tenant customer, including old/new values and
     * staff author, newest first. limit is at most 100. Missing customer returns 404; reading
     * does not add history entries or materialize a legacy contact.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param page
     * @param limit
     * @returns ManagerCustomerContactHistoryResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCustomerContactHistory(
        customerId: number,
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<ManagerCustomerContactHistoryResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/customers/{customer_id}/contact-history',
            path: {
                'customer_id': customerId,
            },
            query: {
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Product
     * Create a manual shared product, normalize specs and synchronize category, brand/series,
     * tags and manuals. Invalid title, references or publication media returns 400.
     * is_published defaults to true; creation is not implicitly a draft. POST has no
     * idempotency receipt and retries may create another card.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param requestBody
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static createManagerProduct(
        requestBody: ProductCreate,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/products',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Duplicate Product
     * Create a separate card from a source product with submitted overrides and optional
     * gallery/manual/tag copying. Publication is inherited unless overridden or
     * make_unpublished is set. Gallery copying reuses media URLs. Missing source returns 404;
     * invalid fields/media returns 400. Each successful POST creates a new card.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param productId
     * @param requestBody
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static duplicateManagerProduct(
        productId: number,
        requestBody: ProductDuplicatePayload,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/products/{product_id}/duplicate',
            path: {
                'product_id': productId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Product
     * Update submitted product fields; submitted specs are normalized and supplied
     * tags/manuals replace those relations. Brand/series and category are synchronized
     * according to explicit overrides and changed inputs. Missing product returns 404; invalid
     * fields/references/media returns 400. Writers lock the product to coordinate with bulk
     * apply; no expected_version or client idempotency receipt is accepted.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param productId
     * @param requestBody
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static updateProduct(
        productId: number,
        requestBody: ProductUpdate,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/products/{product_id}',
            path: {
                'product_id': productId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Product
     * Permanently delete a product and its removable catalog relations. References from orders
     * prevent deletion and return 400. Missing product returns 404, including after successful
     * deletion. This does not mean unpublishing the product.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param productId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteManagerProduct(
        productId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/products/{product_id}',
            path: {
                'product_id': productId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Product For Manager
     * Read a shared product editor card with its related catalog data, including unpublished
     * products. Missing product returns 404; this is not the tenant storefront projection.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param productId
     * @returns ManagerCatalogProductItemResponse Successful Response
     * @throws ApiError
     */
    public static getManagerProduct(
        productId: number,
    ): CancelablePromise<ManagerCatalogProductItemResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/products/{product_id}',
            path: {
                'product_id': productId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Bulk Round Price
     * Round each existing selected master-product price down to a multiple of 50 and return
     * the changed count. Missing IDs are ignored and an empty selection does nothing.
     * Repeating without intervening price changes makes no further changes; this does not edit
     * tenant offers.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ManagerBulkRoundPriceResponse Successful Response
     * @throws ApiError
     */
    public static bulkRoundPrice(
        requestBody: BulkRoundRequest,
    ): CancelablePromise<ManagerBulkRoundPriceResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/products/bulk-round-price',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Bulk Set Rrc Price
     * Set existing selected master-product prices to rounded current supplier-derived
     * recommended retail prices. Products without a positive RRC remain unchanged;
     * skipped_count also includes prices already equal to RRC. Missing IDs are ignored.
     * Repeats recalculate current supply metrics and do not edit tenant offers.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ManagerBulkSetRrcPriceResponse Successful Response
     * @throws ApiError
     */
    public static bulkSetRrcPrice(
        requestBody: BulkProductIdsRequest,
    ): CancelablePromise<ManagerBulkSetRrcPriceResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/products/bulk-set-rrc-price',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Bulk Delete Products
     * Permanently delete explicitly selected products one at a time and report per-product
     * failures. Order-linked products cannot be deleted; missing IDs are failures. Successful
     * deletions commit individually, so the batch may partially succeed. Empty selection does
     * nothing; repeating the batch reports previously deleted IDs as missing.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ManagerBulkDeleteProductsResponse Successful Response
     * @throws ApiError
     */
    public static bulkDeleteManagerProducts(
        requestBody: BulkProductIdsRequest,
    ): CancelablePromise<ManagerBulkDeleteProductsResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/products/bulk-delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get All Tags
     * Read all tags grouped by TagGroup for the shared product editor. No pagination
     * parameters are accepted; this does not restrict groups to the selected tenant.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns ManagerTagGroupResponse Successful Response
     * @throws ApiError
     */
    public static getAllTags(): CancelablePromise<Array<ManagerTagGroupResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tags/all',
        });
    }
    /**
     * Smart Search Products
     * Search the shared catalog for the product picker by text tokens and BTU-index numeric
     * tokens with AND-combined matching against titles, tags, area and cooling power.
     * Technical/brand/category filters refine results; limit is 1–100. This does not require
     * publication or tenant-offer eligibility.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param q Free-text search query, e.g. 'mdv loft 18'
     * @param limit
     * @param isInverter
     * @param areaMin
     * @param areaMax
     * @param heatingMin
     * @param hasWifi
     * @param hasFreshAir
     * @param brandSlugs Brand slugs to include
     * @param categorySlug Category tag slug: cat-household/cat-multi/cat-industrial
     * @returns ManagerCatalogProductListResponse Successful Response
     * @throws ApiError
     */
    public static smartSearchProducts(
        q: string,
        limit: number = 40,
        isInverter?: (boolean | null),
        areaMin?: (number | null),
        areaMax?: (number | null),
        heatingMin?: (number | null),
        hasWifi?: (boolean | null),
        hasFreshAir?: (boolean | null),
        brandSlugs?: (Array<string> | null),
        categorySlug?: (string | null),
    ): CancelablePromise<ManagerCatalogProductListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/products/smart-search',
            query: {
                'q': q,
                'limit': limit,
                'is_inverter': isInverter,
                'area_min': areaMin,
                'area_max': areaMax,
                'heating_min': heatingMin,
                'has_wifi': hasWifi,
                'has_fresh_air': hasFreshAir,
                'brand_slugs': brandSlugs,
                'category_slug': categorySlug,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Import From Onliner
     * Synchronously import product URLs using the importer, optionally following related
     * models and updating existing cards. Blank URLs are stripped; successes and per-product
     * errors are returned separately, so success of the HTTP call does not mean all products
     * imported. This writes catalog state and downloads media; repeated calls follow
     * update_existing and source matching rather than an idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param requestBody
     * @returns CatalogImportResultResponse Successful Response
     * @throws ApiError
     */
    public static importOnliner(
        requestBody: CatalogImportPayload,
    ): CancelablePromise<CatalogImportResultResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog/import-onliner',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Catalog Import
     * Synchronously import URLs from supported catalog sources, selecting the parser for each
     * URL. Optional related-model expansion and update_existing control writes. Blank URLs are
     * removed and partial successes/errors are returned. This downloads source content/media
     * and mutates cards; it is neither preview nor a background-job response.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param requestBody
     * @returns CatalogImportResultResponse Successful Response
     * @throws ApiError
     */
    public static catalogImport(
        requestBody: CatalogImportPayload,
    ): CancelablePromise<CatalogImportResultResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog/import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Catalog Import Job
     * Persist a new catalog import job and return 202 with its ID/status/stage for polling.
     * Blank URLs are removed; no remaining URL returns 400. The shared queue runs jobs in
     * order; accepted/queued does not mean import completed. Each POST creates a new job with
     * no idempotency receipt; results and partial failures are read from job status.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns CatalogImportJobStartResponse Successful Response
     * @throws ApiError
     */
    public static startCatalogImportJob(
        requestBody: CatalogImportPayload,
    ): CancelablePromise<CatalogImportJobStartResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog/import/jobs',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Current Catalog Import Job Status
     * Read the shared import queue’s current job: the running/queued job is preferred,
     * otherwise the latest recorded job. Returns progress and successes/errors without
     * starting work; 404 means no recorded job is available.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns CatalogImportJobStatusResponse Successful Response
     * @throws ApiError
     */
    public static getCurrentCatalogImportJobStatus(): CancelablePromise<CatalogImportJobStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/catalog/import/jobs/current',
        });
    }
    /**
     * Get Catalog Import Job Status
     * Read one persisted shared catalog import job by job_id with progress and results/errors.
     * Missing job returns 404; polling only reads state and does not retry failed imports.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param jobId
     * @returns CatalogImportJobStatusResponse Successful Response
     * @throws ApiError
     */
    public static getCatalogImportJobStatus(
        jobId: string,
    ): CancelablePromise<CatalogImportJobStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/catalog/import/jobs/{job_id}',
            path: {
                'job_id': jobId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Main Image Cleanup Batch
     * Synchronously create and process a review batch of at most 50 product main-image
     * candidates. Existing product/source pairs are skipped; unsupported
     * remote/missing/local-transparent sources receive skip reasons. Processing outcomes and
     * files are saved, but Product.main_image changes only on approval. Invalid processor
     * returns 400. This POST is not a read-only preview or queued worker job.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param requestBody
     * @returns ProductMainImageCleanupBatchCreateResponse Successful Response
     * @throws ApiError
     */
    public static createMainImageCleanupBatch(
        requestBody: ProductMainImageCleanupBatchCreatePayload,
    ): CancelablePromise<ProductMainImageCleanupBatchCreateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/main-image-cleanup/batches',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Main Image Cleanup Batches
     * Read saved main-image review batches with offset and limit 1–100. Completion of a batch
     * means candidate processing ended, not that candidates were approved or product main
     * images changed.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param limit
     * @param offset
     * @returns ProductMainImageCleanupBatchListResponse Successful Response
     * @throws ApiError
     */
    public static listMainImageCleanupBatches(
        limit: number = 20,
        offset?: number,
    ): CancelablePromise<ProductMainImageCleanupBatchListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/main-image-cleanup/batches',
            query: {
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Main Image Cleanup Items
     * Read saved cleanup candidates/outcomes filtered by batch and/or status, with offset and
     * limit 1–100. Unknown batch/status can yield an empty list; this does not process
     * candidates or approve their use.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param batchId
     * @param status
     * @param limit
     * @param offset
     * @returns ProductMainImageCleanupItemListResponse Successful Response
     * @throws ApiError
     */
    public static listMainImageCleanupItems(
        batchId?: (number | null),
        status?: (string | null),
        limit: number = 100,
        offset?: number,
    ): CancelablePromise<ProductMainImageCleanupItemListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/main-image-cleanup/items',
            query: {
                'batch_id': batchId,
                'status': status,
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Approve Main Image Cleanup Items
     * Approve ready candidates and immediately set each product main_image to its candidate
     * URL, recording approval and catalog invalidation together.
     * Missing/not-ready/already-approved items are skipped with reasons; an empty ID selection
     * returns 400. No original-image version check is performed, so approval can replace a
     * main image edited since candidate creation. Repeat approvals skip approved items.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param requestBody
     * @returns ProductMainImageCleanupDecisionResponse Successful Response
     * @throws ApiError
     */
    public static approveMainImageCleanupItems(
        requestBody: ProductMainImageCleanupApprovePayload,
    ): CancelablePromise<ProductMainImageCleanupDecisionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/main-image-cleanup/items/approve',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Reject Main Image Cleanup Items
     * Mark selected nonapproved cleanup items rejected with an operator reason.
     * Missing/already-approved items are skipped; empty ID selection returns 400. This saves
     * review state but does not change product fields or delete candidate files; repeating may
     * update the review timestamp/reason.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ProductMainImageCleanupDecisionResponse Successful Response
     * @throws ApiError
     */
    public static rejectMainImageCleanupItems(
        requestBody: ProductMainImageCleanupRejectPayload,
    ): CancelablePromise<ProductMainImageCleanupDecisionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/main-image-cleanup/items/reject',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Skip Main Image Cleanup Items
     * Mark selected nonapproved cleanup items skipped with an operator-visible reason.
     * Missing/already-approved items are reported as skipped; empty ID selection returns 400.
     * This changes review state without updating product main images or deleting media.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ProductMainImageCleanupDecisionResponse Successful Response
     * @throws ApiError
     */
    public static skipMainImageCleanupItems(
        requestBody: ProductMainImageCleanupSkipPayload,
    ): CancelablePromise<ProductMainImageCleanupDecisionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/main-image-cleanup/items/skip',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Main Image Cleanup Skip Reasons
     * Read known machine skip reasons and whether operator-entered reasons are supported. No
     * candidate processing or product change occurs.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns ProductMainImageCleanupSkipReasonsResponse Successful Response
     * @throws ApiError
     */
    public static listMainImageCleanupSkipReasons(): CancelablePromise<ProductMainImageCleanupSkipReasonsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/main-image-cleanup/skip-reasons',
        });
    }
    /**
     * Search Images
     * Search DuckDuckGo remotely for image metadata/URLs using q and max_results. Provider
     * failures degrade to an empty successful result. This POST only searches: it does not
     * download/store images or change gallery/main-image state. The current max_results
     * integer has no explicit route range; there is no pagination or guaranteed stable result
     * ordering.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param q Query string for image search
     * @param maxResults
     * @returns ManagerMediaImageSearchResultResponse Successful Response
     * @throws ApiError
     */
    public static searchImages(
        q: string,
        maxResults: number = 20,
    ): CancelablePromise<Array<ManagerMediaImageSearchResultResponse>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/search-images',
            query: {
                'q': q,
                'max_results': maxResults,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Image
     * Download a source image, decode/convert it to shared WebP storage and attach it to the
     * product. A non-installation upload also sets main_image; installation uploads do not.
     * Missing product returns 404; invalid source/image returns 400 and runtime storage
     * failure 500. Reusing identical canonical bytes/link does not create another link.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param url URL of the image to download
     * @param productId ID of the product to attach image to
     * @param isInstallation Is this an installation photo?
     * @returns ManagerMediaImageLinkResponse Successful Response
     * @throws ApiError
     */
    public static uploadImage(
        url: string,
        productId: number,
        isInstallation: boolean = false,
    ): CancelablePromise<ManagerMediaImageLinkResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/upload-image',
            query: {
                'url': url,
                'product_id': productId,
                'is_installation': isInstallation,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Local Images
     * Ingest local files into shared WebP product storage and attach successful files in one
     * catalog transaction. Invalid individual files may be skipped; uploaded/images report
     * accepted results. The first successful non-installation image becomes main only if it
     * was missing. Missing product returns 404; repeating identical canonical images can reuse
     * existing links.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param productId ID of the product
     * @param formData
     * @param isInstallation
     * @returns ManagerMediaUploadLocalImagesResponse Successful Response
     * @throws ApiError
     */
    public static uploadLocalImages(
        productId: number,
        formData: Body_upload_local_images,
        isInstallation: boolean = false,
    ): CancelablePromise<ManagerMediaUploadLocalImagesResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/upload-local-images',
            query: {
                'product_id': productId,
                'is_installation': isInstallation,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Reuse Search
     * Search shared product titles for image reuse and return up to 10 product
     * IDs/titles/main-image URLs. q must contain at least two characters; no page/limit
     * parameters are accepted. Reading results does not ingest or link an image.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param q
     * @returns ManagerMediaReuseSearchItemResponse Successful Response
     * @throws ApiError
     */
    public static reuseSearch(
        q: string,
    ): CancelablePromise<Array<ManagerMediaReuseSearchItemResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/gallery/reuse-search',
            query: {
                'q': q,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Common Gallery Images
     * Return non-installation URLs present in every selected product’s gallery. Empty
     * selection returns 400; a product with no matching gallery makes the intersection empty.
     * product_count reflects the submitted selection length. This only reads shared links.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param productIds Selected product IDs
     * @returns CommonGalleryImageResponse Successful Response
     * @throws ApiError
     */
    public static getCommonGalleryImages(
        productIds: Array<number>,
    ): CancelablePromise<Array<CommonGalleryImageResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/gallery/common-images',
            query: {
                'product_ids': productIds,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Image Variant Candidates
     * Read a bounded dry-run candidate set missing the requested variant; limit is 1–100 and
     * installation photos are excluded by default. Invalid variant returns 400. This route
     * uses missing-only selection and does not schedule processing or retry recorded failed
     * variants.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param variantType Variant to check: original, processed, card, full
     * @param limit
     * @param includeInstallation
     * @returns ProductImageVariantCandidatesResponse Successful Response
     * @throws ApiError
     */
    public static getImageVariantCandidates(
        variantType: string = 'card',
        limit: number = 100,
        includeInstallation: boolean = false,
    ): CancelablePromise<ProductImageVariantCandidatesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/gallery/variant-candidates',
            query: {
                'variant_type': variantType,
                'limit': limit,
                'include_installation': includeInstallation,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Link Search Result
     * Download/ingest a search-result image into shared managed product storage and attach its
     * gallery link. Does not set the main image. Missing product returns 404; invalid
     * source/media returns 400 and runtime processing conflict 409. Existing canonical
     * product/URL links are reused; this is a catalog write, not search.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param url URL of the image
     * @param productId ID of the product
     * @returns ManagerMediaImageLinkResponse Successful Response
     * @throws ApiError
     */
    public static linkSearchResult(
        url: string,
        productId: number,
    ): CancelablePromise<ManagerMediaImageLinkResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/link-search-result',
            query: {
                'url': url,
                'product_id': productId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Set Main Image
     * Set Product.main_image to a gallery image’s permitted publication URL. Missing
     * image/product and other ValueError validation failures are exposed as 404 by this route.
     * Repeating the same selection is a semantic no-op; this does not crop/process the image
     * or delete prior media.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param imageId ID of the ProductImage to set as main
     * @returns ManagerMediaSetMainImageResponse Successful Response
     * @throws ApiError
     */
    public static setMainImage(
        imageId: number,
    ): CancelablePromise<ManagerMediaSetMainImageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/set-main',
            query: {
                'image_id': imageId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Gallery Image
     * Delete one gallery database link and its variant rows, synchronize legacy product.images
     * and clear main_image if it points to that URL. Physical objects are retained for
     * deferred garbage collection. Missing link returns 404, including after successful
     * deletion.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param imageId
     * @returns ManagerMediaDeleteImageResponse Successful Response
     * @throws ApiError
     */
    public static deleteImage(
        imageId: number,
    ): CancelablePromise<ManagerMediaDeleteImageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/gallery/{image_id}',
            path: {
                'image_id': imageId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Crop Product Image
     * Crop a gallery source and append a new link or replace the selected link according to
     * mode. Replacement rebuilds original-variant metadata and follows an existing main-image
     * reference; set_main can select the result for non-installation images. Invalid/missing
     * source or crop returns 400. This writes media immediately, preserves installation
     * classification and has no idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param imageId
     * @param requestBody
     * @returns ManagerMediaImageLinkResponse Successful Response
     * @throws ApiError
     */
    public static cropProductImage(
        imageId: number,
        requestBody: ProductImageCropPayload,
    ): CancelablePromise<ManagerMediaImageLinkResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/{image_id}/crop',
            path: {
                'image_id': imageId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Replace Product Image Local
     * Replace one gallery link with browser-prepared image bytes and rebuild its original
     * variant without server crop work. Main image follows the replacement when it used the
     * old URL; installation classification is kept. Empty file, more than 25 MB, missing
     * image/product or invalid media returns 400. Physical old objects remain retained.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param imageId
     * @param formData
     * @returns ManagerMediaImageLinkResponse Successful Response
     * @throws ApiError
     */
    public static replaceProductImageLocal(
        imageId: number,
        formData: Body_replace_product_image_local,
    ): CancelablePromise<ManagerMediaImageLinkResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/{image_id}/replace-local',
            path: {
                'image_id': imageId,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Remove Product Image Background
     * Synchronously process a gallery image with the selected provider/model, replacing its
     * link by default; append creates/reuses a separate result link. Unknown mode falls back
     * to replace. Existing main-image references follow replacement and set_main is honored
     * for non-installation images. Invalid/missing source returns 400; provider/runtime
     * conflict returns 409. This is not a processing-job enqueue.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param imageId
     * @param provider Processing provider: auto, noop, manual, rembg, birefnet, ben
     * @param rembgModel Optional rembg model override
     * @param mode replace current ProductImage URL or append a new image
     * @param setMain
     * @returns ManagerMediaImageLinkResponse Successful Response
     * @throws ApiError
     */
    public static removeProductImageBackground(
        imageId: number,
        provider: string = 'auto',
        rembgModel?: (string | null),
        mode: string = 'replace',
        setMain: boolean = false,
    ): CancelablePromise<ManagerMediaImageLinkResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/{image_id}/remove-background',
            path: {
                'image_id': imageId,
            },
            query: {
                'provider': provider,
                'rembg_model': rembgModel,
                'mode': mode,
                'set_main': setMain,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Reuse Image
     * Canonicalize an image source URL, ingesting external sources when necessary, and link it
     * to the target product without changing its main image. A fully linked canonical URL is
     * reused; original-variant metadata may be repaired. ValueError failures, including
     * missing product, are exposed as 404 by this route.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param productId
     * @param sourceImageUrl
     * @returns ManagerMediaReuseImageResponse Successful Response
     * @throws ApiError
     */
    public static reuseImage(
        productId: number,
        sourceImageUrl: string,
    ): CancelablePromise<ManagerMediaReuseImageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/reuse-image',
            query: {
                'product_id': productId,
                'source_image_url': sourceImageUrl,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Bulk Add Gallery Images
     * Append canonicalized source URLs to all selected products without removing existing
     * gallery links. Existing links are reused; set_main selects the first URL only for
     * non-installation images. Missing products return 404; empty/invalid selections or
     * sources return 400. Database changes and catalog invalidation commit together; this may
     * ingest external sources.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param requestBody
     * @returns ManagerMediaBulkAddResponse Successful Response
     * @throws ApiError
     */
    public static bulkAddGalleryImages(
        requestBody: BulkGalleryAddRequest,
    ): CancelablePromise<ManagerMediaBulkAddResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/bulk-add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Bulk Upload Local Images
     * Upload local files once to shared managed storage and attach their URLs to every
     * selected product. product_ids_json must be a nonempty JSON array; missing products
     * return 404, invalid/empty selection/files return 400. set_main can select the first
     * uploaded URL for non-installation images. Attachments and catalog invalidation commit
     * together.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param formData
     * @returns ManagerMediaBulkUploadResponse Successful Response
     * @throws ApiError
     */
    public static bulkUploadLocalImages(
        formData: Body_bulk_upload_local_images,
    ): CancelablePromise<ManagerMediaBulkUploadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/bulk-upload-local',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Bulk Delete Common Gallery Images
     * Remove selected URLs only when they are common to all selected products under the
     * requested installation filter. Invalid/empty selection or URLs outside that intersection
     * returns 400. Deletes gallery/variant rows and clears affected main images, but retains
     * physical files. A repeat requires recalculating the common intersection.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param requestBody
     * @returns ManagerMediaBulkDeleteResponse Successful Response
     * @throws ApiError
     */
    public static bulkDeleteCommonGalleryImages(
        requestBody: BulkGalleryDeleteRequest,
    ): CancelablePromise<ManagerMediaBulkDeleteResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/bulk-delete-common',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Gallery To Series
     * Replace sibling products’ non-installation galleries and main images with the source
     * product’s gallery/main image, preserving installation photos; source URLs are also
     * merged into the series gallery. dry_run=true only reports effects, while the default
     * false commits them. Missing source returns 404; absent series/gallery returns 400.
     * delete_unreferenced=true always returns 409 because physical deletion is deferred.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param productId Source product ID
     * @param dryRun Preview changes without applying them
     * @param deleteUnreferenced Rejected with 409 because physical media cleanup is deferred
     * @returns ManagerMediaApplySeriesResponse Successful Response
     * @throws ApiError
     */
    public static applyGalleryToSeries(
        productId: number,
        dryRun: boolean = false,
        deleteUnreferenced: boolean = false,
    ): CancelablePromise<ManagerMediaApplySeriesResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/apply-to-series',
            query: {
                'product_id': productId,
                'dry_run': dryRun,
                'delete_unreferenced': deleteUnreferenced,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Process Missing Image Variants
     * Select up to 100 gallery images lacking a requested variant. dry_run defaults to true
     * and only reports candidates; false synchronously processes the bounded batch and saves
     * statuses/files with catalog invalidation. Installation photos are excluded by default;
     * default provider is noop. Invalid variant/provider returns 400. Inspect per-item
     * errors/statuses; an HTTP success can include processing failures.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param variantType Variant to process: processed, card, full
     * @param limit
     * @param includeInstallation
     * @param dryRun
     * @param provider Processing provider: auto, noop, manual, rembg, birefnet, ben
     * @param rembgModel Optional rembg model override
     * @returns ProductImageVariantBatchProcessResponse Successful Response
     * @throws ApiError
     */
    public static processMissingImageVariants(
        variantType: string = 'card',
        limit: number = 100,
        includeInstallation: boolean = false,
        dryRun: boolean = true,
        provider: string = 'noop',
        rembgModel?: (string | null),
    ): CancelablePromise<ProductImageVariantBatchProcessResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/variants/process-missing',
            query: {
                'variant_type': variantType,
                'limit': limit,
                'include_installation': includeInstallation,
                'dry_run': dryRun,
                'provider': provider,
                'rembg_model': rembgModel,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Reprocess Image Variant
     * Synchronously regenerate/retry one gallery image variant and return its saved processing
     * state. Missing image returns 404; invalid variant/provider returns 400. Source/provider
     * failures may be saved as failed and returned with HTTP success; installation catalog
     * variants may be skipped. This is a state change with no job/receipt; inspect
     * processing_status/processing_error before retrying.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param imageId
     * @param variantType Variant to reprocess: processed, card, full
     * @param provider Processing provider: auto, noop, manual, rembg, birefnet, ben
     * @param rembgModel Optional rembg model override
     * @returns ProductImageVariantResponse Successful Response
     * @throws ApiError
     */
    public static reprocessImageVariant(
        imageId: number,
        variantType: string = 'card',
        provider: string = 'noop',
        rembgModel?: (string | null),
    ): CancelablePromise<ProductImageVariantResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/gallery/{image_id}/variants/reprocess',
            path: {
                'image_id': imageId,
            },
            query: {
                'variant_type': variantType,
                'provider': provider,
                'rembg_model': rembgModel,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Cleanup Media
     * Report orphan candidates under local media/products only when dry_run=true. The default
     * dry_run=false returns 409 because physical garbage collection is disabled. deleted_count
     * and reclaimed_bytes describe potential deletions; no file is actually removed, and the
     * returned file list is capped at 50.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param dryRun
     * @returns ManagerMediaCleanupResponse Successful Response
     * @throws ApiError
     */
    public static cleanupMedia(
        dryRun: boolean = false,
    ): CancelablePromise<ManagerMediaCleanupResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/cleanup-media',
            query: {
                'dry_run': dryRun,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Mdv Catalog Import
     * Fetch official MDV exports and calculate a dry-run report, including prospective legacy
     * replacements when requested. No product is saved, deleted or archived. Catalog
     * identifiers and sample bounds are validated by the request/service; this may perform
     * remote reads without creating a queue job.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns MdvCatalogPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewMdvCatalogImport(
        requestBody: MdvCatalogPreviewPayload,
    ): CancelablePromise<MdvCatalogPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog/mdv/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Mdv Catalog Import Job
     * Start an official MDV refresh and return 202 with a shared import job ID. If
     * replace_legacy_catalogs is supplied, legacy cleanup commits BEFORE the job is enqueued:
     * unreferenced cards are deleted and order-linked cards are hidden/marked for update. This
     * is a destructive write, not preview; accepting the job does not guarantee eventual
     * import success. Repeating creates another job.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns CatalogImportJobStartResponse Successful Response
     * @throws ApiError
     */
    public static startMdvCatalogImportJob(
        requestBody: MdvCatalogImportPayload,
    ): CancelablePromise<CatalogImportJobStartResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog/mdv/import/jobs',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Bulk Update Specs
     * Merge, replace or delete spec keys on existing selected products, normalize the result
     * and synchronize brand/series plus catalog revisions. Replace replaces the full spec map;
     * deleting series aliases clears the series assignment when absent. Missing product IDs
     * are ignored. Wi-Fi edits replace related source/derived keys as a group; changes commit
     * together.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ManagerBulkSpecsResponse Successful Response
     * @throws ApiError
     */
    public static bulkUpdateSpecs(
        requestBody: BulkSpecUpdate,
    ): CancelablePromise<ManagerBulkSpecsResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/specs/bulk-update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Normalize Legacy Specs
     * Scan products with specs and convert legacy labels/values using the legacy migration
     * map. dry_run defaults to true and counts prospective changes without saving;
     * dry_run=false commits changed spec maps. Invalid legacy formats and per-product failures
     * are logged/skipped. This synchronous catalog-wide migration does not run the ordinary
     * normalized-spec/brand-series editor pipeline.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param dryRun Если True - не сохраняет изменения в БД, только показывает пример
     * @returns ManagerNormalizeLegacySpecsResponse Successful Response
     * @throws ApiError
     */
    public static normalizeLegacySpecs(
        dryRun: boolean = true,
    ): CancelablePromise<ManagerNormalizeLegacySpecsResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/specs/normalize-legacy',
            query: {
                'dry_run': dryRun,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Check Auth Status
     * Read the authenticated Manager identity, live tenant/storefront context and UI capabilities.
     * Includes password-change eligibility, mandatory-password-change and demo-read-only flags.
     * Does not issue or refresh a token. A valid authentication identity still needs Manager
     * access and tenant/storefront context; insufficient access returns 403. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns ManagerAuthStatusResponse Successful Response
     * @throws ApiError
     */
    public static readUserMe(): CancelablePromise<ManagerAuthStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/me',
        });
    }
    /**
     * Change Account Password
     * Change the current staff account password using its current password and record the
     * credential change. Requires Manager access and self-service password eligibility;
     * unavailable self-service returns 409 with detail.code=self_service_unavailable. Credential
     * validation failures return 400 with code/message. Success is 204, increments the account
     * auth version and clears the authentication cookie; sign in again. This command has no replay
     * receipt, and the old password cannot be reused for a retry.
     * @param requestBody
     * @returns void
     * @throws ApiError
     */
    public static changeManagerAccountPassword(
        requestBody: ManagerPasswordChangePayload,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/account/change-password',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Storefronts
     * List active storefronts belonging to the authenticated Manager's current tenant, including
     * display metadata and is_current/is_default markers. This read does not switch storefront or
     * issue credentials. The requested storefront is resolved within the same tenant by the
     * Manager authentication contract; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns ManagerStorefrontListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerStorefronts(): CancelablePromise<ManagerStorefrontListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/storefronts',
        });
    }
    /**
     * List Suppliers
     * List supplier profiles in the shared platform directory; this endpoint has no page/limit
     * parameters.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @returns SupplierListResponse Successful Response
     * @throws ApiError
     */
    public static listSuppliers(): CancelablePromise<SupplierListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/suppliers',
        });
    }
    /**
     * Create Supplier
     * Create a supplier profile, normalizing its code and optional Google spreadsheet
     * reference. This does not create a partner account or fetch its offers. Invalid
     * configuration returns 400; POST has no client idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestBody
     * @returns SupplierResponse Successful Response
     * @throws ApiError
     */
    public static createSupplier(
        requestBody: SupplierCreatePayload,
    ): CancelablePromise<SupplierResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/suppliers',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Supplier
     * Update only submitted supplier profile fields and normalize code/spreadsheet changes.
     * Missing supplier returns 404; invalid configuration returns 400.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @param requestBody
     * @returns SupplierResponse Successful Response
     * @throws ApiError
     */
    public static patchSupplier(
        supplierId: number,
        requestBody: SupplierUpdatePayload,
    ): CancelablePromise<SupplierResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/suppliers/{supplier_id}',
            path: {
                'supplier_id': supplierId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Supplier
     * Delete a shared supplier and its supply requests/lines, contacts, warehouses, mappings,
     * offers, sync runs and price sources. Missing supplier returns 404, including a repeat
     * after successful deletion. This removes the supplier’s related platform data, not just
     * its profile.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteSupplier(
        supplierId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/suppliers/{supplier_id}',
            path: {
                'supplier_id': supplierId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Supplier Contacts
     * List contacts belonging to one supplier. Missing supplier returns 404.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @returns SupplierContactListResponse Successful Response
     * @throws ApiError
     */
    public static listSupplierContacts(
        supplierId: number,
    ): CancelablePromise<SupplierContactListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/suppliers/{supplier_id}/contacts',
            path: {
                'supplier_id': supplierId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Supplier Contact
     * Create a contact under the selected supplier. Invalid supplier/contact configuration
     * returns 400; no client idempotency receipt is provided.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @param requestBody
     * @returns SupplierContactResponse Successful Response
     * @throws ApiError
     */
    public static createSupplierContact(
        supplierId: number,
        requestBody: SupplierContactCreatePayload,
    ): CancelablePromise<SupplierContactResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/suppliers/{supplier_id}/contacts',
            path: {
                'supplier_id': supplierId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Supplier Contact
     * Patch submitted contact fields under the specified supplier. A contact outside that
     * supplier or missing contact returns 404; invalid values return 400.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @param contactId
     * @param requestBody
     * @returns SupplierContactResponse Successful Response
     * @throws ApiError
     */
    public static patchSupplierContact(
        supplierId: number,
        contactId: number,
        requestBody: SupplierContactUpdatePayload,
    ): CancelablePromise<SupplierContactResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/suppliers/{supplier_id}/contacts/{contact_id}',
            path: {
                'supplier_id': supplierId,
                'contact_id': contactId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Supplier Contact
     * Delete a contact under the specified supplier. Missing contact or wrong supplier returns
     * 404, including a repeat after successful deletion.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @param contactId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteSupplierContact(
        supplierId: number,
        contactId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/suppliers/{supplier_id}/contacts/{contact_id}',
            path: {
                'supplier_id': supplierId,
                'contact_id': contactId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Supplier Warehouses
     * List warehouse profiles belonging to a supplier. Missing supplier returns 404.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @returns SupplierWarehouseListResponse Successful Response
     * @throws ApiError
     */
    public static listSupplierWarehouses(
        supplierId: number,
    ): CancelablePromise<SupplierWarehouseListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/suppliers/{supplier_id}/warehouses',
            path: {
                'supplier_id': supplierId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Supplier Warehouse
     * Create a warehouse profile under a supplier. Invalid supplier/warehouse configuration
     * returns 400; no client idempotency receipt is provided.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @param requestBody
     * @returns SupplierWarehouseResponse Successful Response
     * @throws ApiError
     */
    public static createSupplierWarehouse(
        supplierId: number,
        requestBody: SupplierWarehouseCreatePayload,
    ): CancelablePromise<SupplierWarehouseResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/suppliers/{supplier_id}/warehouses',
            path: {
                'supplier_id': supplierId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Supplier Warehouse
     * Patch submitted warehouse fields under its supplier. Missing warehouse or wrong supplier
     * returns 404; invalid values return 400.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @param warehouseId
     * @param requestBody
     * @returns SupplierWarehouseResponse Successful Response
     * @throws ApiError
     */
    public static patchSupplierWarehouse(
        supplierId: number,
        warehouseId: number,
        requestBody: SupplierWarehouseUpdatePayload,
    ): CancelablePromise<SupplierWarehouseResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/suppliers/{supplier_id}/warehouses/{warehouse_id}',
            path: {
                'supplier_id': supplierId,
                'warehouse_id': warehouseId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Supplier Warehouse
     * Delete a warehouse under its supplier. Missing warehouse or wrong supplier returns 404,
     * including a repeat after deletion.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @param warehouseId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteSupplierWarehouse(
        supplierId: number,
        warehouseId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/suppliers/{supplier_id}/warehouses/{warehouse_id}',
            path: {
                'supplier_id': supplierId,
                'warehouse_id': warehouseId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Supplier Sheets
     * Read Google spreadsheet tab metadata from the selected supplier’s configured
     * spreadsheet. Missing supplier/spreadsheet configuration or upstream read failure returns
     * 400; this is an external read, not an offer sync.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param supplierId
     * @returns SupplierSheetTabListResponse Successful Response
     * @throws ApiError
     */
    public static listSupplierSheets(
        supplierId: number,
    ): CancelablePromise<SupplierSheetTabListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/suppliers/{supplier_id}/sheets',
            path: {
                'supplier_id': supplierId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Supplier Sources
     * List shared supplier price-source configurations, including supplier names. This
     * endpoint does not paginate or sync source contents.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @returns SupplierPriceSourceListResponse Successful Response
     * @throws ApiError
     */
    public static listSupplierSources(): CancelablePromise<SupplierPriceSourceListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/supplier-sources',
        });
    }
    /**
     * Create Supplier Source
     * Create a price-source configuration after verifying the supplier spreadsheet and sheet
     * tab. A missing supplier, unconfigured spreadsheet or invalid sheet returns 400. Saving
     * does not perform an offer sync.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestBody
     * @returns SupplierPriceSourceResponse Successful Response
     * @throws ApiError
     */
    public static createSupplierSource(
        requestBody: SupplierPriceSourceCreatePayload,
    ): CancelablePromise<SupplierPriceSourceResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supplier-sources',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Supplier Source
     * Patch submitted source configuration fields; supplier/sheet changes are checked against
     * available tabs. Missing source returns 404; invalid configuration returns 400. Saving
     * does not perform an offer sync.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param sourceId
     * @param requestBody
     * @returns SupplierPriceSourceResponse Successful Response
     * @throws ApiError
     */
    public static patchSupplierSource(
        sourceId: number,
        requestBody: SupplierPriceSourceUpdatePayload,
    ): CancelablePromise<SupplierPriceSourceResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/supplier-sources/{source_id}',
            path: {
                'source_id': sourceId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Supplier Source
     * Delete a source and deactivate its offers and corresponding mappings. Missing source
     * returns 404, including a repeat after deletion; deleting is not merely hiding its
     * configuration.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param sourceId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteSupplierSource(
        sourceId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/supplier-sources/{source_id}',
            path: {
                'source_id': sourceId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Analyze Supplier Source
     * Read source spreadsheet rows and analyze their column mapping without importing offers.
     * This existing endpoint accepts limit 1–200 (default 50). Missing source or missing
     * spreadsheet configuration raises 404; other read/analysis failures return 400.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param sourceId
     * @param limit
     * @returns SupplierSourceAnalysisResponse Successful Response
     * @throws ApiError
     */
    public static analyzeSupplierSource(
        sourceId: number,
        limit: number = 50,
    ): CancelablePromise<SupplierSourceAnalysisResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/supplier-sources/{source_id}/analysis',
            path: {
                'source_id': sourceId,
            },
            query: {
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Sync Supplier Source
     * Run source synchronization now and return its recorded run result. Sync updates supplier
     * offers and can deactivate offers missing from the source. Inspect run status/error even
     * on HTTP success; source-processing failures can be captured in the run. Unknown source
     * returns 404; adapter exceptions can return 400. A repeat starts another run, not a
     * receipt replay.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param sourceId
     * @returns SupplierSyncRunResponse Successful Response
     * @throws ApiError
     */
    public static syncSupplierSource(
        sourceId: number,
    ): CancelablePromise<SupplierSyncRunResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supplier-sources/{source_id}/sync',
            path: {
                'source_id': sourceId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Sync All Supplier Sources
     * Synchronize active configured sources and return run results. Inspect each run
     * status/error; a repeat runs synchronization again. Unhandled orchestration failure
     * returns 400.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @returns SupplierSyncRunResponse Successful Response
     * @throws ApiError
     */
    public static syncAllSupplierSources(): CancelablePromise<Array<SupplierSyncRunResponse>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supplier-sources/sync-all',
        });
    }
    /**
     * List Unmapped Supplier Offers
     * Page active offers without an active product mapping, optionally filtered by supplier,
     * source and query. limit is 1–100; meta describes the filtered set.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param page
     * @param limit
     * @param supplierId
     * @param sourceId
     * @param q
     * @returns SupplierOfferListResponse Successful Response
     * @throws ApiError
     */
    public static listUnmappedSupplierOffers(
        page: number = 1,
        limit: number = 50,
        supplierId?: (number | null),
        sourceId?: (number | null),
        q?: (string | null),
    ): CancelablePromise<SupplierOfferListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/supplier-offers/unmapped',
            query: {
                'page': page,
                'limit': limit,
                'supplier_id': supplierId,
                'source_id': sourceId,
                'q': q,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Supplier Source Url Import Candidates
     * Find active unmapped offers with a source URL not already represented by a product.
     * Normalized URLs are deduplicated. This existing endpoint accepts limit 1–200, default
     * 100; total is the returned candidate count, not an exhaustive paginated total.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param limit
     * @param supplierId
     * @param sourceId
     * @returns SupplierSourceUrlImportCandidateListResponse Successful Response
     * @throws ApiError
     */
    public static listSupplierSourceUrlImportCandidates(
        limit: number = 100,
        supplierId?: (number | null),
        sourceId?: (number | null),
    ): CancelablePromise<SupplierSourceUrlImportCandidateListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/supplier-offers/source-url-import-candidates',
            query: {
                'limit': limit,
                'supplier_id': supplierId,
                'source_id': sourceId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Supplier Source Url Import
     * Start a catalog import job from trimmed, deduplicated URLs and return its job
     * ID/status/stage. Empty URLs return 400. It starts a job rather than waiting for all
     * products; this is not a supplier push endpoint.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestBody
     * @returns CatalogImportJobStartResponse Successful Response
     * @throws ApiError
     */
    public static startSupplierSourceUrlImport(
        requestBody: SupplierSourceUrlImportPayload,
    ): CancelablePromise<CatalogImportJobStartResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supplier-offers/source-url-import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Suggest Supplier Offers
     * Return product match suggestions for submitted supplier-offer identifiers. Suggestions
     * do not create or replace mappings; the per-offer bound is supplied in the request model.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestBody
     * @returns SupplierOfferSuggestionsResponse Successful Response
     * @throws ApiError
     */
    public static suggestSupplierOffers(
        requestBody: SupplierOfferSuggestionsPayload,
    ): CancelablePromise<SupplierOfferSuggestionsResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supplier-offers/suggestions',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Supplier Mapping
     * Create an active product mapping for a supplier/external_id offer key, recording the
     * current Manager actor. Missing product/offer, inactive offer or an already-mapped key
     * returns 400. A repeated POST is not an idempotent replay.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestBody
     * @returns SupplierMappingResponse Successful Response
     * @throws ApiError
     */
    public static createSupplierMapping(
        requestBody: SupplierMappingCreatePayload,
    ): CancelablePromise<SupplierMappingResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supplier-mappings',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Supplier Mappings Bulk
     * Create product mappings item by item. With skip_conflicts=true, skipped items and their
     * errors are returned beside counts. This is not atomic: earlier created mappings may
     * remain when a later item fails; inspect the result before retrying a batch.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestBody
     * @returns SupplierMappingBulkCreateResponse Successful Response
     * @throws ApiError
     */
    public static bulkCreateSupplierMappings(
        requestBody: SupplierMappingBulkCreatePayload,
    ): CancelablePromise<SupplierMappingBulkCreateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supplier-mappings/bulk',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Supplier Mapping
     * Delete a supplier-to-product mapping. Missing mapping returns 404, including a repeat
     * after successful deletion.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param mappingId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteSupplierMapping(
        mappingId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/supplier-mappings/{mapping_id}',
            path: {
                'mapping_id': mappingId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Product Supplier Offers
     * Read supplier offers linked by active mappings to the selected shared product, including
     * inactive offers. Returns an empty list when no linked offers exist; it does not
     * separately validate product existence. This is platform purchase information, not a
     * public storefront price list.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param productId
     * @returns SupplierOfferListResponse Successful Response
     * @throws ApiError
     */
    public static getProductSupplierOffers(
        productId: number,
    ): CancelablePromise<SupplierOfferListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/products/{product_id}/supplier-offers',
            path: {
                'product_id': productId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upsert Product Local Stock
     * Set the selected product’s local Vitebsk stock quantity and record the actor. Missing
     * product returns 404. This sets an absolute quantity rather than incrementing stock.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param productId
     * @param requestBody
     * @returns ProductLocalStockResponse Successful Response
     * @throws ApiError
     */
    public static upsertProductLocalStock(
        productId: number,
        requestBody: ProductLocalStockPayload,
    ): CancelablePromise<ProductLocalStockResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/products/{product_id}/local-stock',
            path: {
                'product_id': productId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Supply Requests
     * Page supply requests filtered by status, supplier, warehouse, source type or order.
     * limit is 1–100; invalid business filters return 400.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param page
     * @param limit
     * @param status
     * @param supplierId
     * @param warehouseId
     * @param sourceType
     * @param orderId
     * @returns SupplyRequestListResponse Successful Response
     * @throws ApiError
     */
    public static listSupplyRequests(
        page: number = 1,
        limit: number = 50,
        status?: (string | null),
        supplierId?: (number | null),
        warehouseId?: (number | null),
        sourceType?: (string | null),
        orderId?: (number | null),
    ): CancelablePromise<SupplyRequestListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/supply-requests',
            query: {
                'page': page,
                'limit': limit,
                'status': status,
                'supplier_id': supplierId,
                'warehouse_id': warehouseId,
                'source_type': sourceType,
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Supply Request
     * Create a supply request from explicit lines and supplier/warehouse context. Invalid
     * combinations return 400. No Idempotency-Key receipt is provided; reconcile creation
     * before repeating a lost response.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestBody
     * @returns SupplyRequestCreateResponse Successful Response
     * @throws ApiError
     */
    public static createSupplyRequest(
        requestBody: SupplyRequestCreatePayload,
    ): CancelablePromise<SupplyRequestCreateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supply-requests',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Supply Request From Order Lines
     * Create supply requests from selected order lines, checking the order in the
     * authenticated Manager scope. Invalid or unavailable selections return 400; resulting
     * supply records remain platform-managed.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestBody
     * @returns SupplyRequestCreateResponse Successful Response
     * @throws ApiError
     */
    public static createSupplyRequestFromOrderLines(
        requestBody: SupplyRequestFromOrderLinesPayload,
    ): CancelablePromise<SupplyRequestCreateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supply-requests/from-order-lines',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Stock Supply Request
     * Create stock replenishment supply requests from submitted items. Invalid
     * supplier/product/warehouse context returns 400; no client idempotency receipt is
     * provided.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestBody
     * @returns SupplyRequestCreateResponse Successful Response
     * @throws ApiError
     */
    public static createStockSupplyRequest(
        requestBody: SupplyRequestStockCreatePayload,
    ): CancelablePromise<SupplyRequestCreateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supply-requests/stock',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Supply Request
     * Patch submitted supply-request fields, validating its state and business relationships.
     * Service validation failures, including missing request, return 400.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestId
     * @param requestBody
     * @returns SupplyRequestResponse Successful Response
     * @throws ApiError
     */
    public static patchSupplyRequest(
        requestId: number,
        requestBody: SupplyRequestUpdatePayload,
    ): CancelablePromise<SupplyRequestResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/supply-requests/{request_id}',
            path: {
                'request_id': requestId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Supply Request Line
     * Patch submitted fields of a supply-request line and validate its request context.
     * Service validation failures, including missing line, return 400.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param lineId
     * @param requestBody
     * @returns SupplyRequestResponse Successful Response
     * @throws ApiError
     */
    public static patchSupplyRequestLine(
        lineId: number,
        requestBody: SupplyRequestLineUpdatePayload,
    ): CancelablePromise<SupplyRequestResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/supply-requests/lines/{line_id}',
            path: {
                'line_id': lineId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Generate Supply Request Supplier Message
     * Generate supplier message text for a supply request. mark_sent records a snapshot/time
     * and advances the request/active lines to awaiting_reply (reserve) or ordered; this
     * handler returns text and does not send it to the supplier. Invalid request/state returns
     * 400.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestId
     * @param requestBody
     * @returns SupplyMessageResponse Successful Response
     * @throws ApiError
     */
    public static generateSupplyRequestSupplierMessage(
        requestId: number,
        requestBody: SupplyRequestMessagePayload,
    ): CancelablePromise<SupplyMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supply-requests/{request_id}/message/supplier',
            path: {
                'request_id': requestId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Generate Supply Logistics Message
     * Generate logistics message text for selected supply requests. mark_sent records a
     * snapshot/time and can advance ordered/awaiting_reply/reserved requests and active lines
     * to ready_for_pickup; this handler does not deliver the message. Invalid selection/state
     * returns 400.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param requestBody
     * @returns SupplyMessageResponse Successful Response
     * @throws ApiError
     */
    public static generateSupplyLogisticsMessage(
        requestBody: SupplyLogisticsMessagePayload,
    ): CancelablePromise<SupplyMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/supply-requests/message/logistics',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Product Supplier Offer Candidates
     * Page offer candidates for a product within the required supplier and optional
     * source/query. Defaults to active offers; include_inactive includes inactive candidates.
     * Each row reports free/current/conflict/inactive mapping status. limit is 1–100. Missing
     * product returns 404.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param productId
     * @param supplierId
     * @param sourceId
     * @param q
     * @param page
     * @param limit
     * @param includeInactive
     * @returns SupplierOfferCandidateListResponse Successful Response
     * @throws ApiError
     */
    public static listProductSupplierOfferCandidates(
        productId: number,
        supplierId: number,
        sourceId?: (number | null),
        q?: (string | null),
        page: number = 1,
        limit: number = 50,
        includeInactive: boolean = false,
    ): CancelablePromise<SupplierOfferCandidateListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/products/{product_id}/supplier-offer-candidates',
            path: {
                'product_id': productId,
            },
            query: {
                'supplier_id': supplierId,
                'source_id': sourceId,
                'q': q,
                'page': page,
                'limit': limit,
                'include_inactive': includeInactive,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Put Supplier Offer Mapping
     * Map an active offer to a product. Replacing another active mapping requires
     * replace_existing plus both expected_mapping_id and expected_product_id; concurrent
     * changes or a conflicting mapping return 409. Read candidates again before resolving a
     * conflict. Mapping to the already-current product returns the existing mapping. Missing
     * offer/product returns 404; inactive offer returns 400. This does not accept a generic
     * Idempotency-Key.
     *
     * Access and scope: system-tenant Manager access is required; these are platform-global
     * supplier/supply records, not a supplier self-service API. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager)
     * and [supplier
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/api/supplier-integration-boundary.md).
     * @param offerId
     * @param requestBody
     * @returns SupplierOfferMappingResponse Successful Response
     * @throws ApiError
     */
    public static putSupplierOfferMapping(
        offerId: number,
        requestBody: SupplierOfferMappingPutPayload,
    ): CancelablePromise<SupplierOfferMappingResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/supplier-offers/{offer_id}/mapping',
            path: {
                'offer_id': offerId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
