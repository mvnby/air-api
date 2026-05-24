/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerYandexBusinessService {
    /**
     * Get Manager Yandex Business Price List
     * @param siteBaseUrl Public storefront base URL for product and image links
     * @returns string Successful Response
     * @throws ApiError
     */
    public static getManagerYandexBusinessPriceList(
        siteBaseUrl: string = 'https://mvn.by',
    ): CancelablePromise<string> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/yandex-business/price-list.yml',
            query: {
                'site_base_url': siteBaseUrl,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
