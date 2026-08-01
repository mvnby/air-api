/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_bulk_upload_local_images } from '../models/Body_bulk_upload_local_images';
import type { Body_recognize_manager_customer_requisites } from '../models/Body_recognize_manager_customer_requisites';
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
import type { ManagerCustomerDocumentListResponse } from '../models/ManagerCustomerDocumentListResponse';
import type { ManagerCustomerReconciliationDocumentResponse } from '../models/ManagerCustomerReconciliationDocumentResponse';
import type { ManagerCustomerReconciliationResponse } from '../models/ManagerCustomerReconciliationResponse';
import type { ManagerCustomerUpdatePayload } from '../models/ManagerCustomerUpdatePayload';
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
import type { SupplierOfferListResponse } from '../models/SupplierOfferListResponse';
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
     * Paginated product list for manager UI.
     * Unlike the public catalog, this can show unpublished products.
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
     * Paginated customer list for manager UI.
     * Includes order count per customer.
     * @param page
     * @param limit
     * @param search
     * @param type
     * @param onlyWithOrders
     * @returns ManagerCatalogCustomerListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCustomers(
        page: number = 1,
        limit: number = 20,
        search?: (string | null),
        type?: (string | null),
        onlyWithOrders: boolean = true,
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
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Recognize Customer Requisites For Manager
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
     * Confirm Customer Requisites For Manager
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
     * @param customerId
     * @param dateFrom
     * @param dateTo
     * @returns ManagerCustomerReconciliationResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCustomerReconciliation(
        customerId: number,
        dateFrom?: (string | null),
        dateTo?: (string | null),
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
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Customer Reconciliation Document For Manager
     * @param customerId
     * @param dateFrom
     * @param dateTo
     * @returns ManagerCustomerReconciliationDocumentResponse Successful Response
     * @throws ApiError
     */
    public static createManagerCustomerReconciliationDocument(
        customerId: number,
        dateFrom?: (string | null),
        dateTo?: (string | null),
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
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Customer Branches For Manager
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
     * Create Product
     * Create a manual product card from the manager UI.
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
     * Duplicate a product card, optionally overriding selected fields.
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
     * Update individual product fields.
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
     * Round prices down to the nearest multiple of 50.
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
     * Set selected product prices to their current recommended retail prices.
     * Products without RRC stay unchanged.
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
     * Delete explicitly selected products. Products linked to orders are reported as failed.
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
     * Return all tags grouped by TagGroup for the product editor.
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
     * Smart search for manager product picker.
     *
     * Parses the query string into text tokens and BTU-index number tokens,
     * then applies AND-chained ORM filters against title, tags, area, and
     * power_cooling.  Returns matched products with their tags pre-loaded.
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
     * Import products from Onliner.by URLs.
     * Accepts a list of product page URLs and an optional flag to also import
     * related models (sibling AC units linked on the same page).
     * Returns the count of successfully imported and failed products.
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
     * Universal product import endpoint.
     * Accepts URLs from any supported source (onliner.by, aircond.by, etc.).
     * ImporterService automatically routes each URL to the appropriate parser.
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
     * Start a universal catalog import in the background and return a job id
     * that can be polled for progress.
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
     * Create a bounded batch of product main-image cleanup candidates.
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
     * List cleanup batches for manager review.
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
     * List cleanup items by batch and/or status.
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
     * Approve selected candidates and explicitly update Product.main_image.
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
     * Reject selected candidates without changing public product fields.
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
     * Mark selected items skipped with an operator-visible reason.
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
     * Return known machine reasons plus user-entered skip reasons support.
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
     * Search for images using DuckDuckGo.
     * Returns a list of image objects: {image, width, height, ...}
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
     * Download image from URL, convert to WebP, save to local storage,
     * and create a ProductImage record linked to the product.
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
     * Upload multiple local files, convert to WebP, and attach to product.
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
     * Search for products to reuse images from.
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
     * Return non-installation images shared by all selected products.
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
     * Dry-run candidate selection for images missing a requested variant.
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
     * Add a search result image to gallery (download and link). Does NOT set as main image.
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
     * Set a specific gallery image as the product's main image.
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
     * Delete an image link; physical file is deleted only if unreferenced globally.
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
     * Crop a concrete ProductImage and either append or replace the gallery image.
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
     * Remove Product Image Background
     * Remove background from a ProductImage and replace it by default.
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
     * Link an existing image URL to another product.
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
     * Append image links to selected products without removing existing gallery items.
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
     * Upload local files once and attach to all selected products.
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
     * Delete selected common image links from selected products only.
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
     * Replace sibling products' non-installation galleries with this product's gallery.
     * @param productId Source product ID
     * @param dryRun Preview changes without applying them
     * @param deleteUnreferenced Delete physical files that become unreferenced
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
     * Dry-run or explicitly process a bounded batch of missing image variants.
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
     * Retry/reprocess a failed or skipped image variant.
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
     * Delete orphaned media files not referenced in DB.
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
     * Build a dry-run report for official MDV exports before writing products.
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
     * Start an official MDV catalog refresh in the existing background queue.
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
     * Массовое добавление или обновление характеристик.
     * Идеально для установки диаметров труб для целой серии кондиционеров сразу.
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
     * Массовая миграция характеристик.
     * Переводит ключи Onliner (кириллица) в System (английский).
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
     * Check if current user is authenticated.
     * Returns username if valid, 401 otherwise (via Depends).
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
     * List Manager Storefronts
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
     * @param page
     * @param limit
     * @param supplierId
     * @param sourceId
     * @returns SupplierOfferListResponse Successful Response
     * @throws ApiError
     */
    public static listUnmappedSupplierOffers(
        page: number = 1,
        limit: number = 50,
        supplierId?: (number | null),
        sourceId?: (number | null),
    ): CancelablePromise<SupplierOfferListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/supplier-offers/unmapped',
            query: {
                'page': page,
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
     * List Supplier Source Url Import Candidates
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
}
