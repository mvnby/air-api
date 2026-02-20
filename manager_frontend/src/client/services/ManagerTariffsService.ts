/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerTariffCreatePayload } from '../models/ManagerTariffCreatePayload';
import type { ManagerTariffListResponse } from '../models/ManagerTariffListResponse';
import type { ManagerTariffResponse } from '../models/ManagerTariffResponse';
import type { ManagerTariffUpdatePayload } from '../models/ManagerTariffUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerTariffsService {
    /**
     * List Manager Tariffs
     * @returns ManagerTariffListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerTariffs(): CancelablePromise<ManagerTariffListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tariffs',
        });
    }
    /**
     * Create Manager Tariff
     * @param requestBody
     * @returns ManagerTariffResponse Successful Response
     * @throws ApiError
     */
    public static createManagerTariff(
        requestBody: ManagerTariffCreatePayload,
    ): CancelablePromise<ManagerTariffResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/tariffs',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Tariff
     * @param tariffId
     * @param requestBody
     * @returns ManagerTariffResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerTariff(
        tariffId: number,
        requestBody: ManagerTariffUpdatePayload,
    ): CancelablePromise<ManagerTariffResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/tariffs/{tariff_id}',
            path: {
                'tariff_id': tariffId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Tariff
     * @param tariffId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerTariff(
        tariffId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/tariffs/{tariff_id}',
            path: {
                'tariff_id': tariffId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
