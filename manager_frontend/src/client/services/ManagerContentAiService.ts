/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BrandShortDescriptionDraft } from '../models/BrandShortDescriptionDraft';
import type { BrandShortDescriptionDraftRequest } from '../models/BrandShortDescriptionDraftRequest';
import type { FeatureContentDraft } from '../models/FeatureContentDraft';
import type { FeatureContentDraftRequest } from '../models/FeatureContentDraftRequest';
import type { ProductSeriesContentDraft } from '../models/ProductSeriesContentDraft';
import type { ProductSeriesContentDraftRequest } from '../models/ProductSeriesContentDraftRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerContentAiService {
    /**
     * Create Manager Brand Short Description Ai Draft
     * Generate a short-description draft from supplied full brand copy without saving the
     * brand. Blank/invalid input returns 422; rate/concurrency limits return 429 with
     * Retry-After; unavailable configuration/retryable provider failures return 503 and other
     * provider failures return 502. Repeating makes another provider request and may return
     * different text.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param requestBody
     * @returns BrandShortDescriptionDraft Successful Response
     * @throws ApiError
     */
    public static createManagerBrandShortDescriptionAiDraft(
        requestBody: BrandShortDescriptionDraftRequest,
    ): CancelablePromise<BrandShortDescriptionDraft> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/content-ai/brands/short-description/draft',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Feature Content Ai Draft
     * Generate a feature content/SEO draft either from a public source URL or by polishing
     * pasted text; input modes are mutually exclusive. The response is editor draft data and
     * does not create/update a feature. Invalid/unsafe source returns 422, upstream fetch
     * failure 502, limits 429 with Retry-After, and provider failures 502/503. Repeating calls
     * the provider again.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
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
     * Generate a series tagline/content/SEO draft from a public source or pasted full
     * description. Series/brand identity is context; no series or assignments are saved.
     * Invalid/unsafe source returns 422, upstream fetch failure 502, limits 429 with
     * Retry-After and provider failures 502/503. Repeating may produce different draft text.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
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
