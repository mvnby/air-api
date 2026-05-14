/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerQuickTariffListResponse } from '../models/ManagerQuickTariffListResponse';
import type { ManagerTariffCreatePayload } from '../models/ManagerTariffCreatePayload';
import type { ManagerTariffListResponse } from '../models/ManagerTariffListResponse';
import type { ManagerTariffResponse } from '../models/ManagerTariffResponse';
import type { ManagerTariffRuleCreatePayload } from '../models/ManagerTariffRuleCreatePayload';
import type { ManagerTariffRuleListResponse } from '../models/ManagerTariffRuleListResponse';
import type { ManagerTariffRuleResponse } from '../models/ManagerTariffRuleResponse';
import type { ManagerTariffRuleUpdatePayload } from '../models/ManagerTariffRuleUpdatePayload';
import type { ManagerTariffServiceKind } from '../models/ManagerTariffServiceKind';
import type { ManagerTariffUpdatePayload } from '../models/ManagerTariffUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerTariffsService {
    /**
     * List Manager Tariffs
     * @param serviceKind
     * @param includeInactive
     * @returns ManagerTariffListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerTariffs(
        serviceKind?: (ManagerTariffServiceKind | null),
        includeInactive: boolean = true,
    ): CancelablePromise<ManagerTariffListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tariffs',
            query: {
                'service_kind': serviceKind,
                'include_inactive': includeInactive,
            },
            errors: {
                422: `Validation Error`,
            },
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
     * List Manager Quick Tariffs
     * @param q
     * @param serviceKind
     * @param limit
     * @returns ManagerQuickTariffListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerQuickTariffs(
        q: string = '',
        serviceKind?: (ManagerTariffServiceKind | null),
        limit: number = 10,
    ): CancelablePromise<ManagerQuickTariffListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tariffs/quick-add',
            query: {
                'q': q,
                'service_kind': serviceKind,
                'limit': limit,
            },
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
    /**
     * List Manager Favorite Tariff Rules
     * @param serviceKind
     * @param includeInactive
     * @param excludeTariffId
     * @returns ManagerTariffRuleListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerFavoriteTariffRules(
        serviceKind: ManagerTariffServiceKind,
        includeInactive: boolean = false,
        excludeTariffId?: (number | null),
    ): CancelablePromise<ManagerTariffRuleListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tariffs/rules/favorites',
            query: {
                'service_kind': serviceKind,
                'include_inactive': includeInactive,
                'exclude_tariff_id': excludeTariffId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Tariff Rules
     * @param tariffId
     * @param includeInactive
     * @returns ManagerTariffRuleListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerTariffRules(
        tariffId: number,
        includeInactive: boolean = true,
    ): CancelablePromise<ManagerTariffRuleListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tariffs/{tariff_id}/rules',
            path: {
                'tariff_id': tariffId,
            },
            query: {
                'include_inactive': includeInactive,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Tariff Rule
     * @param tariffId
     * @param requestBody
     * @returns ManagerTariffRuleResponse Successful Response
     * @throws ApiError
     */
    public static createManagerTariffRule(
        tariffId: number,
        requestBody: ManagerTariffRuleCreatePayload,
    ): CancelablePromise<ManagerTariffRuleResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/tariffs/{tariff_id}/rules',
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
     * Update Manager Tariff Rule
     * @param tariffId
     * @param ruleId
     * @param requestBody
     * @returns ManagerTariffRuleResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerTariffRule(
        tariffId: number,
        ruleId: number,
        requestBody: ManagerTariffRuleUpdatePayload,
    ): CancelablePromise<ManagerTariffRuleResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/tariffs/{tariff_id}/rules/{rule_id}',
            path: {
                'tariff_id': tariffId,
                'rule_id': ruleId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Tariff Rule
     * @param tariffId
     * @param ruleId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerTariffRule(
        tariffId: number,
        ruleId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/tariffs/{tariff_id}/rules/{rule_id}',
            path: {
                'tariff_id': tariffId,
                'rule_id': ruleId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
