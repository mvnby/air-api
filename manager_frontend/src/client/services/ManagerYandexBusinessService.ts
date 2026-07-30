/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { YandexBusinessFeedQualityReport } from '../models/YandexBusinessFeedQualityReport';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerYandexBusinessService {
    /**
     * Get Manager Yandex Business Price List
     * @returns string Successful Response
     * @throws ApiError
     */
    public static getManagerYandexBusinessPriceList(): CancelablePromise<string> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/yandex-business/price-list.yml',
        });
    }
    /**
     * Get Manager Yandex Business Quality Report
     * @returns YandexBusinessFeedQualityReport Successful Response
     * @throws ApiError
     */
    public static getManagerYandexBusinessQualityReport(): CancelablePromise<YandexBusinessFeedQualityReport> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/yandex-business/quality-report',
        });
    }
}
