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
import type { ManagerMediaProcessingJobCreatePayload } from '../models/ManagerMediaProcessingJobCreatePayload';
import type { ManagerMediaProcessingJobListResponse } from '../models/ManagerMediaProcessingJobListResponse';
import type { ManagerMediaProcessingJobResponse } from '../models/ManagerMediaProcessingJobResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerMediaService {
    /**
     * List Media Assets
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
     * Get Media Background Removal Config
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
