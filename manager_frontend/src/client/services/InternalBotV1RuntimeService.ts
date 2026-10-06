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
     * Read durable bot FSM state by service storage_key; missing state is state=null/data={}.
     * This service primitive does not authorize a Telegram actor and is not a tenant CRM read.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Update the service-owned FSM row under storage_key. write_state and write_data choose
     * which parts to replace; data is replaced, not merged. Empty state/data removes the row.
     * No Telegram actor check or caller-supplied version precondition is provided.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Acquire or extend a service process lease by name and owner_id. A different owner with a
     * nonexpired lease yields acquired=false rather than 409; same owner or expired lease can
     * be acquired for ttl_seconds. This primitive does not authorize a Telegram actor.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Use the same acquire-or-extend semantics as /runtime-leases/acquire. If absent or
     * expired the lease can be acquired; it is not restricted to renewing an existing row. A
     * different live owner yields acquired=false. No Telegram actor check is performed.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Release a service process lease only when its owner_id matches. Missing lease or another
     * owner returns acquired=false; a successful release returns acquired=true. No Telegram
     * actor check is performed.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
