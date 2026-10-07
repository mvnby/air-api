/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallationRateListResponse } from '../models/ManagerInstallationRateListResponse';
import type { ManagerInstallationRateResponse } from '../models/ManagerInstallationRateResponse';
import type { ManagerInstallationRateUpdatePayload } from '../models/ManagerInstallationRateUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerInstallationRatesService {
    /**
     * List Manager Installation Rates
     * Read the tenant’s legacy installation-rate projection before price-book publication.
     * Once a book is published, items is empty and published_price_book_revision identifies
     * the active replacement. This does not delete rates or accepted historical calculations.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @returns ManagerInstallationRateListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerInstallationRates(): CancelablePromise<ManagerInstallationRateListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installation-rates',
        });
    }
    /**
     * Update Manager Installation Rate
     * Save submitted legacy rate fields under the tenant publication lock.
     * Missing/out-of-scope rate returns 404; after book publication the route returns 409
     * installation_rates_retired. This edits the pre-publication rate dictionary without
     * publishing a price book or rewriting accepted estimates.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param rateId
     * @param requestBody
     * @returns ManagerInstallationRateResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerInstallationRate(
        rateId: number,
        requestBody: ManagerInstallationRateUpdatePayload,
    ): CancelablePromise<ManagerInstallationRateResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/installation-rates/{rate_id}',
            path: {
                'rate_id': rateId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
