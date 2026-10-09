/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { NativeOpportunity } from '../models/NativeOpportunity';
import type { TenderLeadPushResult } from '../models/TenderLeadPushResult';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class IntegrationsTendersService {
    /**
     * Push Tender Lead
     * Accept one native opportunity using the dedicated Bearer key and server-owned destination.
     *
     * Activation and writable-primary controls fail closed. Replays deduplicate by source and
     * external tender ID; source updates preserve staff workflow and reviewed enrichment.
     * Creation follows the existing confirmed/eligible/deadline rules. Older updates cannot
     * replace newer source state. Push does not advance the shared pull cursor or timestamp.
     * The validated native model is limited to 64 KiB; IDs are producer-owned and timestamps
     * are timezone-aware. Returns a nullable order ID and created/updated/unchanged/skipped.
     * Configured intake rejects missing/wrong keys with 401, invalid destination with 403,
     * disabled/unwritable intake with 503 and malformed payload with 422. The outer HA fence
     * may return its own 503 before routing.
     * No source HTTP request, customer qualification or downstream business action is performed.
     *
     * See [intake contract](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#direct-push-intake-849-first-release-slice).
     * @param requestBody
     * @returns TenderLeadPushResult Successful Response
     * @throws ApiError
     */
    public static pushTenderLead(
        requestBody: NativeOpportunity,
    ): CancelablePromise<TenderLeadPushResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/integrations/tenders/leads',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
