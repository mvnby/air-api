/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FeatureContentDraft } from '../models/FeatureContentDraft';
import type { FeatureContentDraftRequest } from '../models/FeatureContentDraftRequest';
import type { ProductSeriesContentDraft } from '../models/ProductSeriesContentDraft';
import type { ProductSeriesContentDraftRequest } from '../models/ProductSeriesContentDraftRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerContentAiService {
    /**
     * Create Manager Feature Content Ai Draft
     * @param requestBody
     * @returns FeatureContentDraft Successful Response
     * @throws ApiError
     */
    public static createManagerFeatureContentAiDraft(
        requestBody: FeatureContentDraftRequest,
    ): CancelablePromise<FeatureContentDraft> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/content-ai/features/draft',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Series Content Ai Draft
     * @param requestBody
     * @returns ProductSeriesContentDraft Successful Response
     * @throws ApiError
     */
    public static createManagerSeriesContentAiDraft(
        requestBody: ProductSeriesContentDraftRequest,
    ): CancelablePromise<ProductSeriesContentDraft> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/content-ai/series/draft',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
