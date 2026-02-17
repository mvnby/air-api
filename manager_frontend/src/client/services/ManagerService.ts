/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_bulk_upload_local_images } from '../models/Body_bulk_upload_local_images';
import type { Body_upload_local_images } from '../models/Body_upload_local_images';
import type { BulkGalleryAddRequest } from '../models/BulkGalleryAddRequest';
import type { BulkGalleryDeleteRequest } from '../models/BulkGalleryDeleteRequest';
import type { BulkRoundRequest } from '../models/BulkRoundRequest';
import type { BulkSpecUpdate } from '../models/BulkSpecUpdate';
import type { CommonGalleryImageResponse } from '../models/CommonGalleryImageResponse';
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerAuthStatusResponse } from '../models/ManagerAuthStatusResponse';
import type { ManagerBulkRoundPriceResponse } from '../models/ManagerBulkRoundPriceResponse';
import type { ManagerBulkSpecsResponse } from '../models/ManagerBulkSpecsResponse';
import type { ManagerCatalogCustomerListResponse } from '../models/ManagerCatalogCustomerListResponse';
import type { ManagerCatalogProductListResponse } from '../models/ManagerCatalogProductListResponse';
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
import type { ManagerTagGroupResponse } from '../models/ManagerTagGroupResponse';
import type { ProductUpdate } from '../models/ProductUpdate';
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
        sort: string = 'newest',
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
}
