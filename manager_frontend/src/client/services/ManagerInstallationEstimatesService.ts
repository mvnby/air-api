/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationResolvePayload } from '../models/InstallationResolvePayload';
import type { InstallationResolveResponse } from '../models/InstallationResolveResponse';
import type { ManagerInstallationAttachPayload } from '../models/ManagerInstallationAttachPayload';
import type { ManagerInstallationAttachResponse } from '../models/ManagerInstallationAttachResponse';
import type { ManagerInstallationConfirmPayload } from '../models/ManagerInstallationConfirmPayload';
import type { ManagerInstallationConfirmResponse } from '../models/ManagerInstallationConfirmResponse';
import type { ManagerInstallationEstimateRevisionResponse } from '../models/ManagerInstallationEstimateRevisionResponse';
import type { ManagerInstallationPreviewPayload } from '../models/ManagerInstallationPreviewPayload';
import type { ManagerInstallationPreviewResponse } from '../models/ManagerInstallationPreviewResponse';
import type { ManagerInstallationStandardTariffList } from '../models/ManagerInstallationStandardTariffList';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerInstallationEstimatesService {
    /**
     * List Manager Installation Standard Tariffs
     * @returns ManagerInstallationStandardTariffList Successful Response
     * @throws ApiError
     */
    public static listManagerInstallationStandardTariffs(): CancelablePromise<ManagerInstallationStandardTariffList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installation-estimates/standard-tariffs',
        });
    }
    /**
     * Resolve Manager Installation Tariff
     * @param requestBody
     * @returns InstallationResolveResponse Successful Response
     * @throws ApiError
     */
    public static resolveManagerInstallationTariff(
        requestBody: InstallationResolvePayload,
    ): CancelablePromise<InstallationResolveResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-estimates/resolve',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Manager Installation Estimate
     * @param idempotencyKey
     * @param requestBody
     * @returns ManagerInstallationPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewManagerInstallationEstimate(
        idempotencyKey: string,
        requestBody: ManagerInstallationPreviewPayload,
    ): CancelablePromise<ManagerInstallationPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-estimates/preview',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Confirm Manager Installation Estimate
     * @param idempotencyKey
     * @param requestBody
     * @returns ManagerInstallationConfirmResponse Successful Response
     * @throws ApiError
     */
    public static confirmManagerInstallationEstimate(
        idempotencyKey: string,
        requestBody: ManagerInstallationConfirmPayload,
    ): CancelablePromise<ManagerInstallationConfirmResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-estimates/confirm',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Installation Estimate Revision
     * @param estimateId
     * @param revision
     * @returns ManagerInstallationEstimateRevisionResponse Successful Response
     * @throws ApiError
     */
    public static getManagerInstallationEstimateRevision(
        estimateId: number,
        revision: number,
    ): CancelablePromise<ManagerInstallationEstimateRevisionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installation-estimates/{estimate_id}/revisions/{revision}',
            path: {
                'estimate_id': estimateId,
                'revision': revision,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Attach Manager Installation Estimate
     * @param estimateId
     * @param orderId
     * @param proposalId
     * @param idempotencyKey
     * @param requestBody
     * @returns ManagerInstallationAttachResponse Successful Response
     * @throws ApiError
     */
    public static attachManagerInstallationEstimate(
        estimateId: number,
        orderId: number,
        proposalId: number,
        idempotencyKey: string,
        requestBody: ManagerInstallationAttachPayload,
    ): CancelablePromise<ManagerInstallationAttachResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-estimates/{estimate_id}/orders/{order_id}/proposals/{proposal_id}/attach',
            path: {
                'estimate_id': estimateId,
                'order_id': orderId,
                'proposal_id': proposalId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
