/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_media_assets } from '../models/Body_upload_media_assets';
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerBackgroundRemovalConfigResponse } from '../models/ManagerBackgroundRemovalConfigResponse';
import type { ManagerMediaAssetCropPayload } from '../models/ManagerMediaAssetCropPayload';
import type { ManagerMediaAssetListResponse } from '../models/ManagerMediaAssetListResponse';
import type { ManagerMediaAssetResponse } from '../models/ManagerMediaAssetResponse';
import type { ManagerMediaAssetUpdatePayload } from '../models/ManagerMediaAssetUpdatePayload';
import type { ManagerMediaAssetUploadResponse } from '../models/ManagerMediaAssetUploadResponse';
import type { ManagerMediaAssetUrlUploadPayload } from '../models/ManagerMediaAssetUrlUploadPayload';
import type { ManagerMediaBackfillReferencedAssetsResponse } from '../models/ManagerMediaBackfillReferencedAssetsResponse';
import type { ManagerMediaProcessingJobCreatePayload } from '../models/ManagerMediaProcessingJobCreatePayload';
import type { ManagerMediaProcessingJobListResponse } from '../models/ManagerMediaProcessingJobListResponse';
import type { ManagerMediaProcessingJobResponse } from '../models/ManagerMediaProcessingJobResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerMediaService {
    /**
     * List Media Assets
     * Read the platform media library with title/text, kind, tag and status filters, ordered
     * newest first. page starts at 1 and limit is 1–100; usage_count describes known URL
     * references. This system route lists platform-wide assets, including scoped assets,
     * rather than filtering by selected storefront.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param page
     * @param limit
     * @param q
     * @param kind
     * @param tag
     * @param status
     * @returns ManagerMediaAssetListResponse Successful Response
     * @throws ApiError
     */
    public static listMediaAssets(
        page: number = 1,
        limit: number = 40,
        q?: (string | null),
        kind?: (string | null),
        tag?: (string | null),
        status?: (string | null),
    ): CancelablePromise<ManagerMediaAssetListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/media/assets',
            query: {
                'page': page,
                'limit': limit,
                'q': q,
                'kind': kind,
                'tag': tag,
                'status': status,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Media Assets
     * Upload exactly one image per multipart request (despite the files array). The source is
     * limited to 20 MB and tags_json must be a JSON array; violations or invalid/unsafe
     * image/SVG returns 400. Stores a ready original asset in managed library storage; SVG is
     * sanitized and retained as vector. Each call creates asset metadata even when storage
     * deduplicates bytes.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param formData
     * @returns ManagerMediaAssetUploadResponse Successful Response
     * @throws ApiError
     */
    public static uploadMediaAssets(
        formData: Body_upload_media_assets,
    ): CancelablePromise<ManagerMediaAssetUploadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/media/assets',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Media Asset From Url
     * Fetch an HTTP(S) image from a public-network source and store it as a ready original
     * library asset. Redirects, MIME and size are checked; localhost/private-network sources
     * are rejected. Invalid source/content returns 400 and runtime storage failure 500. This
     * saves an asset rather than linking it to a product; no idempotency receipt exists.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param requestBody
     * @returns ManagerMediaAssetUploadResponse Successful Response
     * @throws ApiError
     */
    public static uploadMediaAssetFromUrl(
        requestBody: ManagerMediaAssetUrlUploadPayload,
    ): CancelablePromise<ManagerMediaAssetUploadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/media/assets/from-url',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Backfill Referenced Media Assets
     * Index existing catalog/content media references into library metadata without rewriting
     * their URLs. execute defaults to false and reports a plan; true creates up to limit
     * (1–5000) metadata records. Already indexed URLs are skipped; include_remote controls
     * recognition of remote references, not remote downloads. This is a synchronous backfill,
     * not ordinary upload or physical cleanup.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param execute
     * @param limit
     * @param includeRemote
     * @returns ManagerMediaBackfillReferencedAssetsResponse Successful Response
     * @throws ApiError
     */
    public static backfillReferencedMediaAssets(
        execute: boolean = false,
        limit: number = 500,
        includeRemote: boolean = false,
    ): CancelablePromise<ManagerMediaBackfillReferencedAssetsResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/media/assets/backfill-references',
            query: {
                'execute': execute,
                'limit': limit,
                'include_remote': includeRemote,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Media Background Removal Config
     * Read configured/default background-removal provider, rembg models/process mode and
     * preload options. No image is processed, model configuration changed or worker job
     * started by this request.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns ManagerBackgroundRemovalConfigResponse Successful Response
     * @throws ApiError
     */
    public static getMediaBackgroundRemovalConfig(): CancelablePromise<ManagerBackgroundRemovalConfigResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/media/assets/background-removal/options',
        });
    }
    /**
     * Update Media Asset
     * Update non-null metadata fields and replace tags when supplied; file bytes and URL
     * remain unchanged. Empty alt_text/description clears their value; null fields are
     * ignored. Missing asset returns 404; changing the kind of an in-use storefront_logo
     * returns 400. This global route can edit asset metadata across storefronts.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param assetId
     * @param requestBody
     * @returns ManagerMediaAssetResponse Successful Response
     * @throws ApiError
     */
    public static updateMediaAsset(
        assetId: number,
        requestBody: ManagerMediaAssetUpdatePayload,
    ): CancelablePromise<ManagerMediaAssetResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/media/assets/{asset_id}',
            path: {
                'asset_id': assetId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Media Asset
     * Delete library metadata, detach child parent references and attempt to remove the
     * underlying local file only when no references remain. Missing asset returns 404; known
     * usage blocks deletion with 409 unless force=true. force bypasses metadata usage
     * protection but never deletion of an in-use storefront logo. It does not delete child
     * assets or rewrite content references.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param assetId
     * @param force
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteMediaAsset(
        assetId: number,
        force: boolean = false,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/media/assets/{asset_id}',
            path: {
                'asset_id': assetId,
            },
            query: {
                'force': force,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Crop Media Asset
     * Crop a raster source and create a separate crop child asset, preserving the parent
     * asset. Crop coordinates are clamped to source bounds; SVG cropping is rejected. Missing
     * asset returns 404; unavailable/invalid source returns 400. The new processing variant is
     * not an original publication URL; repeating creates another metadata asset.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param assetId
     * @param requestBody
     * @returns ManagerMediaAssetResponse Successful Response
     * @throws ApiError
     */
    public static cropMediaAsset(
        assetId: number,
        requestBody: ManagerMediaAssetCropPayload,
    ): CancelablePromise<ManagerMediaAssetResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/media/assets/{asset_id}/crop',
            path: {
                'asset_id': assetId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Remove Media Asset Background
     * Synchronously remove a raster source background using provider/model and create a
     * processed child asset. The source is preserved; no product/brand/series reference is
     * automatically switched. Missing asset returns 404, invalid source/SVG/provider returns
     * 400 and runtime conflict 409. Processed library variants differ from permitted original
     * publication URLs; repeats create new metadata.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param assetId
     * @param provider Processing provider: auto, noop, manual, rembg, birefnet, ben
     * @param rembgModel Optional rembg model override
     * @returns ManagerMediaAssetResponse Successful Response
     * @throws ApiError
     */
    public static removeMediaAssetBackground(
        assetId: number,
        provider: string = 'auto',
        rembgModel?: (string | null),
    ): CancelablePromise<ManagerMediaAssetResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/media/assets/{asset_id}/remove-background',
            path: {
                'asset_id': assetId,
            },
            query: {
                'provider': provider,
                'rembg_model': rembgModel,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Media Processing Jobs
     * Read up to 100 newest shared media-processing jobs, optionally filtered by status.
     * meta.total is the returned row count, not the size of the full queue; there is no
     * page/offset. Lease tokens are excluded from normal Manager serialization. This does not
     * claim or retry jobs.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param status
     * @param limit
     * @returns ManagerMediaProcessingJobListResponse Successful Response
     * @throws ApiError
     */
    public static listMediaProcessingJobs(
        status?: (string | null),
        limit: number = 50,
    ): CancelablePromise<ManagerMediaProcessingJobListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/media/processing-jobs',
            query: {
                'status': status,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Media Processing Job
     * Persist a new queued background_removal or upscale job for a library raster asset.
     * Missing source returns 404; unsupported operation or SVG source returns 400. Lower
     * priority values are claimed first. The response confirms enqueue, not processing success
     * or publication; each POST creates another job and the original asset remains unchanged.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param assetId
     * @param requestBody
     * @returns ManagerMediaProcessingJobResponse Successful Response
     * @throws ApiError
     */
    public static createMediaProcessingJob(
        assetId: number,
        requestBody: ManagerMediaProcessingJobCreatePayload,
    ): CancelablePromise<ManagerMediaProcessingJobResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/media/processing-jobs/{asset_id}',
            path: {
                'asset_id': assetId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
