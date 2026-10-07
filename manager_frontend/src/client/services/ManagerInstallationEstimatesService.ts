/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationResolvePayload } from '../models/InstallationResolvePayload';
import type { InstallationResolveResponse } from '../models/InstallationResolveResponse';
import type { ManagerInstallationAttachPayload } from '../models/ManagerInstallationAttachPayload';
import type { ManagerInstallationAttachResponse } from '../models/ManagerInstallationAttachResponse';
import type { ManagerInstallationConfirmPayload } from '../models/ManagerInstallationConfirmPayload';
import type { ManagerInstallationConfirmResponse } from '../models/ManagerInstallationConfirmResponse';
import type { ManagerInstallationEstimateRevisionResponse } from '../models/ManagerInstallationEstimateRevisionResponse';
import type { ManagerInstallationPreviewPayload } from '../models/ManagerInstallationPreviewPayload';
import type { ManagerInstallationPreviewResponse } from '../models/ManagerInstallationPreviewResponse';
import type { ManagerInstallationStandardSuggestionsPayload } from '../models/ManagerInstallationStandardSuggestionsPayload';
import type { ManagerInstallationStandardSuggestionsResponse } from '../models/ManagerInstallationStandardSuggestionsResponse';
import type { ManagerInstallationStandardTariffList } from '../models/ManagerInstallationStandardTariffList';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerInstallationEstimatesService {
    /**
     * List Manager Installation Standard Tariffs
     * Read fixed standard complete-split-system tariffs from the tenant’s published price
     * book, using capacity-only or type-only matching. Strict product matches are excluded.
     * With no published book the response contains no revision and no items. These suggestions
     * are for free commercial rows; reading them does not bind equipment or confirm an
     * estimate.
     *
     * Access and scope: Manager access is required; published installation pricing belongs to
     * the authenticated tenant, independently of storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @returns ManagerInstallationStandardTariffList Successful Response
     * @throws ApiError
     */
    public static listManagerInstallationStandardTariffs(): CancelablePromise<ManagerInstallationStandardTariffList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installation-estimates/standard-tariffs',
        });
    }
    /**
     * Suggest Manager Installation Standard Tariffs
     * Resolve standard installation suggestions for at most 100 submitted visible catalog
     * products against the tenant’s current published book. Unknown/inaccessible products and
     * incomplete, ambiguous or unmatched profiles are omitted; repeated product IDs are
     * deduplicated. This reads suggestions without creating an estimate, equipment claim or
     * proposal line.
     *
     * Access and scope: Manager access is required; published installation pricing belongs to
     * the authenticated tenant, independently of storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param requestBody
     * @returns ManagerInstallationStandardSuggestionsResponse Successful Response
     * @throws ApiError
     */
    public static suggestManagerInstallationStandardTariffs(
        requestBody: ManagerInstallationStandardSuggestionsPayload,
    ): CancelablePromise<ManagerInstallationStandardSuggestionsResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-estimates/standard-suggestions',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Resolve Manager Installation Tariff
     * Resolve installation input against the tenant’s current published book and return
     * fixed/from/provisional/quote/unavailable status with its reason. Missing published book
     * produces quote with price_book_not_published rather than a fabricated price. No preview
     * snapshot, estimate or proposal line is saved.
     *
     * Access and scope: Manager access is required; published installation pricing belongs to
     * the authenticated tenant, independently of storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param requestBody
     * @returns InstallationResolveResponse Successful Response
     * @throws ApiError
     */
    public static resolveManagerInstallationTariff(
        requestBody: InstallationResolvePayload,
    ): CancelablePromise<InstallationResolveResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-estimates/resolve',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Manager Installation Estimate
     * Calculate installation pricing; fixed/from results save a preview snapshot with opaque
     * preview_ref valid for 30 minutes, while quote/unresolved results may have no snapshot.
     * Idempotency-Key is required: an unexpired saved key/input replays and changed input
     * under that key returns 409. expected_revision mismatch returns 409 price_changed;
     * receipt contention/unavailable preview reference returns 503 with Retry-After. Expired
     * keys can produce a fresh calculation. This does not accept a price or add order lines;
     * only fixed previews can subsequently be confirmed.
     *
     * Access and scope: Manager access is required; pricing uses the authenticated tenant’s
     * book and saved previews belong to that tenant and the selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param idempotencyKey
     * @param requestBody
     * @returns ManagerInstallationPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewManagerInstallationEstimate(
        idempotencyKey: string,
        requestBody: ManagerInstallationPreviewPayload,
    ): CancelablePromise<ManagerInstallationPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-estimates/preview',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Confirm Manager Installation Estimate
     * Accept a fixed, unexpired preview as an immutable estimate revision for the scoped
     * order/proposal, verifying equipment identity and any explicitly verified service-only
     * profiles. Idempotency-Key is required; same key/payload replays and changed payload
     * returns 409. Missing target/preview returns 404; non-fixed/expired preview or
     * sent/approved proposal returns 409. A changed price book returns 409 price_changed with
     * a fresh preview requiring new consent; unavailable receipt storage returns 503 with
     * Retry-After. This saves the accepted estimate; proposal service lines are added
     * separately by attach.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param idempotencyKey
     * @param requestBody
     * @returns ManagerInstallationConfirmResponse Successful Response
     * @throws ApiError
     */
    public static confirmManagerInstallationEstimate(
        idempotencyKey: string,
        requestBody: ManagerInstallationConfirmPayload,
    ): CancelablePromise<ManagerInstallationConfirmResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-estimates/confirm',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Installation Estimate Revision
     * Read one immutable accepted installation estimate revision and its factual
     * pricing/confirmation snapshot. Missing or out-of-scope estimate/revision returns 404.
     * Current tariff edits and price-book publication do not recalculate these saved amounts.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param estimateId
     * @param revision
     * @returns ManagerInstallationEstimateRevisionResponse Successful Response
     * @throws ApiError
     */
    public static getManagerInstallationEstimateRevision(
        estimateId: number,
        revision: number,
    ): CancelablePromise<ManagerInstallationEstimateRevisionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installation-estimates/{estimate_id}/revisions/{revision}',
            path: {
                'estimate_id': estimateId,
                'revision': revision,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Attach Manager Installation Estimate
     * Add accepted installation revision lines to its original scoped order/proposal in
     * collapsed or detailed projection, preserving the accepted total and recalculating order
     * financials. Idempotency-Key is required; changed payload under the key returns 409 and
     * receipt unavailability 503 with Retry-After. Missing or mismatched estimate/target
     * returns 404; conflicting existing projection, duplicate installation identity or
     * noneditable proposal returns 409. An identical existing attachment is reused; a new
     * attachment requires an editable proposal. This writes proposal lines without rerunning
     * current pricing.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param estimateId
     * @param orderId
     * @param proposalId
     * @param idempotencyKey
     * @param requestBody
     * @returns ManagerInstallationAttachResponse Successful Response
     * @throws ApiError
     */
    public static attachManagerInstallationEstimate(
        estimateId: number,
        orderId: number,
        proposalId: number,
        idempotencyKey: string,
        requestBody: ManagerInstallationAttachPayload,
    ): CancelablePromise<ManagerInstallationAttachResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-estimates/{estimate_id}/orders/{order_id}/proposals/{proposal_id}/attach',
            path: {
                'estimate_id': estimateId,
                'order_id': orderId,
                'proposal_id': proposalId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
