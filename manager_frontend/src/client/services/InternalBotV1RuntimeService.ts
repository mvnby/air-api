/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotFsmStateGetRequest } from '../models/BotFsmStateGetRequest';
import type { BotFsmStateResponse } from '../models/BotFsmStateResponse';
import type { BotFsmStateUpdateRequest } from '../models/BotFsmStateUpdateRequest';
import type { BotRuntimeLeaseRequest } from '../models/BotRuntimeLeaseRequest';
import type { BotRuntimeLeaseResponse } from '../models/BotRuntimeLeaseResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InternalBotV1RuntimeService {
    /**
     * Get Fsm State
     * @param requestBody
     * @returns BotFsmStateResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotFsmStateV1(
        requestBody: BotFsmStateGetRequest,
    ): CancelablePromise<BotFsmStateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/fsm/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Fsm State
     * @param requestBody
     * @returns BotFsmStateResponse Successful Response
     * @throws ApiError
     */
    public static updateInternalBotFsmStateV1(
        requestBody: BotFsmStateUpdateRequest,
    ): CancelablePromise<BotFsmStateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/fsm/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Acquire Runtime Lease
     * @param requestBody
     * @returns BotRuntimeLeaseResponse Successful Response
     * @throws ApiError
     */
    public static acquireInternalBotRuntimeLeaseV1(
        requestBody: BotRuntimeLeaseRequest,
    ): CancelablePromise<BotRuntimeLeaseResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/runtime-leases/acquire',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Renew Runtime Lease
     * @param requestBody
     * @returns BotRuntimeLeaseResponse Successful Response
     * @throws ApiError
     */
    public static renewInternalBotRuntimeLeaseV1(
        requestBody: BotRuntimeLeaseRequest,
    ): CancelablePromise<BotRuntimeLeaseResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/runtime-leases/renew',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Release Runtime Lease
     * @param requestBody
     * @returns BotRuntimeLeaseResponse Successful Response
     * @throws ApiError
     */
    public static releaseInternalBotRuntimeLeaseV1(
        requestBody: BotRuntimeLeaseRequest,
    ): CancelablePromise<BotRuntimeLeaseResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/runtime-leases/release',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
