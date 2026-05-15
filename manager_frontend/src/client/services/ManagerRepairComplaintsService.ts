/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerRepairComplaintPresetCreatePayload } from '../models/ManagerRepairComplaintPresetCreatePayload';
import type { ManagerRepairComplaintPresetListResponse } from '../models/ManagerRepairComplaintPresetListResponse';
import type { ManagerRepairComplaintPresetResponse } from '../models/ManagerRepairComplaintPresetResponse';
import type { ManagerRepairComplaintPresetUpdatePayload } from '../models/ManagerRepairComplaintPresetUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerRepairComplaintsService {
    /**
     * List Manager Repair Complaint Presets
     * @param q
     * @param complaintGroup
     * @param includeInactive
     * @param favoritesOnly
     * @param limit
     * @returns ManagerRepairComplaintPresetListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerRepairComplaintPresets(
        q: string = '',
        complaintGroup?: (string | null),
        includeInactive: boolean = false,
        favoritesOnly: boolean = false,
        limit: number = 100,
    ): CancelablePromise<ManagerRepairComplaintPresetListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/repair-complaints',
            query: {
                'q': q,
                'complaint_group': complaintGroup,
                'include_inactive': includeInactive,
                'favorites_only': favoritesOnly,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Repair Complaint Preset
     * @param requestBody
     * @returns ManagerRepairComplaintPresetResponse Successful Response
     * @throws ApiError
     */
    public static createManagerRepairComplaintPreset(
        requestBody: ManagerRepairComplaintPresetCreatePayload,
    ): CancelablePromise<ManagerRepairComplaintPresetResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/repair-complaints',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Repair Complaint Preset
     * @param presetId
     * @param requestBody
     * @returns ManagerRepairComplaintPresetResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerRepairComplaintPreset(
        presetId: number,
        requestBody: ManagerRepairComplaintPresetUpdatePayload,
    ): CancelablePromise<ManagerRepairComplaintPresetResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/repair-complaints/{preset_id}',
            path: {
                'preset_id': presetId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Repair Complaint Preset
     * @param presetId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerRepairComplaintPreset(
        presetId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/repair-complaints/{preset_id}',
            path: {
                'preset_id': presetId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
