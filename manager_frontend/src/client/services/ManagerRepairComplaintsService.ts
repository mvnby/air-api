/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerRepairActAiDraftPayload } from '../models/ManagerRepairActAiDraftPayload';
import type { ManagerRepairActAiDraftResponse } from '../models/ManagerRepairActAiDraftResponse';
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
     * Read shared complaint presets filtered by text, group and favorite status; inactive
     * presets are excluded by default. limit is 1–200, default 100; results follow
     * favorite/sort/group/name ordering. No repair order or diagnostic statement is saved.
     *
     * Access and scope: Manager access is required; these definitions are shared across
     * tenants. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Create a shared complaint preset after cleaning whitespace. Empty phrase returns 400 and
     * an existing normalized group/phrase returns 409. This defines reusable text without
     * modifying repair orders; repeated creation is subject to duplicate detection rather than
     * an idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Generate Manager Repair Act Ai Draft
     * Generate structured repair diagnostic metadata using the configured DeepSeek provider
     * and local defect templates. The response is a draft; no order, diagnosis or act document
     * is saved. Value/input errors and HTTP provider failures caught by this route return 400.
     * Repeats call the provider again and may produce different text.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ManagerRepairActAiDraftResponse Successful Response
     * @throws ApiError
     */
    public static generateManagerRepairActAiDraft(
        requestBody: ManagerRepairActAiDraftPayload,
    ): CancelablePromise<ManagerRepairActAiDraftResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/repair-complaints/ai-draft',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Repair Complaint Preset
     * Update submitted preset fields after cleaning text. Missing preset returns 404, empty
     * phrase 400 and conflicting normalized group/phrase 409. Changes affect future selection
     * and do not rewrite text already saved in repair orders.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Permanently delete a shared complaint preset. Missing preset returns 404, including
     * repeats. This does not remove complaint text already copied into repair orders.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
