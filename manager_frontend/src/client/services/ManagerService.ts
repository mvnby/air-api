/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_local_images_api_manager_upload_local_images_post } from '../models/Body_upload_local_images_api_manager_upload_local_images_post';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerService {
    /**
     * Check Auth Status
     * Check if current user is authenticated.
     * Returns username if valid, 401 otherwise (via Depends).
     * @returns any Successful Response
     * @throws ApiError
     */
    public static checkAuthStatusApiManagerMeGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/me',
        });
    }
    /**
     * Search Images
     * Search for images using DuckDuckGo.
     * Returns a list of image objects: {image, width, height, ...}
     * @param q Query string for image search
     * @param maxResults
     * @returns any Successful Response
     * @throws ApiError
     */
    public static searchImagesApiManagerSearchImagesPost(
        q: string,
        maxResults: number = 20,
    ): CancelablePromise<Array<Record<string, any>>> {
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
     * @returns any Successful Response
     * @throws ApiError
     */
    public static uploadImageApiManagerUploadImagePost(
        url: string,
        productId: number,
        isInstallation: boolean = false,
    ): CancelablePromise<any> {
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
     * @returns any Successful Response
     * @throws ApiError
     */
    public static uploadLocalImagesApiManagerUploadLocalImagesPost(
        productId: number,
        formData: Body_upload_local_images_api_manager_upload_local_images_post,
        isInstallation: boolean = false,
    ): CancelablePromise<any> {
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
     * Link Search Result
     * Add a search result image to gallery (download and link). Does NOT set as main image.
     * @param url URL of the image
     * @param productId ID of the product
     * @returns any Successful Response
     * @throws ApiError
     */
    public static linkSearchResultApiManagerGalleryLinkSearchResultPost(
        url: string,
        productId: number,
    ): CancelablePromise<any> {
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
     * @returns any Successful Response
     * @throws ApiError
     */
    public static setMainImageApiManagerGallerySetMainPost(
        imageId: number,
    ): CancelablePromise<any> {
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
     * Delete an image from the gallery (and disk).
     * @param imageId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteGalleryImageApiManagerGalleryImageIdDelete(
        imageId: number,
    ): CancelablePromise<any> {
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
     * Reuse Search
     * Search for products to reuse images from.
     * @param q
     * @returns any Successful Response
     * @throws ApiError
     */
    public static reuseSearchApiManagerGalleryReuseSearchGet(
        q: string,
    ): CancelablePromise<any> {
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
     * Reuse Image
     * Link an existing image URL to another product.
     * @param productId
     * @param sourceImageUrl
     * @returns any Successful Response
     * @throws ApiError
     */
    public static reuseImageApiManagerGalleryReuseImagePost(
        productId: number,
        sourceImageUrl: string,
    ): CancelablePromise<any> {
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
     * Cleanup Media
     * Delete orphaned media files not referenced in DB.
     * @param dryRun
     * @returns any Successful Response
     * @throws ApiError
     */
    public static cleanupMediaApiManagerCleanupMediaPost(
        dryRun: boolean = false,
    ): CancelablePromise<any> {
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
}
