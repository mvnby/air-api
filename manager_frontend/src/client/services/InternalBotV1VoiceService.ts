/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_parse_internal_bot_voice_quick_order_v1 } from '../models/Body_parse_internal_bot_voice_quick_order_v1';
import type { BotVoiceQuickOrderParseResponse } from '../models/BotVoiceQuickOrderParseResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InternalBotV1VoiceService {
    /**
     * Parse Internal Bot Voice Quick Order
     * @param formData
     * @returns BotVoiceQuickOrderParseResponse Successful Response
     * @throws ApiError
     */
    public static parseInternalBotVoiceQuickOrderV1(
        formData: Body_parse_internal_bot_voice_quick_order_v1,
    ): CancelablePromise<BotVoiceQuickOrderParseResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/quick-orders/parse-voice',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
