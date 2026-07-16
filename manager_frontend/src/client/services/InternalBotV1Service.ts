/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotApiHealthResponse } from '../models/BotApiHealthResponse';
import type { BotStaffContextResponse } from '../models/BotStaffContextResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InternalBotV1Service {
    /**
     * Get Internal Bot Api Health
     * @returns BotApiHealthResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotApiHealthV1(): CancelablePromise<BotApiHealthResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/internal/bot/v1/health',
        });
    }
    /**
     * Get Internal Bot Staff Context
     * @param telegramId
     * @returns BotStaffContextResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotStaffContextV1(
        telegramId: number,
    ): CancelablePromise<BotStaffContextResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/internal/bot/v1/staff/context/{telegram_id}',
            path: {
                'telegram_id': telegramId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
