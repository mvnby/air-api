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
     * Transcribe a voice upload and parse an editable quick-order draft for an active Manager
     * Telegram actor (403 otherwise); no order is created. Audio is limited to 180 seconds and
     * 8 MB; empty/invalid audio returns 422 and oversize file 413. Disabled transcription or
     * unavailable audio tooling returns 503, provider failure 502 and provider timeout 504.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
