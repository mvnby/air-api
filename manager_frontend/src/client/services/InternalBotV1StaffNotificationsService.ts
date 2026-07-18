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
