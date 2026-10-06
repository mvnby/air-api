/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotStaffNotificationAckRequest } from '../models/BotStaffNotificationAckRequest';
import type { BotStaffNotificationClaimRequest } from '../models/BotStaffNotificationClaimRequest';
import type { BotStaffNotificationClaimResponse } from '../models/BotStaffNotificationClaimResponse';
import type { BotStaffNotificationMutationResponse } from '../models/BotStaffNotificationMutationResponse';
import type { BotStaffNotificationNackRequest } from '../models/BotStaffNotificationNackRequest';
import type { BotStaffNotificationRenewRequest } from '../models/BotStaffNotificationRenewRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InternalBotV1StaffNotificationsService {
    /**
     * Claim Staff Notification
     * Claim the next eligible staff-bot Telegram outbox delivery for a worker, recovering
     * expired leases and materializing pending outbox events. Returns notification=null when
     * none is claimable. The service checks recipient/stage freshness; this endpoint uses
     * worker identity, not a caller Telegram actor.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param requestBody
     * @returns BotStaffNotificationClaimResponse Successful Response
     * @throws ApiError
     */
    public static claimInternalBotStaffNotificationV1(
        requestBody: BotStaffNotificationClaimRequest,
    ): CancelablePromise<BotStaffNotificationClaimResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/staff-notifications/claim',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Renew Staff Notification
     * Extend a claimed staff notification lease using the worker identity and lease token.
     * Missing delivery returns 404; a lost/mismatched lease returns 409. This does not send or
     * acknowledge the Telegram message.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param deliveryId
     * @param requestBody
     * @returns BotStaffNotificationMutationResponse Successful Response
     * @throws ApiError
     */
    public static renewInternalBotStaffNotificationV1(
        deliveryId: string,
        requestBody: BotStaffNotificationRenewRequest,
    ): CancelablePromise<BotStaffNotificationMutationResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/staff-notifications/{delivery_id}/renew',
            path: {
                'delivery_id': deliveryId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Ack Staff Notification
     * Record successful Telegram delivery under the current worker lease and supplied provider
     * result. Missing delivery returns 404; lost/mismatched lease returns 409. The caller
     * performs delivery; this HTTP operation updates outbox state.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param deliveryId
     * @param requestBody
     * @returns BotStaffNotificationMutationResponse Successful Response
     * @throws ApiError
     */
    public static ackInternalBotStaffNotificationV1(
        deliveryId: string,
        requestBody: BotStaffNotificationAckRequest,
    ): CancelablePromise<BotStaffNotificationMutationResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/staff-notifications/{delivery_id}/ack',
            path: {
                'delivery_id': deliveryId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Nack Staff Notification
     * Record a failed staff Telegram delivery under the current worker lease, applying the
     * delivery service retry/failure decision. Missing delivery returns 404; lost/mismatched
     * lease returns 409. Inspect returned status/next_attempt_at rather than assuming
     * immediate retry.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param deliveryId
     * @param requestBody
     * @returns BotStaffNotificationMutationResponse Successful Response
     * @throws ApiError
     */
    public static nackInternalBotStaffNotificationV1(
        deliveryId: string,
        requestBody: BotStaffNotificationNackRequest,
    ): CancelablePromise<BotStaffNotificationMutationResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/staff-notifications/{delivery_id}/nack',
            path: {
                'delivery_id': deliveryId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
